"""Switch platform for TellStick Local integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

from .client import DeviceEvent, RawDeviceEvent, TellStickController
from .const import (
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
    TELLSTICK_TURNON,
)
from .entity import TellStickEntity

_LOGGER = logging.getLogger(__name__)

# Exact model names that map to a switch entity (not a dimmer/light).
# Uses exact set membership – "selflearning-dimmer" must NOT match here.
_SWITCH_MODELS = {
    "codeswitch",
    "selflearning-switch",
    "selflearning",  # raw RF event model for auto-discovered arctech devices
    "bell",
    "kp100",
    "ecosavers",
}

# Protocols that use UP/DOWN/STOP (not ON/OFF) — handled by cover.py instead.
# Source: ProtocolHasta.cpp and ProtocolBrateck.cpp — methods() returns
# TELLSTICK_UP | TELLSTICK_DOWN | TELLSTICK_STOP, not TELLSTICK_TURNON.
_COVER_PROTOCOLS = {"hasta", "brateck"}


def _is_switch(protocol: str, model: str) -> bool:
    if protocol.lower() in _COVER_PROTOCOLS:
        return False
    base = model.split(":")[0].lower() if ":" in model else model.lower()
    return base in _SWITCH_MODELS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TellStick switch entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    controller: TellStickController = entry_data[ENTRY_TELLSTICK_CONTROLLER]
    device_id_map: dict[str, int] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)

    known: set[str] = set()

    # Pre-create entities for stored (manually-added) switch devices
    stored_entities: list[TellStickSwitch] = []
    for device_uid, device_cfg in entry.options.get(CONF_DEVICES, {}).items():
        protocol = device_cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = device_cfg.get(CONF_DEVICE_MODEL, "")
        if not _is_switch(protocol, model):
            continue
        known.add(device_uid)
        stored_entities.append(
            TellStickSwitch(
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
            if er.async_get(hass).async_get_entity_id("switch", DOMAIN, unique_id) is not None:
                return  # entity still active — skip duplicate
            known.discard(uid)  # entity was deleted — fall through to create
        if not _is_switch(protocol, model):
            return
        known.add(uid)
        # Use stored name if available, otherwise generate one
        stored = entry.options.get(CONF_DEVICES, {}).get(uid, {})
        name = stored.get(CONF_DEVICE_NAME) or f"TellStick {uid}"
        entity = TellStickSwitch(
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
        house: str = "",
        unit: str = "",
    ) -> None:
        """Initialize a TellStick switch."""
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
        else:
            _LOGGER.warning(
                "Cannot send on command for %s: no telldusd device ID (UID mismatch?)",
                self._device_uid,
            )
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._telldusd_device_id is not None:
            await self._controller.turn_off(self._telldusd_device_id)
        else:
            _LOGGER.warning(
                "Cannot send off command for %s: no telldusd device ID (UID mismatch?)",
                self._device_uid,
            )
        self._attr_is_on = False
        self.async_write_ha_state()
