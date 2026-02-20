"""Switch platform for TellStick Local integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import DeviceEvent, RawDeviceEvent, TellStickController
from .const import (
    CONF_AUTOMATIC_ADD,
    DOMAIN,
    ENTRY_TELLSTICK_CONTROLLER,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
    TELLSTICK_TURNON,
)
from .entity import TellStickEntity

_LOGGER = logging.getLogger(__name__)

# Model keywords that indicate a switch (not a dimmer/light)
_SWITCH_MODELS = {
    "codeswitch",
    "selflearning-switch",
    "selflearning",
    "bell",
    "kp100",
    "ecosavers",
}


def _is_switch(protocol: str, model: str) -> bool:
    return any(kw in model.lower() for kw in _SWITCH_MODELS)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TellStick switch entities."""
    controller: TellStickController = hass.data[DOMAIN][entry.entry_id][
        ENTRY_TELLSTICK_CONTROLLER
    ]
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)

    known: set[str] = set()

    @callback
    def _async_new_device(event: Any) -> None:
        if not isinstance(event, RawDeviceEvent):
            return
        params = event.params
        protocol = params.get("protocol", "")
        model = params.get("model", "")
        uid = event.device_id
        if not uid or uid in known:
            return
        if not _is_switch(protocol, model):
            return
        known.add(uid)
        name = f"TellStick {uid}"
        entity = TellStickSwitch(
            entry_id=entry.entry_id,
            device_uid=uid,
            name=name,
            protocol=protocol,
            model=model,
            controller=controller,
        )
        async_add_entities([entity])

    if entry.options.get(CONF_AUTOMATIC_ADD, False):
        entry.async_on_unload(
            async_dispatcher_connect(hass, new_device_signal, _async_new_device)
        )


class TellStickSwitch(TellStickEntity, SwitchEntity):
    """Representation of a TellStick switch."""

    def __init__(
        self,
        entry_id: str,
        device_uid: str,
        name: str,
        protocol: str,
        model: str,
        controller: TellStickController,
        device_id: int | None = None,
    ) -> None:
        """Initialize a TellStick switch."""
        super().__init__(
            entry_id=entry_id,
            device_uid=device_uid,
            name=name,
            protocol=protocol,
            model=model,
        )
        self._controller = controller
        self._telldusd_device_id = device_id
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to events."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = last.state == "on"

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
            self._attr_is_on = event.method == TELLSTICK_TURNON
            self.async_write_ha_state()
            return

        if isinstance(event, RawDeviceEvent):
            if event.device_id != self._device_uid:
                return
            method = event.params.get("method", "")
            self._attr_is_on = method == "turnon"
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self._telldusd_device_id is not None:
            await self._controller.turn_on(self._telldusd_device_id)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._telldusd_device_id is not None:
            await self._controller.turn_off(self._telldusd_device_id)
        self._attr_is_on = False
        self.async_write_ha_state()
