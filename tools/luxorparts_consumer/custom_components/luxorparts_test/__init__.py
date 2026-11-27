"""Luxorparts 433 MHz socket, sent through a radio_frequency transmitter.

This is a *consumer*: the protocol lives in ``luxorparts.py``, and the
transmission goes through Home Assistant's ``radio_frequency`` API, so any
integration that provides a transmitter can carry it.  It exists to test that
provider end to end — pairing included — without TellStick Local needing any
knowledge of the protocol.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one Luxorparts socket."""
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Luxorparts socket."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
