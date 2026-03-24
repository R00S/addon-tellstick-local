"""TellStick Local integration – hub setup and event dispatch."""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import time
from typing import Any

from homeassistant.components.persistent_notification import (
    async_create as pn_async_create,
    async_dismiss as pn_async_dismiss,
)
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import (
    DeviceEvent,
    RawDeviceEvent,
    SensorEvent,
    TellStickController,
)
from .const import (
    BACKEND_DUO,
    BACKEND_NET,
    CONF_AUTOMATIC_ADD,
    CONF_BACKEND,
    CONF_COMMAND_PORT,
    CONF_DETECT_SARTANO,
    CONF_DEVICE_HOUSE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    CONF_EVENT_PORT,
    CONF_IGNORED_UIDS,
    CONF_MIRROR_OF,
    DEFAULT_AUTOMATIC_ADD,
    DEFAULT_DETECT_SARTANO,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_MIRRORS,
    ENTRY_TELLSTICK_CONTROLLER,
    INTEGRATION_VERSION,
    PLATFORMS,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
    build_device_uid,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Multi-protocol detection: why one button press creates multiple events
# ---------------------------------------------------------------------------
#
# telldusd (telldus-core) runs ALL protocol decoders on every received RF
# signal.  A single button press can produce multiple TDRawDeviceEvent
# callbacks with different protocol/model/house/unit interpretations.
#
# Source: telldus-core Protocol.cpp::decodeData() (lines 216-261)
#   - "arctech" branch decodes ProtocolNexa → ProtocolWaveman →
#     ProtocolSartano in that fixed order (single list, published
#     sequentially by Controller.cpp::decodePublishData lines 79-83).
#   - "everflourish" is a separate else-if branch — it fires only when
#     the firmware classifies the raw data differently, potentially from
#     a separate RF transmission seconds later.
#
# Example: Luxorparts 50969 remote (A-on) produces THREE events:
#   1. arctech/selflearning (house: 2673666, unit: 1)
#   2. everflourish/selflearning (house: 3264, unit: 1)
#   3. waveman/codeswitch (house: A, unit: 10)
#
# Controller.cpp has a 1-second dedup on exact raw data strings, but
# different protocol decodings produce different strings → no dedup.
#
# How other implementations handle this:
#   - NexaHome (Android app): ignores TDRawDeviceEvent for class:command
#     entirely.  Only uses TDDeviceEvent (named/registered devices) with
#     a 3-second dedup keyed on deviceId+method+value.
#     Source: decompiled JnaCmd$_D.class, u$_G.class
#   - TelldusCenter (Qt GUI): deduplicates scan results by protocol+model
#     pair, ignoring house/unit.  One entry per protocol+model combination.
#     Source: filtereddeviceproxymodel.cpp:60-70 (addFilter)
#   - RFXtrx (HA core): uses PT2262 data_bits masking — user configures
#     how many low bits are command data, system masks them for stable ID.
#   - RFLink (HA core): manual YAML aliasing — user maps multiple IDs to
#     one entity.
#
# Our approach (three complementary layers):
#   1. _discovered_uids: set — blocks same UID from being discovered twice
#   2. _last_known_event_time: float — suppresses unknown events within 1s
#      of a known device event (cross-protocol false positives from the
#      same RF signal; works because arctech is decoded FIRST)
#   3. _discovered_protocol_models: set — deduplicates by protocol+model
#      per session (TelldusCenter approach; NOT pre-seeded from stored
#      devices — pre-seeding blocks new devices sharing a protocol+model
#      with existing ones)
#
# Known limitation — unstable UID devices (e.g. some door sensors):
#   Some devices produce different house/unit values on every activation
#   due to pulse timing jitter in ProtocolNexa.cpp (house=bits 6-31,
#   unit=bits 0-3 of allData — small timing variations flip bits).
#   telldusd's own DeviceManager.cpp uses exact parameter matching and
#   has the same limitation.  This cannot be fixed at the integration
#   level without access to raw pulse data.  RFXtrx solves a similar
#   problem with user-configurable PT2262 bit masking at firmware level.
#   A future firmware-level fix or raw record/replay feature could help.
# ---------------------------------------------------------------------------

# Seconds to suppress unknown-device events after a known-device event.
# All protocol decodings from a single RF signal arrive within ~100 ms
# (Protocol.cpp decodes sequentially: ProtocolNexa → ProtocolWaveman →
# ProtocolSartano).  1 second gives ample margin.
_KNOWN_DEVICE_SHADOW_SECS = 1.0

# Seconds to suppress cross-protocol phantom discoveries.  telldusd runs
# ALL protocol decoders on every RF signal — identical protocols like
# sartano + x10 both decode the same signal, producing two "new" events
# with different protocol names but the same physical device.  The first
# decode triggers a discovery/auto-add; subsequent decodes within this
# window are suppressed as phantoms.  500 ms is generous (cross-decodes
# arrive within ~100 ms) while short enough to not block a user pressing
# two different buttons in quick succession.
_CROSS_DECODE_WINDOW_SECS = 0.5

# Seconds to defer processing of unknown-device events.  When a door
# sensor fires, telldusd decodes the RF signal as BOTH the real device
# (arctech/selflearning) AND a phantom (sartano/codeswitch).  Previous
# timing-only suppression assumed arctech events always arrived first,
# but event ordering through socat/TCP is not guaranteed.  By deferring
# unknown-event processing, we ensure the known-device event has time
# to set _last_known_event_time before the phantom is evaluated.
# 300 ms is invisible to the user but 3× the ~100 ms cross-decode window.
_PHANTOM_DEFER_SECS = 0.3

# Sensor data-type → suffix (mirrors sensor.py _SENSOR_META keys)
_SENSOR_SUFFIX: dict[int, str] = {
    1: "temperature",
    2: "humidity",
    4: "rain_rate",
    8: "rain_total",
    16: "wind_direction",
    32: "wind_speed",
    64: "wind_gust",
}

_ISSUE_RESTART = "restart_required"
_ISSUE_DEV_CHANNEL = "dev_channel"

# Protocols that are receive-only sensors — telldusd emits TDSensorEvent for
# these (not controllable devices).  Pre-configured app-config entries for these
# protocols are skipped during startup import because they have no house/unit and
# are auto-discovered from RF events instead.
_APP_SENSOR_PROTOCOLS = frozenset({"fineoffset", "oregon", "mandolyn"})


async def _check_version_mismatch(hass: HomeAssistant) -> None:
    """Fire or clear a repair issue based on on-disk manifest vs loaded code.

    The TellStick Local app copies updated integration files to
    ``/config/custom_components/tellstick_local/`` at startup.  If the
    version in the on-disk ``manifest.json`` differs from the compiled-in
    ``INTEGRATION_VERSION``, HA Core must be restarted to load the new code.

    File I/O is offloaded to a thread executor to avoid blocking the event loop.
    """
    disk_manifest = pathlib.Path(__file__).parent / "manifest.json"
    try:
        raw = await hass.async_add_executor_job(disk_manifest.read_text)
        disk_version = json.loads(raw).get("version", "")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError) as exc:
        _LOGGER.debug("Could not read on-disk manifest for version check: %s", exc)
        # Clear any stale issue/notification — if we can't verify a mismatch,
        # assume it's resolved so users don't see stale alerts after restart.
        async_delete_issue(hass, DOMAIN, _ISSUE_RESTART)
        pn_async_dismiss(hass, _ISSUE_RESTART)
        return

    if not disk_version or disk_version == INTEGRATION_VERSION:
        # Versions match — clear any stale repair issue / notification
        async_delete_issue(hass, DOMAIN, _ISSUE_RESTART)
        pn_async_dismiss(hass, _ISSUE_RESTART)
        return

    _LOGGER.warning(
        "TellStick Local integration on disk is v%s but loaded code is v%s — "
        "restart Home Assistant to apply the update",
        disk_version,
        INTEGRATION_VERSION,
    )
    async_create_issue(
        hass,
        DOMAIN,
        _ISSUE_RESTART,
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key=_ISSUE_RESTART,
        translation_placeholders={
            "new_version": disk_version,
            "current_version": INTEGRATION_VERSION,
        },
    )
    pn_async_create(
        hass,
        (
            f"TellStick Local integration **v{disk_version}** has been installed "
            f"(currently loaded: v{INTEGRATION_VERSION}).\n\n"
            "**Restart Home Assistant** to activate the new version.\n\n"
            "Go to **Settings → Developer tools → Restart**."
        ),
        title=f"Restart required — TellStick Local v{disk_version} installed",
        notification_id=_ISSUE_RESTART,
    )


