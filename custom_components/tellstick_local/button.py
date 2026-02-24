"""Button platform for TellStick Local integration.

Provides a "Send learn signal" button on each non-sensor device so users
can trigger pairing directly from the device page (instead of navigating
to the integration's options flow).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import RawDeviceEvent, TellStickController
from .const import (
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICES,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    SIGNAL_NEW_DEVICE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TellStick learn button entities."""
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)

    known: set[str] = set()

    # Pre-create button entities for stored non-sensor devices
    stored_entities: list[TellStickLearnButton] = []
    for device_uid, device_cfg in entry.options.get(CONF_DEVICES, {}).items():
        if device_uid.startswith("sensor_"):
            continue
        known.add(device_uid)
        stored_entities.append(
            TellStickLearnButton(
                entry_id=entry.entry_id,
                device_uid=device_uid,
                name=device_cfg.get(CONF_DEVICE_NAME, f"TellStick {device_uid}"),
                protocol=device_cfg.get(CONF_DEVICE_PROTOCOL, ""),
                model=device_cfg.get(CONF_DEVICE_MODEL, ""),
            )
        )
    if stored_entities:
        async_add_entities(stored_entities)

    @callback
    def _async_new_device(event: Any) -> None:
        if not isinstance(event, RawDeviceEvent):
            return
        params = event.params
        uid = event.device_id
        if not uid or uid in known:
            return
        # Sensors don't get learn buttons
        if uid.startswith("sensor_"):
            return
        known.add(uid)
        stored = entry.options.get(CONF_DEVICES, {}).get(uid, {})
        name = stored.get(CONF_DEVICE_NAME) or f"TellStick {uid}"
        entity = TellStickLearnButton(
            entry_id=entry.entry_id,
            device_uid=uid,
            name=name,
            protocol=params.get("protocol", ""),
            model=params.get("model", ""),
        )
        async_add_entities([entity])

    entry.async_on_unload(
        async_dispatcher_connect(hass, new_device_signal, _async_new_device)
    )


class TellStickLearnButton(ButtonEntity):
    """Button to send a learn/pairing signal for a TellStick device.

    Appears on the device page so users can trigger pairing without
    navigating to the integration's options flow.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:broadcast"
    _attr_translation_key = "learn"

    def __init__(
        self,
        entry_id: str,
        device_uid: str,
        name: str,
        protocol: str,
        model: str,
    ) -> None:
        """Initialize the learn button."""
        self._entry_id = entry_id
        self._device_uid = device_uid
        self._attr_unique_id = f"{entry_id}_{device_uid}_learn"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{device_uid}")},
        )

    async def async_press(self) -> None:
        """Send learn signal when pressed."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        controller: TellStickController | None = entry_data.get(
            ENTRY_TELLSTICK_CONTROLLER
        )
        device_id_map: dict[str, int] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
        telldusd_id = device_id_map.get(self._device_uid)

        if controller is None or telldusd_id is None:
            _LOGGER.error(
                "Cannot send learn signal for %s: controller or device ID unavailable",
                self._device_uid,
            )
            return

        _LOGGER.debug("Sending learn signal for %s (telldusd id %s)", self._device_uid, telldusd_id)
        await controller.learn(telldusd_id)
