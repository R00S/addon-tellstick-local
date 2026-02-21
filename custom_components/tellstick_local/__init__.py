"""TellStick Local integration – hub setup and event dispatch."""
from __future__ import annotations

import asyncio
import logging
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
    CONF_COMMAND_PORT,
    CONF_DEVICE_HOUSE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    CONF_EVENT_PORT,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    PLATFORMS,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
)

_LOGGER = logging.getLogger(__name__)

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


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

    if device_uid in stored_devices:
        # Known device — fire SIGNAL_NEW_DEVICE so platforms can revive
        # entities after a restart (the entity is pre-created from stored
        # config, but the signal lets late-starting platforms pick it up).
        async_dispatcher_send(
            hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), event
        )
    else:
        # Unknown device — fire a discovery config flow.  The device will
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

    if device_uid in discovered:
        return  # Already fired a discovery for this device this session

    discovered.add(device_uid)
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "integration_discovery"},
            data={
                "device_uid": device_uid,
                "protocol": params.get("protocol", ""),
                "model": params.get("model", ""),
                "house": params.get("house", ""),
                "unit": params.get("unit", params.get("code", "")),
                "entry_id": entry.entry_id,
                "type": "device",
            },
        )
    )


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
    suffix = _SENSOR_SUFFIX.get(event.data_type)
    sensor_prefix = f"sensor_{event.sensor_id}_"
    is_known = any(uid.startswith(sensor_prefix) for uid in stored_devices)

    if is_known:
        # Known sensor — revive entity after restart
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