async def _check_dev_channel(hass: HomeAssistant) -> None:
    """Fire or clear a repair issue based on whether this is a dev-channel build.

    The edge.yaml CI workflow writes a ``channel.txt`` file with content ``dev``
    into the bundled integration directory.  Stable builds do not write this
    file.  When present, the integration surfaces a HA repair issue so users
    can easily see they are on the development channel and learn how to switch
    to the stable release.
    """
    channel_file = pathlib.Path(__file__).parent / "channel.txt"
    try:
        content = await hass.async_add_executor_job(channel_file.read_text)
        channel = content.strip().lower()
    except (FileNotFoundError, OSError):
        channel = ""

    if channel == "dev":
        _LOGGER.info(
            "TellStick Local is running on the dev channel "
            "(addon-tellsticklive-roosfork). "
            "Switch to https://github.com/R00S/addon-tellstick-local for stable releases."
        )
        async_create_issue(
            hass,
            DOMAIN,
            _ISSUE_DEV_CHANNEL,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key=_ISSUE_DEV_CHANNEL,
        )
    else:
        async_delete_issue(hass, DOMAIN, _ISSUE_DEV_CHANNEL)


@callback
def _migrate_entry_title(
    hass: HomeAssistant, entry: ConfigEntry, backend: str, host: str
) -> None:
    """Update legacy generic entry titles to hub-specific names.

    Before 2.4.0.3 all entries used 'TellStick Local' / 'TellStick Net (host)'
    as their title.  When both a Duo and a Net/ZNet are configured at the same
    time those titles are indistinguishable in the HA UI, causing users to
    accidentally configure or use the wrong hub.
    """
    title = entry.title
    if backend == BACKEND_NET:
        expected = f"TellStick Net/ZNet ({host})"
        # Old titles: "TellStick Net (host)"
        if title.startswith("TellStick Net") and title != expected:
            hass.config_entries.async_update_entry(entry, title=expected)
    else:
        # Old titles: "TellStick Local" or "TellStick Local (host)"
        if title.startswith("TellStick Local"):
            new_title = (
                f"TellStick Duo ({host})" if "(" in title else "TellStick Duo"
            )
            hass.config_entries.async_update_entry(entry, title=new_title)


