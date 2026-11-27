"""Switch platform: one Luxorparts socket per config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.components.radio_frequency import async_send_command
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from rf_protocols.commands.ook import OOKCommand

from . import luxorparts
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the socket switch."""
    async_add_entities([LuxorpartsSwitch(entry)])


class LuxorpartsSwitch(SwitchEntity):
    """A Luxorparts socket, sending one OOK packet per command."""

    _attr_has_entity_name = True
    _attr_assumed_state = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_switch"
        self._attr_name = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Luxorparts",
            model="50969 / 50970 / 50972",
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send the ON code."""
        await self._async_send("on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send the OFF code."""
        await self._async_send("off")

    async def _async_send(self, action: str) -> None:
        data = self._entry.data
        try:
            code = luxorparts.codes(data["house"], data["unit"])[action]
            command = OOKCommand(
                frequency=luxorparts.FREQUENCY_HZ,
                timings=luxorparts.timings(code),
                repeat_count=luxorparts.REPEATS,
            )
            await async_send_command(self.hass, data["transmitter"], command)
        except (HomeAssistantError, OSError, ValueError) as err:
            raise HomeAssistantError(f"Luxorparts {action} failed: {err}") from err
        self._attr_is_on = action == "on"
        self.async_write_ha_state()
