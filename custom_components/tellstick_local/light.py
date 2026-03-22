"""Light platform for TellStick Local integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

from .client import DeviceEvent, RawDeviceEvent, TellStickController
from .const import (
    BACKEND_DUO,
    CONF_BACKEND,
    CONF_DEVICE_HOUSE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
    TELLSTICK_DIM,
    TELLSTICK_TURNOFF,
    TELLSTICK_TURNON,
)
from .entity import TellStickEntity

_LOGGER = logging.getLogger(__name__)

# Exact model names that map to a dimmable light entity.
_DIMMER_MODELS = {
    "selflearning-dimmer",
}


def _is_dimmer(protocol: str, model: str) -> bool:
    base = model.split(":")[0].lower() if ":" in model else model.lower()
    return base in _DIMMER_MODELS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TellStick light (dimmer) entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    controller: TellStickController = entry_data[ENTRY_TELLSTICK_CONTROLLER]
    device_id_map: dict[str, Any] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)

    known: set[str] = set()

    # Pre-create entities for stored (manually-added) dimmer devices
    stored_entities: list[TellStickLight] = []
    for device_uid, device_cfg in entry.options.get(CONF_DEVICES, {}).items():
        protocol = device_cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = device_cfg.get(CONF_DEVICE_MODEL, "")
        if not _is_dimmer(protocol, model):
            continue
        known.add(device_uid)
        stored_entities.append(
            TellStickLight(
                entry_id=entry.entry_id,
                device_uid=device_uid,
                name=device_cfg.get(CONF_DEVICE_NAME, f"TellStick {device_uid}"),
                protocol=protocol,
                model=model,
                controller=controller,
                device_id=device_id_map.get(device_uid),
                house=device_cfg.get(CONF_DEVICE_HOUSE, ""),
                unit=device_cfg.get(CONF_DEVICE_UNIT, ""),
            )
        )
    if stored_entities:
        async_add_entities(stored_entities)

    @callback
    def _async_new_device(event: Any) -> None:
        if not isinstance(event, RawDeviceEvent):
            return
        params = event.params
        protocol = params.get("protocol", "")
        model = params.get("model", "")
        uid = event.device_id
        if not uid:
            return
        if uid in known:
            # Guard: if the entity was deleted in this session without a
            # reload (delete + re-add same session), `uid` stays in `known`
            # but the entity is gone from the registry.  Check and allow
            # re-creation.  Issue #33.
            unique_id = f"{entry.entry_id}_{uid}"
            if er.async_get(hass).async_get_entity_id("light", DOMAIN, unique_id) is not None:
                return  # entity still active — skip duplicate
            known.discard(uid)  # entity was deleted — fall through to create
        if not _is_dimmer(protocol, model):
            return
        known.add(uid)
        # Use stored name if available, otherwise generate one
        stored = entry.options.get(CONF_DEVICES, {}).get(uid, {})
        name = stored.get(CONF_DEVICE_NAME) or f"TellStick {uid}"
        entity = TellStickLight(
            entry_id=entry.entry_id,
            device_uid=uid,
            name=name,
            protocol=protocol,
            model=model,
            controller=controller,
            device_id=device_id_map.get(uid),
            house=params.get("house", ""),
            unit=params.get("unit", params.get("code", "")),
        )
        async_add_entities([entity])

    # Always listen for new device signals — manually added devices (via the
    # "Add device" button) dispatch this signal immediately, while auto-detected
    # devices are gated by automatic_add in __init__._handle_raw_event.
    entry.async_on_unload(
        async_dispatcher_connect(hass, new_device_signal, _async_new_device)
    )


class TellStickLight(TellStickEntity, LightEntity):
    """Representation of a dimmable TellStick light."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        entry_id: str,
        device_uid: str,
        name: str,
        protocol: str,
        model: str,
        controller: TellStickController,
        device_id: Any = None,
        house: str = "",
        unit: str = "",
    ) -> None:
        """Initialize a TellStick light."""
        super().__init__(
            entry_id=entry_id,
            device_uid=device_uid,
            name=name,
            protocol=protocol,
            model=model,
            house=house,
            unit=unit,
        )
        self._controller = controller
        self._telldusd_device_id = device_id
        self._attr_is_on = False
        self._attr_brightness: int | None = None

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to events."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = last.state == "on"
            if (brightness := last.attributes.get(ATTR_BRIGHTNESS)) is not None:
                self._attr_brightness = int(brightness)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_EVENT.format(self._entry_id),
                self._handle_event,
            )
        )

    @callback
    def _handle_event(self, event: Any) -> None:
        """Update state from incoming event."""
        if isinstance(event, DeviceEvent) and self._telldusd_device_id is not None:
            if event.device_id != self._telldusd_device_id:
                return
            if event.method == TELLSTICK_TURNON:
                self._attr_is_on = True
            elif event.method == TELLSTICK_TURNOFF:
                self._attr_is_on = False
            elif event.method == TELLSTICK_DIM and event.value:
                try:
                    self._attr_brightness = int(event.value)
                    self._attr_is_on = self._attr_brightness > 0
                except ValueError:
                    pass
            self.async_write_ha_state()
            return

        if isinstance(event, RawDeviceEvent):
            if event.device_id != self._device_uid:
                return
            method = event.params.get("method", "")
            if method == "turnon":
                self._attr_is_on = True
            elif method == "turnoff":
                self._attr_is_on = False
            elif method == "dim":
                try:
                    self._attr_brightness = int(event.params.get("dimlevel", "0"))
                    self._attr_is_on = self._attr_brightness > 0
                except ValueError:
                    pass
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, optionally at a brightness level."""
        if self._telldusd_device_id is not None:
            if ATTR_BRIGHTNESS in kwargs:
                level = int(kwargs[ATTR_BRIGHTNESS])
                await self._controller.dim(self._telldusd_device_id, level)
                self._attr_brightness = level
            else:
                await self._controller.turn_on(self._telldusd_device_id)
        else:
            _LOGGER.warning(
                "Cannot send on command for %s: no telldusd device ID (UID mismatch?)",
                self._device_uid,
            )
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        if self._telldusd_device_id is not None:
            await self._controller.turn_off(self._telldusd_device_id)
        else:
            _LOGGER.warning(
                "Cannot send off command for %s: no telldusd device ID (UID mismatch?)",
                self._device_uid,
            )
        self._attr_is_on = False
        self.async_write_ha_state()