@callback
def _clear_orphaned_tombstones(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove stale entity and device registry tombstones at startup.

    Before v2.1.12.2 the options-flow delete paths did not pop tombstones
    after calling async_remove / async_remove_device.  If a user deleted a
    device using those paths on an older version, the tombstone was written to
    disk and survives upgrades.

    What tombstones actually do (verified from HA source):
    - Entity tombstone (DeletedRegistryEntry): on re-add, HA restores the old
      *internal HA UUID* (the ``id`` field) and ``created_at``.  The entity_id
      is always regenerated from ``suggested_object_id`` — not from the
      tombstone — so entity_id inheritance is unaffected.  The risk is that the
      new entity silently reuses the old UUID, which links it to the old
      entity's recorder history.
    - Device tombstone (DeletedDeviceEntry): since HA 2025.6 this stores
      ``area_id``, ``labels``, AND ``name_by_user`` in addition to
      ``config_entries``, ``connections``, ``identifiers``, and the device UUID.
      ``to_device_entry()`` restores all of them on re-add.  This is the direct
      cause of area/label inheritance when a device is deleted and re-added
      (Issue #33, jet001se report).  Clearing the tombstone prevents the old
      area, labels, and name from being resurrected on re-add.

    Clearing both tombstones at startup ensures every re-added device starts
    truly fresh.  Issue #33.
    """
    # --- Entity registry tombstones ---
    ent_reg = er.async_get(hass)
    valid_unique_ids: set[str] = {
        f"{entry.entry_id}_{uid}"
        for uid in entry.options.get(CONF_DEVICES, {})
    }
    orphan_ent_keys = [
        key
        for key, deleted_ent in list(ent_reg.deleted_entities.items())
        if key[1] == DOMAIN  # platform == tellstick_local
        and deleted_ent.config_entry_id == entry.entry_id
        and deleted_ent.unique_id not in valid_unique_ids
    ]
    for key in orphan_ent_keys:
        ent_reg.deleted_entities.pop(key, None)
    if orphan_ent_keys:
        _LOGGER.debug(
            "Cleared %d orphaned entity tombstone(s) for entry %s (Issue #33)",
            len(orphan_ent_keys),
            entry.entry_id,
        )

    # --- Device registry tombstones ---
    dev_reg = dr.async_get(hass)
    orphan_dev_ids = [
        dev_id
        for dev_id, deleted_dev in list(dev_reg.deleted_devices.items())
        if entry.entry_id in deleted_dev.config_entries
    ]
    for dev_id in orphan_dev_ids:
        dev_reg.deleted_devices.pop(dev_id, None)
    if orphan_dev_ids:
        _LOGGER.debug(
            "Cleared %d orphaned device tombstone(s) for entry %s (Issue #33)",
            len(orphan_dev_ids),
            entry.entry_id,
        )


async def _import_app_configured_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    controller: TellStickController,
    device_id_map: dict[str, Any],
) -> None:
    """Import devices pre-configured in the app config but not yet in CONF_DEVICES.

    When a user pastes their device YAML into the app's Configuration tab (HAOS
    YAML mode), those devices are registered with telldusd via ``tellstick.conf``
    but are unknown to the integration.  This function detects such "unmanaged"
    telldusd devices and adds them to CONF_DEVICES before platform setup, so that
    each platform (switch/light/cover) creates the correct entity type based on
    the original model string from the app config.

    Sensor-only protocols (fineoffset, oregon, mandolyn) are skipped — they have
    no house/unit and are auto-discovered from TDSensorEvent instead.

    This restores the "paste YAML → devices appear in HA" workflow from the
    parent repo (erik73/addon-tellsticklive) after migrating to this fork.
    """
    all_devices = await controller.list_devices()

    existing_devices: dict[str, Any] = dict(entry.options.get(CONF_DEVICES, {}))
    ignored_uids: set[str] = set(entry.options.get(CONF_IGNORED_UIDS, {}).keys())

    # Build a lookup of already-managed (protocol, house, unit) tuples so we
    # can skip devices that are managed via the old house/unit format (where
    # the UID key might differ from build_device_uid when models differ).
    managed_params: set[tuple[str, str, str]] = {
        (
            cfg.get(CONF_DEVICE_PROTOCOL, ""),
            cfg.get(CONF_DEVICE_HOUSE, ""),
            cfg.get(CONF_DEVICE_UNIT, ""),
        )
        for cfg in existing_devices.values()
    }

    new_devices: dict[str, dict[str, Any]] = {}
    for dev in all_devices:
        protocol = dev["protocol"]
        house = dev["house"]
        unit = dev["unit"]
        telldusd_id = dev["id"]

        if not protocol:
            continue

        # Sensor-only protocols: auto-discovered from TDSensorEvent, not here.
        if protocol in _APP_SENSOR_PROTOCOLS:
            continue

        # Skip if already managed by protocol+house+unit (covers both UID
        # formats and avoids fetching name/model for known devices).
        if (protocol, house, unit) in managed_params:
            continue

        # Fetch name and model only for candidates to minimise TCP round-trips.
        name, model = await controller.get_device_name_model(telldusd_id)

        uid = build_device_uid(protocol, model, house, unit)

        # Skip if already managed by UID or user-ignored.
        if uid in existing_devices or uid in ignored_uids:
            continue

        # Avoid duplicates when list_devices() returns two entries with the
        # same effective UID (can happen when app config and integration both
        # previously registered the same device).
        if uid in new_devices:
            continue

        new_devices[uid] = {
            CONF_DEVICE_NAME: name or f"TellStick {uid}",
            CONF_DEVICE_PROTOCOL: protocol,
            CONF_DEVICE_MODEL: model,
            CONF_DEVICE_HOUSE: house,
            CONF_DEVICE_UNIT: unit,
            "_telldusd_id": telldusd_id,
        }

    if not new_devices:
        return

    _LOGGER.info(
        "Importing %d device(s) pre-configured in app config: %s",
        len(new_devices),
        list(new_devices.keys()),
    )

    for uid, dev_cfg in new_devices.items():
        existing_devices[uid] = {
            k: v for k, v in dev_cfg.items() if not k.startswith("_")
        }
        device_id_map[uid] = dev_cfg["_telldusd_id"]

    new_options = dict(entry.options)
    new_options[CONF_DEVICES] = existing_devices
    hass.config_entries.async_update_entry(entry, options=new_options)


# ---------------------------------------------------------------------------
# Mirror / range extender helpers
# ---------------------------------------------------------------------------

async def _register_mirror_devices(
    primary_entry: ConfigEntry,
    mirror_backend: str,
    mirror_controller: Any,
) -> dict[str, Any]:
    """Register the primary's devices on a mirror controller.

    Returns a device_id_map for the mirror.  The primary and mirror can be
    different backend types (Duo ↔ Net/ZNet), so the device_id values differ:
    - Duo mirror: integer telldusd IDs (devices registered via add_device)
    - Net mirror: param dicts (protocol/model/house/unit)
    """
    mirror_device_id_map: dict[str, Any] = {}
    stored_devices: dict[str, Any] = primary_entry.options.get(CONF_DEVICES, {})

    for device_uid, device_cfg in stored_devices.items():
        if device_uid.startswith("sensor_"):
            continue

        protocol = device_cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = device_cfg.get(CONF_DEVICE_MODEL, "")
        house = device_cfg.get(CONF_DEVICE_HOUSE, "")
        unit = device_cfg.get(CONF_DEVICE_UNIT, "")
        name = device_cfg.get(CONF_DEVICE_NAME, device_uid)

        if mirror_backend == BACKEND_NET:
            # Net/ZNet mirror: store param dict (no telldusd registration)
            mirror_device_id_map[device_uid] = {
                CONF_DEVICE_PROTOCOL: protocol,
                CONF_DEVICE_MODEL: model,
                CONF_DEVICE_HOUSE: house,
                CONF_DEVICE_UNIT: unit,
            }
        else:
            # Duo mirror: register device with the mirror's telldusd
            try:
                params = device_cfg.get("params")
                if params:
                    telldusd_id = await mirror_controller.add_device(
                        name, protocol, model, params,
                    )
                else:
                    telldusd_id = await mirror_controller.find_or_add_device(
                        name, protocol, model, house, unit,
                    )
                mirror_device_id_map[device_uid] = telldusd_id
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Could not register device %s on mirror telldusd",
                    device_uid,
                    exc_info=True,
                )

    return mirror_device_id_map


async def _register_device_on_mirror(
    mirror: dict[str, Any],
    device_uid: str,
    name: str,
    protocol: str,
    model: str,
    house: str,
    unit: str,
) -> None:
    """Register a single newly-added device on one mirror controller.

    Called when the primary auto-adds or manually adds a device after setup.
    Determines the mirror's backend type by checking the controller type and
    updates the mirror's device_id_map accordingly.
    """
    ctrl = mirror["controller"]
    device_id_map: dict[str, Any] = mirror["device_id_map"]

    # Detect backend from controller type — avoids storing backend string
    # in the mirror_info dict.  TellStickController (Duo) has add_device;
    # TellStickNetController (Net) does not.
    if hasattr(ctrl, "find_or_add_device"):
        # Duo mirror: register with telldusd
        try:
            telldusd_id = await ctrl.find_or_add_device(
                name, protocol, model, house, unit,
            )
            device_id_map[device_uid] = telldusd_id
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Could not register device %s on mirror %s",
                device_uid, mirror.get("entry_id", "?"),
                exc_info=True,
            )
    else:
        # Net/ZNet mirror: store param dict
        device_id_map[device_uid] = {
            CONF_DEVICE_PROTOCOL: protocol,
            CONF_DEVICE_MODEL: model,
            CONF_DEVICE_HOUSE: house,
            CONF_DEVICE_UNIT: unit,
        }


async def _setup_mirror_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    mirror_of: str,
    backend: str,
    controller: Any,
    device_id_map: dict[str, Any],
) -> bool:
    """Set up a mirror/range extender entry.

    A mirror TellStick:
    - Connects its own controller (Duo or Net — can differ from the primary)
    - Registers the primary's devices on its own hardware
    - Forwards received RF events to the primary entry's event handler
    - Does NOT load platforms (no entities of its own)

    The primary and mirror can be different backend types (e.g. a Net/ZNet can
    mirror a Duo and vice versa).
    """
    primary_entry = hass.config_entries.async_get_entry(mirror_of)
    if primary_entry is None:
        _LOGGER.error(
            "Mirror entry %s references primary %s which does not exist",
            entry.entry_id, mirror_of,
        )
        return False

    # Register primary's devices on the mirror's controller
    mirror_device_id_map = await _register_mirror_devices(
        primary_entry, backend, controller,
    )

    # Store minimal runtime data for the mirror entry (needed for unload)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        ENTRY_TELLSTICK_CONTROLLER: controller,
        ENTRY_DEVICE_ID_MAP: mirror_device_id_map,
        "_is_mirror": True,
        "_mirror_of": mirror_of,
    }

    mirror_info: dict[str, Any] = {
        "controller": controller,
        "device_id_map": mirror_device_id_map,
        "entry_id": entry.entry_id,
        "mirror_of": mirror_of,
    }

    # Forward events from the mirror to the primary's event handler,
    # so RF signals received by the mirror also update primary's entities
    # and trigger device discovery.
    @callback
    def _mirror_event_callback(event: Any) -> None:
        if primary_entry.state is ConfigEntryState.LOADED:
            _handle_event(hass, primary_entry, event)

    controller.add_callback(_mirror_event_callback)
    controller.start_event_listener()

    async def _on_hass_stop(_event: Any) -> None:
        await controller.disconnect()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_hass_stop)
    )

    # Register with the primary entry's data so entities can send
    # commands through the mirror.
    primary_data = hass.data.get(DOMAIN, {}).get(mirror_of)
    if primary_data is not None:
        primary_data.setdefault(ENTRY_MIRRORS, []).append(mirror_info)
        _LOGGER.info(
            "Mirror %s (%s) attached to primary %s",
            entry.entry_id, entry.title, primary_entry.title,
        )
    else:
        # Primary not loaded yet — store in a pending list.
        # The primary will pick this up in its own async_setup_entry.
        pending = hass.data.setdefault(DOMAIN, {}).setdefault(
            "_pending_mirrors", []
        )
        pending.append(mirror_info)
        _LOGGER.info(
            "Mirror %s queued (primary %s not yet loaded)",
            entry.entry_id, mirror_of,
        )

    # Mirror entries do NOT load platforms — they have no entities of their own.
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TellStick Local from a config entry."""

    # --- Version-mismatch detection ---
    # INTEGRATION_VERSION is frozen at import time.  If the app copied a
    # newer integration to disk while HA was running, the on-disk
    # manifest.json will have a higher version than the loaded code.
    # In that case we fire a persistent notification so the user knows
    # a restart is needed.
    await _check_version_mismatch(hass)

    # --- Dev-channel detection ---
    # The edge.yaml CI workflow writes channel.txt = "dev" into the bundled
    # integration.  When present, we surface a repair issue so users on the
    # dev channel are clearly informed and shown how to switch to stable.
    await _check_dev_channel(hass)

    # --- One-time tombstone cleanup (Issue #33) ---
    # Clear orphaned entity/device registry tombstones left by deletions
    # performed on versions older than 2.1.12.3 (before tombstone clearing
    # was added to all delete paths).  This is a no-op on clean installs.
    _clear_orphaned_tombstones(hass, entry)

    backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
    host = entry.data[CONF_HOST]
    mirror_of = entry.data.get(CONF_MIRROR_OF)

    # --- One-time title migration ---
    # Older versions used generic titles ("TellStick Local", "TellStick Local (host)",
    # "TellStick Net (host)").  Migrate to hub-specific titles so users can
    # immediately tell which entry controls which hardware, especially important
    # when both a Duo and a Net/ZNet are configured simultaneously.
    if not mirror_of:
        _migrate_entry_title(hass, entry, backend, host)

    if backend == BACKEND_NET:
        # --- TellStick Net / ZNet UDP backend ---
        from .net_client import TellStickNetController  # noqa: PLC0415

        mac = entry.data.get("mac", "")
        controller: Any = TellStickNetController(host=host, mac=mac)
        try:
            await asyncio.wait_for(controller.connect(), timeout=10)
        except (asyncio.TimeoutError, OSError) as err:
            _LOGGER.error(
                "Cannot connect to TellStick Net at %s: %s", host, err
            )
            return False

        # For Net, populate device_id_map with device parameter dicts.
        # The Net controller has no telldusd registry; commands are sent
        # directly using the stored protocol/model/house/unit.
        device_id_map: dict[str, Any] = {}
        stored_devices: dict[str, Any] = entry.options.get(CONF_DEVICES, {})
        for device_uid, device_cfg in stored_devices.items():
            if device_uid.startswith("sensor_"):
                continue
            device_id_map[device_uid] = {
                CONF_DEVICE_PROTOCOL: device_cfg.get(CONF_DEVICE_PROTOCOL, ""),
                CONF_DEVICE_MODEL: device_cfg.get(CONF_DEVICE_MODEL, ""),
                CONF_DEVICE_HOUSE: device_cfg.get(CONF_DEVICE_HOUSE, ""),
                CONF_DEVICE_UNIT: device_cfg.get(CONF_DEVICE_UNIT, ""),
            }
        # Net does not use _import_app_configured_devices
        do_app_import = False

    else:
        # --- TellStick Duo TCP backend (default) ---
        cmd_port = entry.data[CONF_COMMAND_PORT]
        evt_port = entry.data[CONF_EVENT_PORT]

        controller = TellStickController(
            host=host, command_port=cmd_port, event_port=evt_port
        )

        try:
            await asyncio.wait_for(controller.connect(), timeout=10)
        except (asyncio.TimeoutError, OSError) as err:
            _LOGGER.error(
                "Cannot connect to TellStick daemon at %s: %s", host, err
            )
            return False

        # Re-register stored devices with telldusd.  telldusd's device list is
        # ephemeral (reset when the app container restarts), so we must do this
        # on every setup.  find_or_add_device avoids duplicates on warm reconnects.
        device_id_map = {}
        stored_devices = entry.options.get(CONF_DEVICES, {})
        for device_uid, device_cfg in stored_devices.items():
            # Skip sensor entries — they don't register with telldusd
            if device_uid.startswith("sensor_"):
                continue
            try:
                # Prefer the "params" dict (new format) over house/unit (old format)
                params = device_cfg.get("params")
                if params:
                    telldusd_id = await controller.add_device(
                        device_cfg.get(CONF_DEVICE_NAME, device_uid),
                        device_cfg[CONF_DEVICE_PROTOCOL],
                        device_cfg.get(CONF_DEVICE_MODEL, ""),
                        params,
                    )
                else:
                    telldusd_id = await controller.find_or_add_device(
                        device_cfg.get(CONF_DEVICE_NAME, device_uid),
                        device_cfg[CONF_DEVICE_PROTOCOL],
                        device_cfg.get(CONF_DEVICE_MODEL, ""),
                        device_cfg.get(CONF_DEVICE_HOUSE, ""),
                        device_cfg.get(CONF_DEVICE_UNIT, ""),
                    )
                device_id_map[device_uid] = telldusd_id
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Could not register device %s with telldusd: %s", device_uid, err
                )
        do_app_import = True

    # ------------------------------------------------------------------
    # Mirror / range extender entry — register with primary and return
    # ------------------------------------------------------------------
    if mirror_of:
        return await _setup_mirror_entry(
            hass, entry, mirror_of, backend, controller, device_id_map
        )

    # Clean up orphan subentry records left by older versions of the
    # integration.  We no longer create subentries because they cause the
    # HA frontend to show a confusing "Devices that don't belong in a
    # sub-entry" grouping for auto-detected devices.
    if hasattr(entry, "subentries") and entry.subentries:
        for subentry_id in list(entry.subentries):
            try:
                hass.config_entries.async_remove_subentry(entry, subentry_id)
            except (AttributeError, TypeError):
                _LOGGER.debug("Could not remove orphan subentry %s", subentry_id)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        ENTRY_TELLSTICK_CONTROLLER: controller,
        ENTRY_DEVICE_ID_MAP: device_id_map,
        ENTRY_MIRRORS: [],
        # Track UIDs for which discovery flows have been fired this session
        # to avoid flooding the UI with duplicate notifications.
        "_discovered_uids": set(),
        # Track protocol+model pairs already discovered this session.
        # telldusd fires ALL protocol decoders on every RF signal, and some
        # devices (e.g. door sensors) decode with different house/unit values
        # on each transmission.  TelldusCenter (filtereddeviceproxymodel.cpp)
        # solves this by deduplicating on protocol+model — we do the same.
        # NOT pre-seeded from stored devices — that would block new devices
        # that share a protocol+model with existing ones.
        "_discovered_protocol_models": set(),
        # Timestamp of the last known-device raw event.  Used to suppress
        # false-positive unknown events from the same RF signal.
        # Protocol.cpp decodes arctech first (ProtocolNexa → ProtocolWaveman
        # → ProtocolSartano), so known-device events always arrive before
        # their cross-protocol false positives.
        "_last_known_event_time": 0.0,
        # Timestamp of the last discovery/auto-add event that was actually
        # fired (not suppressed).  Used to suppress cross-protocol phantom
        # discoveries: sartano+x10 decode the same RF signal, but only the
        # first decode should trigger a discovery.  Issue #33.
        "_last_discovery_fire_time": 0.0,
    }

    @callback
    def _event_callback(event: Any) -> None:
        _handle_event(hass, entry, event)

    controller.add_callback(_event_callback)
    controller.start_event_listener()

    async def _on_hass_stop(_event: Any) -> None:
        await controller.disconnect()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_hass_stop)
    )

    # Listen for options changes (reload only when automatic_add changes)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Import devices pre-configured in the app's YAML config (Configuration tab)
    # that are not yet known to the integration.  Duo-only — the Net backend
    # has no telldusd registry and no app config tab.
    # Must run BEFORE platform setup so platforms see the imported devices in
    # CONF_DEVICES and create entities with the correct type (switch/light/cover)
    # from the original model string.
    # Wrapped in a broad try/except — this is a bonus hook-on and must never
    # interfere with the existing setup flow.
    if do_app_import:
        try:
            await _import_app_configured_devices(
                hass, entry, controller, device_id_map
            )
        except Exception as _import_err:  # noqa: BLE001
            _LOGGER.warning(
                "App-config device import skipped due to error (setup continues): %s",
                _import_err,
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Attach any mirror entries that loaded before this primary.
    # Mirror entries store themselves in _pending_mirrors when their
    # primary isn't ready yet; we pick them up here.
    pending: list[dict[str, Any]] = (
        hass.data.get(DOMAIN, {}).pop("_pending_mirrors", [])
    )
    primary_data = hass.data[DOMAIN][entry.entry_id]
    for mirror_info in pending:
        if mirror_info["mirror_of"] == entry.entry_id:
            primary_data[ENTRY_MIRRORS].append(mirror_info)
            _LOGGER.info(
                "Attached pending mirror %s to primary %s",
                mirror_info["entry_id"],
                entry.entry_id,
            )

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the integration only when the automatic_add toggle changes."""
    # We read the current automatic_add from entry.options.  On initial setup
    # it defaults to True.  When the user toggles it via the options flow, the
    # option changes and we must reload so the event handler picks up the new
    # value.  Device additions/edits must NOT trigger a reload — they use
    # signals to create entities on the fly.
    pass  # No reload needed — options are read live from entry.options


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    is_mirror = entry_data.get("_is_mirror", False)

    if is_mirror:
        # Mirror entry: disconnect controller, remove from primary's mirrors list
        mirror_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        ctrl: Any = mirror_data.get(ENTRY_TELLSTICK_CONTROLLER)
        if ctrl:
            await ctrl.disconnect()
        # Remove from primary's mirror list
        mirror_of = mirror_data.get("_mirror_of", "")
        primary_data = hass.data.get(DOMAIN, {}).get(mirror_of, {})
        mirrors: list[dict[str, Any]] = primary_data.get(ENTRY_MIRRORS, [])
        primary_data[ENTRY_MIRRORS] = [
            m for m in mirrors if m.get("entry_id") != entry.entry_id
        ]
        return True

    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        ctrl = entry_data.get(ENTRY_TELLSTICK_CONTROLLER)
        if ctrl:
            await ctrl.disconnect()
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear runtime dedup state when a natively-ignored discovery entry is removed.

    When the user clicks the HA-native "Ignore" button on a pending integration
    discovery flow, HA creates a separate config entry with source=SOURCE_IGNORE
    and unique_id="rf_{device_uid}".  When they later un-ignore the device from
    the tile in Settings → Devices & Services, HA removes that entry and calls
    this hook.  We clear the UID from the in-memory deduplication sets so the
    device can be re-discovered the next time it sends an RF signal — without
    requiring an integration reload.

    NOTE: This function is called for ALL entries being removed for this domain,
    including the main hub entry.  We guard on source == SOURCE_IGNORE and
    unique_id prefix "rf_" so we only act on our own discovery-ignored entries.
    """
    if entry.source != SOURCE_IGNORE:
        return

    unique_id = entry.unique_id or ""
    if not unique_id.startswith("rf_"):
        return

    device_uid = unique_id[3:]  # strip the "rf_" prefix we add in the flow

    for entry_data in hass.data.get(DOMAIN, {}).values():
        if not isinstance(entry_data, dict):
            continue
        discovered: set[str] = entry_data.get("_discovered_uids", set())
        discovered.discard(device_uid)

        # Also clear the protocol+model deduplication key so the next RF signal
        # from this device is not silently swallowed.  Sensor UIDs use a
        # different code path and do not participate in proto_model dedup.
        if not device_uid.startswith("sensor_"):
            seen_proto_models: set[str] = entry_data.get(
                "_discovered_protocol_models", set()
            )
            parts = device_uid.split("_", 2)
            if len(parts) >= 2:
                seen_proto_models.discard(f"{parts[0]}_{parts[1]}")


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a device from the integration (called from device page delete)."""
    # Extract device UID from the device registry identifiers
    device_uid: str | None = None
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            # identifier is (DOMAIN, "{entry_id}_{device_uid}")
            prefix = f"{entry.entry_id}_"
            if identifier[1].startswith(prefix):
                device_uid = identifier[1][len(prefix):]
            break

    if device_uid is None:
        return True

    # Best-effort removal from telldusd
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    controller: Any = entry_data.get(ENTRY_TELLSTICK_CONTROLLER)
    device_id_map: dict[str, Any] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
    discovered: set[str] = entry_data.get("_discovered_uids", set())

    # Sensor devices use identifier "sensor_{sensor_id}" (no type suffix).
    # Stored entries are "sensor_{sensor_id}_temperature" / "_humidity".
    # Find and remove ALL matching entries.
    stored_devices: dict[str, Any] = dict(entry.options.get(CONF_DEVICES, {}))
    removed_any = False
    removed_uids: list[str] = []

    if device_uid.startswith("sensor_") and device_uid in stored_devices:
        # Exact match (unlikely — sensors use sensor_{id} without suffix)
        del stored_devices[device_uid]
        removed_any = True
        removed_uids.append(device_uid)
        discovered.discard(device_uid)
    elif device_uid.startswith("sensor_"):
        # Shared identifier format: sensor_{sensor_id}
        # Remove all entries: sensor_{id}_temperature, sensor_{id}_humidity, etc.
        sensor_prefix = f"{device_uid}_"
        for uid in list(stored_devices.keys()):
            if uid.startswith(sensor_prefix):
                del stored_devices[uid]
                removed_any = True
                removed_uids.append(uid)
                discovered.discard(uid)
                # Remove from telldusd map
                if controller and uid in device_id_map:
                    try:
                        await controller.remove_device(device_id_map[uid])
                    except Exception:  # noqa: BLE001
                        _LOGGER.warning(
                            "Could not remove %s from telldusd", uid
                        )
                    device_id_map.pop(uid, None)
        # Also clear the per-sensor-id dedup key so re-discovery can fire
        # if automatic_add is off.  UID format for dedup key: sensor_{id}.
        discovered.discard(device_uid)
    elif device_uid in stored_devices:
        # Non-sensor device: exact UID match
        del stored_devices[device_uid]
        removed_any = True
        removed_uids.append(device_uid)
        discovered.discard(device_uid)
        if controller and device_uid in device_id_map:
            try:
                await controller.remove_device(device_id_map[device_uid])
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Could not remove device %s from telldusd", device_uid
                )
            device_id_map.pop(device_uid, None)

    if removed_any:
        new_options = dict(entry.options)
        new_options[CONF_DEVICES] = stored_devices
        hass.config_entries.async_update_entry(entry, options=new_options)

        # Remove entity registry entries so that if the same device is later
        # re-added with a new name it gets fresh entity_ids instead of
        # inheriting the old ones.  Issue #33.
        ent_reg = er.async_get(hass)
        remove_unique_ids = {f"{entry.entry_id}_{u}" for u in removed_uids}
        for ent in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
            if ent.unique_id in remove_unique_ids:
                try:
                    ent_reg.async_remove(ent.entity_id)
                    # Clear the DeletedRegistryEntry tombstone so that the old
                    # entity UUID is not silently reused when the device is
                    # re-added, which would link the new entity to the old
                    # entity's recorder history.  Issue #33.
                    ent_reg.deleted_entities.pop(
                        (ent.domain, ent.platform, ent.unique_id), None
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "Could not remove entity %s from registry",
                        ent.entity_id,
                    )

    # Schedule device registry tombstone clearing AFTER HA removes the device.
    # When this function returns True, HA calls
    # async_update_device(device.id, remove_config_entry_id=entry.entry_id)
    # which (since we have only one config entry per device) calls
    # async_remove_device() — moving the device to deleted_devices.
    # We schedule a task to pop the tombstone so the old area, labels, and
    # name_by_user are not resurrected on re-add (HA 2025.6+ stores these in
    # DeletedDeviceEntry and to_device_entry() restores them).
    #
    # No race condition: async_create_task schedules a new asyncio Task that
    # cannot start until the current coroutine returns and the caller's
    # synchronous @callback (async_update_device → async_remove_device) has
    # already completed.  The tombstone is guaranteed to exist by the time the
    # task runs.  Issue #33.
    _dev_entry_id = device_entry.id

    async def _clear_device_tombstone() -> None:
        dev_reg = dr.async_get(hass)
        dev_reg.deleted_devices.pop(_dev_entry_id, None)

    hass.async_create_task(_clear_device_tombstone())

    return True


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------

def _handle_event(
    hass: HomeAssistant,
    entry: ConfigEntry,
    event: Any,
) -> None:
    """Dispatch an incoming telldusd event."""
    if isinstance(event, RawDeviceEvent):
        _handle_raw_event(hass, entry, event)
    elif isinstance(event, DeviceEvent):
        _handle_device_event(hass, entry, event)
    elif isinstance(event, SensorEvent):
        _handle_sensor_event(hass, entry, event)


def _handle_raw_event(
    hass: HomeAssistant,
    entry: ConfigEntry,
    event: RawDeviceEvent,
) -> None:
    """Handle a raw RF device event.

    Known devices → update entity state + revive after restart.
    Unknown devices → fire a discovery config flow (BLE-like UX).
    """
    params = event.params
    device_uid = event.device_id
    if not device_uid:
        return

    # Sensor protocols (fineoffset, oregon, mandolyn) emit TDRawDeviceEvent
    # with class:sensor AND a separate TDSensorEvent.  The raw event carries
    # no house/unit, so device_uid is just "fineoffset_temperaturehumidity" —
    # adding it produces an empty device with no entities.  Sensor data is
    # handled exclusively by _handle_sensor_event; bail out here.
    if params.get("class") == "sensor":
        return

    _LOGGER.debug("Raw RF event from %s: %s", device_uid, params)

    # Broadcast for entity listeners (state updates for existing entities)
    async_dispatcher_send(hass, SIGNAL_EVENT.format(entry.entry_id), event)

    # Fire an HA bus event so device triggers (automations) can listen
    method = params.get("method", "")
    if method in ("turnon", "turnoff"):
        hass.bus.async_fire(
            f"{DOMAIN}_event",
            {
                "device_uid": device_uid,
                "type": "turned_on" if method == "turnon" else "turned_off",
            },
        )

    stored_devices = entry.options.get(CONF_DEVICES, {})
    automatic_add = entry.options.get(CONF_AUTOMATIC_ADD, DEFAULT_AUTOMATIC_ADD)

    if device_uid in stored_devices:
        # Known device — record timestamp so we can suppress false-positive
        # unknown events from the same RF signal (they arrive within ms).
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        entry_data["_last_known_event_time"] = time.monotonic()
        # Fire SIGNAL_NEW_DEVICE so platforms can revive entities after a
        # restart (the entity is pre-created from stored config, but the
        # signal lets late-starting platforms pick it up).
        async_dispatcher_send(
            hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), event
        )
    else:
        # Unknown device — defer processing to allow known-device events
        # from the same RF signal to arrive first and set the timestamp.
        # Without deferral, phantoms like sartano/codeswitch slip through
        # when they arrive before the real arctech event.  Issue #33.
        hass.loop.call_later(
            _PHANTOM_DEFER_SECS,
            _process_unknown_event,
            hass, entry, device_uid, params, event, automatic_add,
        )


@callback
def _process_unknown_event(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_uid: str,
    params: dict[str, str],
    event: RawDeviceEvent,
    automatic_add: bool,
) -> None:
    """Process an unknown-device event after a short deferral.

    Called by ``loop.call_later`` so that known-device events from the
    same RF signal have time to set ``_last_known_event_time``.
    """
    # Guard: integration may have been unloaded during the delay.
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data is None:
        return

    # Sartano/codeswitch opt-in: skip auto-detection of sartano protocol
    # unless the user has explicitly enabled it.  telldusd cross-decodes
    # arctech signals as sartano phantoms; this is the simplest workaround.
    protocol = params.get("protocol", "")
    if protocol == "sartano":
        detect_sartano = entry.options.get(
            CONF_DETECT_SARTANO, DEFAULT_DETECT_SARTANO
        )
        if not detect_sartano:
            _LOGGER.debug(
                "Ignoring sartano event %s (detect_sartano is off)", device_uid
            )
            return

    if automatic_add:
        _auto_add_device(hass, entry, device_uid, params, event)
    else:
        _fire_device_discovery(hass, entry, device_uid, params)


def _fire_device_discovery(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_uid: str,
    params: dict[str, str],
) -> None:
    """Fire an integration_discovery config flow for a new 433 MHz device."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    discovered: set[str] = entry_data.get("_discovered_uids", set())

    if device_uid in discovered:
        return  # Already fired a discovery for this device this session

    # Skip permanently ignored devices
    ignored_uids = entry.options.get(CONF_IGNORED_UIDS, {})
    if device_uid in ignored_uids:
        discovered.add(device_uid)
        return

    # Suppress false positives from a known device's RF signal.
    # Protocol.cpp decodes arctech first, so the known-device event
    # (if any) has already been processed and set the timestamp.
    last_known = entry_data.get("_last_known_event_time", 0.0)
    now = time.monotonic()
    if now - last_known < _KNOWN_DEVICE_SHADOW_SECS:
        discovered.add(device_uid)
        return

    # Suppress cross-protocol phantom discoveries.  Identical protocols
    # (e.g. sartano + x10) decode the same RF signal with different
    # protocol names.  The first decode triggers a discovery; subsequent
    # decodes within the window are phantoms.  Issue #33.
    last_fire = entry_data.get("_last_discovery_fire_time", 0.0)
    if now - last_fire < _CROSS_DECODE_WINDOW_SECS:
        discovered.add(device_uid)
        return

    # Deduplicate by protocol+model, matching TelldusCenter's approach
    # (filtereddeviceproxymodel.cpp:60-70).  telldusd fires ALL protocol
    # decoders on every RF signal, and some devices decode with different
    # house/unit values on each transmission.  We only fire one discovery
    # flow per unique protocol+model combination.
    protocol = params.get("protocol", "")
    model = params.get("model", "")
    proto_model_key = f"{protocol}_{model}"
    seen_proto_models: set[str] = entry_data["_discovered_protocol_models"]
    if proto_model_key in seen_proto_models:
        discovered.add(device_uid)
        # Still update fire time so cross-decode phantoms from this RF
        # signal are suppressed (e.g. sartano from an arctech signal).
        entry_data["_last_discovery_fire_time"] = now
        return
    seen_proto_models.add(proto_model_key)

    discovered.add(device_uid)
    entry_data["_last_discovery_fire_time"] = now
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "integration_discovery"},
            data={
                "device_uid": device_uid,
                "protocol": protocol,
                "model": model,
                "house": params.get("house", ""),
                "unit": params.get("unit", params.get("code", "")),
                "entry_id": entry.entry_id,
                "type": "device",
            },
        )
    )


