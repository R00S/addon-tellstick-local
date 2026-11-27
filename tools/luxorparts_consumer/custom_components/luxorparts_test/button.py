"""Learn button: sends the long pairing burst."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.components.radio_frequency import async_send_command
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    """Add the learn button."""
    async_add_entities([LuxorpartsLearnButton(entry)])


class LuxorpartsLearnButton(ButtonEntity):
    """Put the socket in learn mode, then press this."""

    _attr_has_entity_name = True
    _attr_name = "Learn"
    _attr_icon = "mdi:remote"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_learn"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}
        )

    async def async_press(self) -> None:
        """Send the ON code with the long learn burst."""
        data = self._entry.data
        code = luxorparts.codes(data["house"], data["unit"])["on"]
        command = OOKCommand(
            frequency=luxorparts.FREQUENCY_HZ,
            timings=luxorparts.timings(code),
            repeat_count=luxorparts.LEARN_REPEATS,
        )
        await async_send_command(self.hass, data["transmitter"], command)
