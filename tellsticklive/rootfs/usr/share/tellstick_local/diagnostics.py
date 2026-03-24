"""Diagnostics for TellStick Local integration.

Users can download this from Settings → Devices & Services →
TellStick Local → three-dot menu → Download diagnostics.

The output mirrors the old `hassio.addon_stdin` `list-sensors` command,
showing every stored sensor and device with its protocol, model, id and type.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import (
    CONF_COMMAND_PORT,
    CONF_DEVICE_HOUSE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    CONF_EVENT_PORT,
    CONF_IGNORED_UIDS,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    SENSOR_TYPE_NAMES,
)

_SENSOR_TYPE_NAMES: dict[int, str] = SENSOR_TYPE_NAMES


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Provides an equivalent of the old 'list-sensors' / 'list' stdin commands,
    showing every registered sensor and device with protocol, model, id and
    data type so users can identify strange or duplicate discovered devices.
    """
    devices = entry.options.get(CONF_DEVICES, {})
    ignored = entry.options.get(CONF_IGNORED_UIDS, {})
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    device_id_map: dict[str, int] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})

    sensors: list[dict[str, Any]] = []
    controllable: list[dict[str, Any]] = []

    for uid, cfg in devices.items():
        if uid.startswith("sensor_"):
            data_type = cfg.get("data_type")
            sensors.append(
                {
                    "uid": uid,
                    "name": cfg.get(CONF_DEVICE_NAME, uid),
                    "protocol": cfg.get(CONF_DEVICE_PROTOCOL, ""),
                    "model": cfg.get(CONF_DEVICE_MODEL, ""),
                    "sensor_id": cfg.get("sensor_id"),
                    "data_type": (
                        _SENSOR_TYPE_NAMES.get(data_type, str(data_type))
                        if data_type is not None
                        else None
                    ),
                }
            )
        else:
            controllable.append(
                {
                    "uid": uid,
                    "name": cfg.get(CONF_DEVICE_NAME, uid),
                    "protocol": cfg.get(CONF_DEVICE_PROTOCOL, ""),
                    "model": cfg.get(CONF_DEVICE_MODEL, ""),
                    "house": cfg.get(CONF_DEVICE_HOUSE, ""),
                    "unit": cfg.get(CONF_DEVICE_UNIT, ""),
                    "telldusd_id": device_id_map.get(uid),
                }
            )

    return {
        "connection": {
            "host": entry.data.get(CONF_HOST, ""),
            "command_port": entry.data.get(CONF_COMMAND_PORT, ""),
            "event_port": entry.data.get(CONF_EVENT_PORT, ""),
        },
        "sensors": sensors,
        "devices": controllable,
        "ignored_count": len(ignored),
    }
