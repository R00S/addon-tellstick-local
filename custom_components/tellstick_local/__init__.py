"""TellStick Local integration – hub setup and event dispatch."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
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
    CONF_DEVICE_HOUSE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    CONF_EVENT_PORT,
    DEFAULT_AUTOMATIC_ADD,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    PLATFORMS,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
)

_LOGGER = logging.getLogger(__name__)

# Seconds to suppress unknown-device events after a known-device event.
# All protocol decodings from a single RF signal arrive within ~100 ms
# (Protocol.cpp decodes sequentially: ProtocolNexa → ProtocolWaveman →
# ProtocolSartano).  1 second gives ample margin.
_KNOWN_DEVICE_SHADOW_SECS = 1.0

# Seconds to suppress duplicate protocol+model discoveries.
# Door sensors decode with different house/unit each time → rapid noise.
# Remotes like SYS2000 Proove have different buttons (same protocol+model,
# different house/unit) that the user presses seconds apart.
# 5 seconds is long enough to suppress door-sensor noise but short enough
# to let a user discover multiple buttons on a remote.
_PROTO_MODEL_COOLDOWN_SECS = 5.0

# Sensor data-type → suffix (mirrors sensor.py _SENSOR_META keys)
_SENSOR_SUFFIX: dict[int, str] = {1: "temperature", 2: "humidity"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TellStick Local from a config entry."""
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
        # Track protocol+model pairs with timestamps for time-limited dedup.
        # Suppresses same protocol+model within _PROTO_MODEL_COOLDOWN_SECS.
        "_discovered_protocol_models": {},  # dict[str, float] → timestamp
        # Track all UIDs seen per protocol+model key.  Used to detect whether
        # a protocol+model produces stable UIDs (same button = same UID, like
        # SYS2000 Proove) or unstable UIDs (different house/unit every time,
        # like some door sensors decoded through arctech).
        "_proto_model_uids": {},  # dict[str, set[str]]
        # True once a protocol+model has been "confirmed stable" — i.e. the
        # same UID was seen twice.  Stable protocol+models are allowed to
        # discover multiple UIDs (different buttons).  Unconfirmed ones are
        # blocked after the first discovery to prevent device flooding.
        "_proto_model_confirmed": {},  # dict[str, bool]
        # Timestamp of the last event from a known OR just-discovered device.
        # Used to suppress cross-protocol false positives from the same RF
        # signal.  Protocol.cpp decodes arctech first (ProtocolNexa →
        # ProtocolWaveman → ProtocolSartano), so the primary event always
        # arrives before its false positives.
        "_last_known_event_time": 0.0,
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
    if controller and device_uid in device_id_map:
        try:
            await controller.remove_device(device_id_map[device_uid])
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Could not remove device %s from telldusd", device_uid
            )
        device_id_map.pop(device_uid, None)

    # Remove from stored devices if present
    stored_devices: dict[str, Any] = dict(entry.options.get(CONF_DEVICES, {}))
    if device_uid in stored_devices:
        del stored_devices[device_uid]
        new_options = dict(entry.options)
        new_options[CONF_DEVICES] = stored_devices
        hass.config_entries.async_update_entry(entry, options=new_options)

    # Allow re-discovery if the device sends again
    discovered: set[str] = entry_data.get("_discovered_uids", set())
    discovered.discard(device_uid)

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
    elif automatic_add:
        # Auto-add mode: immediately add the device and fire signal
        _auto_add_device(hass, entry, device_uid, params, event)
    else:
        # Discovery mode: fire a discovery config flow.  The device will
        # appear in the "Discovered" section of Settings → Devices & Services.
        # The user clicks Configure → names it → it becomes a stored device.
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

    # --- Track UID per protocol+model (BEFORE any early returns) ---
    # This lets us detect stability: stable devices (SYS2000) produce the
    # same UID on repeat presses; unstable devices (door sensors) produce
    # a different UID every time.
    protocol = params.get("protocol", "")
    model = params.get("model", "")
    proto_model_key = f"{protocol}_{model}"
    proto_uids: dict[str, set[str]] = entry_data.setdefault(
        "_proto_model_uids", {}
    )
    uid_set = proto_uids.setdefault(proto_model_key, set())
    if device_uid in uid_set:
        # Same UID seen again → this protocol+model produces stable UIDs
        entry_data.setdefault("_proto_model_confirmed", {})[
            proto_model_key
        ] = True
    uid_set.add(device_uid)

    # --- Standard dedup checks ---
    if device_uid in discovered:
        return  # Already fired a discovery for this device this session

    # Suppress cross-protocol false positives from a recent RF signal.
    last_known = entry_data.get("_last_known_event_time", 0.0)
    if time.monotonic() - last_known < _KNOWN_DEVICE_SHADOW_SECS:
        discovered.add(device_uid)
        return

    # Stability check: if we've seen >1 UID for this protocol+model and
    # NONE has been confirmed (no repeat), the device has unstable decoding
    # (e.g. door sensor).  Block further discoveries — only the first is
    # allowed.  If confirmed stable (like SYS2000), allow after cooldown.
    confirmed = entry_data.get("_proto_model_confirmed", {})
    if len(uid_set) > 1 and not confirmed.get(proto_model_key):
        discovered.add(device_uid)
        return

    # Cooldown: suppress rapid same-protocol+model discoveries.
    seen_proto_models: dict[str, float] = entry_data["_discovered_protocol_models"]
    now = time.monotonic()
    last_seen = seen_proto_models.get(proto_model_key, 0.0)
    if now - last_seen < _PROTO_MODEL_COOLDOWN_SECS:
        discovered.add(device_uid)
        return
    seen_proto_models[proto_model_key] = now

    # --- Proceed with discovery ---
    # Set time shadow so cross-protocol events from this same RF signal
    # (waveman/sartano arriving within ms) are suppressed.
    entry_data["_last_known_event_time"] = time.monotonic()

    discovered.add(device_uid)
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

    # --- Track UID per protocol+model (BEFORE any early returns) ---
    protocol = params.get("protocol", "")
    model = params.get("model", "")
    proto_model_key = f"{protocol}_{model}"
    proto_uids: dict[str, set[str]] = entry_data.setdefault(
        "_proto_model_uids", {}
    )
    uid_set = proto_uids.setdefault(proto_model_key, set())
    if device_uid in uid_set:
        entry_data.setdefault("_proto_model_confirmed", {})[
            proto_model_key
        ] = True
    uid_set.add(device_uid)

    if device_uid in discovered:
        return
    discovered.add(device_uid)

    # Suppress cross-protocol false positives from a recent RF signal.
    last_known = entry_data.get("_last_known_event_time", 0.0)
    if time.monotonic() - last_known < _KNOWN_DEVICE_SHADOW_SECS:
        return

    # Stability check: block unconfirmed protocol+models with >1 UID.
    confirmed = entry_data.get("_proto_model_confirmed", {})
    if len(uid_set) > 1 and not confirmed.get(proto_model_key):
        return

    # Cooldown: suppress rapid same-protocol+model auto-adds.
    seen_proto_models: dict[str, float] = entry_data["_discovered_protocol_models"]
    now = time.monotonic()
    last_seen = seen_proto_models.get(proto_model_key, 0.0)
    if now - last_seen < _PROTO_MODEL_COOLDOWN_SECS:
        return
    seen_proto_models[proto_model_key] = now

    # --- Proceed with auto-add ---
    # Set time shadow so cross-protocol events from this same RF signal
    # are suppressed.
    entry_data["_last_known_event_time"] = time.monotonic()

    house = params.get("house", "")
    unit = params.get("unit", params.get("code", ""))
    name = f"TellStick {device_uid}"

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
    elif suffix and automatic_add:
        # Auto-add: persist sensor and fire signal
        sensor_uid = f"sensor_{event.sensor_id}_{suffix}"
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        discovered: set[str] = entry_data.get("_discovered_uids", set())
        if sensor_uid not in discovered:
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
        # Unknown sensor — fire a discovery config flow
        sensor_uid = f"sensor_{event.sensor_id}_{suffix}"
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        discovered: set[str] = entry_data.get("_discovered_uids", set())
        if sensor_uid not in discovered:
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
