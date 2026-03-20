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
from homeassistant.config_entries import SOURCE_IGNORE, ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import (
    DeviceEvent,
    RawDeviceEvent,
    SensorEvent,
    TellStickController,
)
from .const import (
    CONF_AUTOMATIC_ADD,
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
    DEFAULT_AUTOMATIC_ADD,
    DEFAULT_DETECT_SARTANO,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    INTEGRATION_VERSION,
    PLATFORMS,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
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
    # PARKED: Still no repair issue. No more dev time must be spent on this until
    # copilot agents have fixed these issues:
    #   - agents guessing instead of doing research
    #   - agents reimplementing already failed code
    #   - agents not reading prompts
    #   - agents taking shortcuts to shortsightedly save tokens, creating a lot more
    #     load by failing
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TellStick Local from a config entry."""

    # --- Version-mismatch detection ---
    # INTEGRATION_VERSION is frozen at import time.  If the app copied a
    # newer integration to disk while HA was running, the on-disk
    # manifest.json will have a higher version than the loaded code.
    # In that case we fire a persistent notification so the user knows
    # a restart is needed.
    await _check_version_mismatch(hass)

    host = entry.data[CONF_HOST]
    cmd_port = entry.data[CONF_COMMAND_PORT]
    evt_port = entry.data[CONF_EVENT_PORT]

    controller = TellStickController(
        host=host, command_port=cmd_port, event_port=evt_port
    )

    try:
        await asyncio.wait_for(controller.connect(), timeout=10)
    except (asyncio.TimeoutError, OSError) as err:
        _LOGGER.error("Cannot connect to TellStick daemon at %s: %s", host, err)
        return False

    # Re-register stored devices with telldusd.  telldusd's device list is
    # ephemeral (reset when the app container restarts), so we must do this on
    # every setup.  find_or_add_device avoids duplicates on warm reconnects.
    device_id_map: dict[str, int] = {}
    stored_devices: dict[str, Any] = entry.options.get(CONF_DEVICES, {})
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        ctrl: TellStickController | None = entry_data.get(ENTRY_TELLSTICK_CONTROLLER)
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
    controller: TellStickController | None = entry_data.get(
        ENTRY_TELLSTICK_CONTROLLER
    )
    device_id_map: dict[str, int] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
    discovered: set[str] = entry_data.get("_discovered_uids", set())

    # Sensor devices use identifier "sensor_{sensor_id}" (no type suffix).
    # Stored entries are "sensor_{sensor_id}_temperature" / "_humidity".
    # Find and remove ALL matching entries.
    stored_devices: dict[str, Any] = dict(entry.options.get(CONF_DEVICES, {}))
    removed_any = False

    if device_uid.startswith("sensor_") and device_uid in stored_devices:
        # Exact match (unlikely — sensors use sensor_{id} without suffix)
        del stored_devices[device_uid]
        removed_any = True
        discovered.discard(device_uid)
    elif device_uid.startswith("sensor_"):
        # Shared identifier format: sensor_{sensor_id}
        # Remove all entries: sensor_{id}_temperature, sensor_{id}_humidity, etc.
        sensor_prefix = f"{device_uid}_"
        for uid in list(stored_devices.keys()):
            if uid.startswith(sensor_prefix):
                del stored_devices[uid]
                removed_any = True
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
        controller: TellStickController | None = entry_data.get(
            ENTRY_TELLSTICK_CONTROLLER
        )
        device_id_map: dict[str, int] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
        if controller:
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
        # Known sensor — revive entity after restart
        async_dispatcher_send(
            hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), event
        )
        # Auto-persist this data_type if not already stored.  After a
        # migration or add-as-new for one data_type, the companion
        # (temp↔hum) arrives later and must also be persisted so it
        # survives restarts.  Issue #33.
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
