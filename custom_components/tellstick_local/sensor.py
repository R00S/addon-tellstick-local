"""Sensor platform for TellStick Local integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEGREE, PERCENTAGE, UnitOfLength, UnitOfSpeed, UnitOfTemperature, UnitOfVolumetricFlux
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

from .client import SensorEvent
from .const import (
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICES,
    DOMAIN,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
    TELLSTICK_HUMIDITY,
    TELLSTICK_RAINRATE,
    TELLSTICK_RAINTOTAL,
    TELLSTICK_TEMPERATURE,
    TELLSTICK_WINDDIRECTION,
    TELLSTICK_WINDAVERAGE,
    TELLSTICK_WINDGUST,
)
from .entity import TellStickEntity

_LOGGER = logging.getLogger(__name__)

_SENSOR_META: dict[int, tuple[str, SensorDeviceClass | None, str]] = {
    TELLSTICK_TEMPERATURE: ("temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    TELLSTICK_HUMIDITY: ("humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE),
    TELLSTICK_RAINRATE: ("rain_rate", SensorDeviceClass.PRECIPITATION_INTENSITY, UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR),
    TELLSTICK_RAINTOTAL: ("rain_total", SensorDeviceClass.PRECIPITATION, UnitOfLength.MILLIMETERS),
    TELLSTICK_WINDDIRECTION: ("wind_direction", None, DEGREE),
    TELLSTICK_WINDAVERAGE: ("wind_speed", SensorDeviceClass.WIND_SPEED, UnitOfSpeed.METERS_PER_SECOND),
    TELLSTICK_WINDGUST: ("wind_gust", SensorDeviceClass.WIND_SPEED, UnitOfSpeed.METERS_PER_SECOND),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TellStick sensor entities."""
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)

    known: set[str] = set()

    # Pre-create entities for stored sensor devices (persisted auto-detections)
    stored_entities: list[TellStickSensor] = []
    for device_uid, device_cfg in entry.options.get(CONF_DEVICES, {}).items():
        if not device_uid.startswith("sensor_"):
            continue
        sensor_id = device_cfg.get("sensor_id")
        data_type = device_cfg.get("data_type")
        if sensor_id is None or data_type is None:
            continue
        if data_type not in _SENSOR_META:
            continue
        known.add(device_uid)
        suffix, _, _ = _SENSOR_META[data_type]
        stored_entities.append(
            TellStickSensor(
                entry_id=entry.entry_id,
                device_uid=device_uid,
                name=device_cfg.get(CONF_DEVICE_NAME, f"TellStick sensor {sensor_id} {suffix}"),
                protocol=device_cfg.get(CONF_DEVICE_PROTOCOL, ""),
                model=device_cfg.get(CONF_DEVICE_MODEL, ""),
                sensor_id=sensor_id,
                data_type=data_type,
            )
        )
    if stored_entities:
        async_add_entities(stored_entities)

    @callback
    def _async_new_device(event: Any) -> None:
        if not isinstance(event, SensorEvent):
            return
        if event.data_type not in _SENSOR_META:
            return
        suffix, _, _ = _SENSOR_META[event.data_type]
        uid = f"sensor_{event.sensor_id}_{suffix}"
        if uid in known:
            # Guard: if the entity was deleted in this session without a
            # reload (delete + re-add same session), `uid` stays in `known`
            # but the entity is gone from the registry.  Check and allow
            # re-creation.  Issue #33.
            unique_id = f"{entry.entry_id}_{uid}"
            if er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id) is not None:
                return  # entity still active — skip duplicate
            known.discard(uid)  # entity was deleted — fall through to create
        known.add(uid)
        protocol = event.protocol or ""
        model = event.model or ""
        # Use stored name from entry options when available (e.g. after
        # discovery Add flow sets a user-provided name).  Fall back to
        # the default sensor name.
        stored_cfg = entry.options.get(CONF_DEVICES, {}).get(uid, {})
        name = stored_cfg.get(
            CONF_DEVICE_NAME, f"TellStick sensor {event.sensor_id} {suffix}"
        )
        entity = TellStickSensor(
            entry_id=entry.entry_id,
            device_uid=uid,
            name=name,
            protocol=protocol,
            model=model,
            sensor_id=event.sensor_id,
            data_type=event.data_type,
        )
        # Set initial value from the event that triggered creation.
        # SIGNAL_EVENT fires before SIGNAL_NEW_DEVICE in __init__.py, so
        # the entity misses the first value update.  Without this, the
        # entity shows "unavailable" until the next sensor reading.
        if event.value is not None:
            try:
                entity._attr_native_value = float(event.value)
            except (ValueError, TypeError):
                entity._attr_native_value = event.value
        async_add_entities([entity])

    # Always listen for new sensor signals — __init__.py gates new discovery
    # behind automatic_add, but always fires for known (stored) sensors so
    # they can be revived after a restart.
    entry.async_on_unload(
        async_dispatcher_connect(hass, new_device_signal, _async_new_device)
    )