def _auto_add_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_uid: str,
    params: dict[str, str],
    event: RawDeviceEvent,
) -> None:
    """Auto-add a new device: persist in options, register with telldusd, fire signal."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    discovered: set[str] = entry_data.get("_discovered_uids", set())
    if device_uid in discovered:
        return
    discovered.add(device_uid)

    # Skip permanently ignored devices
    ignored_uids = entry.options.get(CONF_IGNORED_UIDS, {})
    if device_uid in ignored_uids:
        return

    # Suppress false positives from a known device's RF signal.
    last_known = entry_data.get("_last_known_event_time", 0.0)
    now = time.monotonic()
    if now - last_known < _KNOWN_DEVICE_SHADOW_SECS:
        return

    # Suppress cross-protocol phantoms (same RF signal decoded as
    # different protocols, e.g. sartano + x10).  Issue #33.
    last_fire = entry_data.get("_last_discovery_fire_time", 0.0)
    if now - last_fire < _CROSS_DECODE_WINDOW_SECS:
        return

    protocol = params.get("protocol", "")
    model = params.get("model", "")

    # Deduplicate by protocol+model, matching TelldusCenter's approach
    # (filtereddeviceproxymodel.cpp:60-70).  Only auto-add the first
    # event for each protocol+model combination per session.
    proto_model_key = f"{protocol}_{model}"
    seen_proto_models: set[str] = entry_data["_discovered_protocol_models"]
    if proto_model_key in seen_proto_models:
        # Still update fire time so cross-decode phantoms from this RF
        # signal are suppressed (e.g. sartano from an arctech signal).
        entry_data["_last_discovery_fire_time"] = now
        return
    seen_proto_models.add(proto_model_key)

    house = params.get("house", "")
    unit = params.get("unit", params.get("code", ""))
    name = f"TellStick {device_uid}"

    entry_data["_last_discovery_fire_time"] = now

    # Persist immediately
    existing_devices = dict(entry.options.get(CONF_DEVICES, {}))
    existing_devices[device_uid] = {
        CONF_DEVICE_NAME: name,
        CONF_DEVICE_PROTOCOL: protocol,
        CONF_DEVICE_MODEL: model,
        CONF_DEVICE_HOUSE: house,
        CONF_DEVICE_UNIT: unit,
    }
    new_options = dict(entry.options)
    new_options[CONF_DEVICES] = existing_devices
    hass.config_entries.async_update_entry(entry, options=new_options)

    # Register with telldusd and store ID so commands work
    async def _register_and_signal() -> None:
        controller: Any = entry_data.get(ENTRY_TELLSTICK_CONTROLLER)
        device_id_map: dict[str, Any] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
        if controller:
            backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
            if backend == BACKEND_NET:
                # Net controller: store device params dict so commands work
                device_id_map[device_uid] = {
                    CONF_DEVICE_PROTOCOL: protocol,
                    CONF_DEVICE_MODEL: model,
                    CONF_DEVICE_HOUSE: house,
                    CONF_DEVICE_UNIT: unit,
                }
            else:
                try:
                    telldusd_id = await controller.find_or_add_device(
                        name, protocol, model, house, unit,
                    )
                    device_id_map[device_uid] = telldusd_id
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "Could not register auto-added device %s with telldusd",
                        device_uid,
                    )
        # Register on all mirror controllers too
        for mirror in entry_data.get(ENTRY_MIRRORS, []):
            await _register_device_on_mirror(
                mirror, device_uid, name, protocol, model, house, unit,
            )
        async_dispatcher_send(
            hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), event
        )

    hass.async_create_task(_register_and_signal())


def _handle_device_event(
    hass: HomeAssistant,
    entry: ConfigEntry,
    event: DeviceEvent,
) -> None:
    """Handle a named-device state-change event."""
    _LOGGER.debug(
        "Device event: id=%s method=%s value=%s",
        event.device_id,
        event.method,
        event.value,
    )
    async_dispatcher_send(hass, SIGNAL_EVENT.format(entry.entry_id), event)


def _handle_sensor_event(
    hass: HomeAssistant,
    entry: ConfigEntry,
    event: SensorEvent,
) -> None:
    """Handle a sensor reading event."""
    _LOGGER.debug(
        "Sensor event: id=%s protocol=%s model=%s type=%s value=%s",
        event.sensor_id,
        event.protocol,
        event.model,
        event.data_type,
        event.value,
    )
    async_dispatcher_send(hass, SIGNAL_EVENT.format(entry.entry_id), event)

    # Check if this sensor is already stored (known)
    stored_devices = entry.options.get(CONF_DEVICES, {})
    automatic_add = entry.options.get(CONF_AUTOMATIC_ADD, DEFAULT_AUTOMATIC_ADD)
    suffix = _SENSOR_SUFFIX.get(event.data_type)
    sensor_prefix = f"sensor_{event.sensor_id}_"
    is_known = any(uid.startswith(sensor_prefix) for uid in stored_devices)

    if is_known:
        # Auto-persist this data_type if not already stored.  After a
        # migration or add-as-new for one data_type, the companion
        # (temp↔hum) arrives later and must also be persisted so it
        # survives restarts.  Issue #33.
        # IMPORTANT: do this BEFORE dispatching SIGNAL_NEW_DEVICE so that
        # when sensor.py._async_new_device runs it can read the correct
        # user-provided name from entry.options (not the default fallback).
        if suffix:
            sensor_uid = f"sensor_{event.sensor_id}_{suffix}"
            if sensor_uid not in stored_devices:
                # Derive device name from existing companion entry
                base_name = ""
                for uid, cfg in stored_devices.items():
                    if uid.startswith(sensor_prefix):
                        base_name = cfg.get(CONF_DEVICE_NAME, "")
                        break
                for s in _SENSOR_SUFFIX.values():
                    if base_name.lower().endswith(f" {s}"):
                        base_name = base_name[: -(len(s) + 1)]
                        break
                if not base_name:
                    base_name = f"TellStick sensor {event.sensor_id}"
                existing_devices = dict(stored_devices)
                existing_devices[sensor_uid] = {
                    CONF_DEVICE_NAME: f"{base_name} {suffix}",
                    CONF_DEVICE_PROTOCOL: event.protocol or "",
                    CONF_DEVICE_MODEL: event.model or "",
                    "sensor_id": event.sensor_id,
                    "data_type": event.data_type,
                }
                new_options = dict(entry.options)
                new_options[CONF_DEVICES] = existing_devices
                hass.config_entries.async_update_entry(
                    entry, options=new_options
                )
        # Known sensor — revive entity after restart
        async_dispatcher_send(
            hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), event
        )
    elif suffix and automatic_add:
        # Auto-add: persist sensor and fire signal
        sensor_uid = f"sensor_{event.sensor_id}_{suffix}"
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        discovered: set[str] = entry_data.get("_discovered_uids", set())
        ignored_uids = entry.options.get(CONF_IGNORED_UIDS, {})
        if sensor_uid not in discovered and sensor_uid not in ignored_uids:
            discovered.add(sensor_uid)
            existing_devices = dict(stored_devices)
            existing_devices[sensor_uid] = {
                CONF_DEVICE_NAME: f"TellStick sensor {event.sensor_id} {suffix}",
                CONF_DEVICE_PROTOCOL: event.protocol or "",
                CONF_DEVICE_MODEL: event.model or "",
                "sensor_id": event.sensor_id,
                "data_type": event.data_type,
            }
            new_options = dict(entry.options)
            new_options[CONF_DEVICES] = existing_devices
            hass.config_entries.async_update_entry(entry, options=new_options)
            async_dispatcher_send(
                hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), event
            )
    elif suffix:
        # Unknown sensor — fire a discovery config flow.
        # Deduplicate by sensor_id (not by individual data_type) so
        # only ONE discovery flow fires per physical sensor.  A temp+hum
        # sensor sends separate events for each type; without this,
        # the user sees two "Add" entries for the same sensor.  Issue #33.
        sensor_dedup = f"sensor_{event.sensor_id}"
        sensor_uid = f"sensor_{event.sensor_id}_{suffix}"
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        discovered: set[str] = entry_data.get("_discovered_uids", set())
        ignored_uids = entry.options.get(CONF_IGNORED_UIDS, {})
        if (
            sensor_dedup not in discovered
            and sensor_uid not in ignored_uids
        ):
            discovered.add(sensor_dedup)
            discovered.add(sensor_uid)
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "integration_discovery"},
                    data={
                        "device_uid": sensor_uid,
                        "protocol": event.protocol or "",
                        "model": event.model or "",
                        "sensor_id": event.sensor_id,
                        "data_type": event.data_type,
                        "entry_id": entry.entry_id,
                        "type": "sensor",
                    },
                )
            )