class TellStickSensor(TellStickEntity, SensorEntity):
    """Representation of a TellStick wireless sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        entry_id: str,
        device_uid: str,
        name: str,
        protocol: str,
        model: str,
        sensor_id: int,
        data_type: int,
    ) -> None:
        """Initialize a TellStick sensor."""
        meta = _SENSOR_META.get(data_type)
        suffix, device_class, unit = meta if meta else (None, None, None)

        # Entity name is just the measurement type ("Temperature" / "Humidity").
        # With _attr_has_entity_name = True the HA frontend displays it as
        # "{device name} Temperature", which is the standard HA pattern.
        # Note: suffix is None only for unknown data_types, which are already
        # filtered out by the _SENSOR_META check in async_setup_entry, so
        # the fallback to `name` is purely defensive.
        type_name = suffix.capitalize() if suffix else name

        # Device name: strip the type suffix from the stored name so that
        # temperature and humidity entities share a consistent device name.
        # e.g. "TellStick sensor 202 temperature" → "TellStick sensor 202"
        if suffix and name.lower().endswith(f" {suffix}"):
            device_name = name[: -(len(suffix) + 1)]
        else:
            device_name = name

        super().__init__(
            entry_id=entry_id,
            device_uid=device_uid,
            name=type_name,
            protocol=protocol,
            model=model,
        )

        # Explicitly set the entity name and the suggested object_id so HA
        # generates a clean entity_id like "sensor.living_room_temperature"
        # rather than inheriting a mangled or doubled name.  With
        # _attr_has_entity_name=True the frontend displays "{device} {type}",
        # but the entity_id comes from suggested_object_id.  Issue #33.
        self._attr_name = type_name
        self._attr_suggested_object_id = f"{device_name} {type_name}".lower()

        # Group temperature + humidity from the same physical sensor under one
        # HA device.  Use sensor_{sensor_id} (without the type suffix) as the
        # shared device identifier so both entities appear under one device.
        # _attr_unique_id is still {entry_id}_sensor_{id}_{suffix} (unchanged)
        # so entity history and entity_ids are fully preserved.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sensor_{sensor_id}")},
            name=device_name,
            model=f"{protocol}/{model}" if model else protocol,
        )

        self._sensor_id = sensor_id
        self._data_type = data_type
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to events."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_native_value = last.state

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_EVENT.format(self._entry_id),
                self._handle_event,
            )
        )

    @callback
    def _handle_event(self, event: Any) -> None:
        """Update value from sensor event."""
        if not isinstance(event, SensorEvent):
            return
        if event.sensor_id != self._sensor_id or event.data_type != self._data_type:
            return
        try:
            self._attr_native_value = float(event.value) if event.value else None
        except ValueError:
            self._attr_native_value = event.value
        self.async_write_ha_state()
