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
    LX_GROUND_TRUTH_CODES,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
    TELLSTICK_TURNON,
    luxorparts_build_raw_command,
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


def _is_dimmer_model(model: str) -> bool:
    """Return True if *model* is a dimmer model (light, not switch)."""
    base = model.split(":")[0].lower() if ":" in model else model.lower()
    return base == "selflearning-dimmer"


def _remove_stale_switch(
    ent_reg: er.EntityRegistry, entry_id: str, device_uid: str
) -> None:
    """Remove a stale switch entity for a device that is now a dimmer/light.

    When a device is (re-)added as a dimmer, any previously auto-discovered
    switch entity for the same UID must be removed from the entity registry.
    Without this cleanup the old switch persists alongside the new light,
    leaving the user with a broken switch entity and no dimmer controls.
    """
    unique_id = f"{entry_id}_{device_uid}"
    entity_id = ent_reg.async_get_entity_id("switch", DOMAIN, unique_id)
    if entity_id is not None:
        _LOGGER.info(
            "Removing stale switch entity %s for dimmer device %s",
            entity_id,
            device_uid,
        )
        ent_reg.async_remove(entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TellStick switch entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    controller: TellStickController = entry_data[ENTRY_TELLSTICK_CONTROLLER]
    device_id_map: dict[str, Any] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)
    backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
    manufacturer = "TellStick Net/ZNet" if backend != BACKEND_DUO else "TellStick Duo"

    known: set[str] = set()

    # Pre-create entities for stored (manually-added) switch devices
    ent_reg = er.async_get(hass)
    stored_entities: list[TellStickSwitch] = []
    for device_uid, device_cfg in entry.options.get(CONF_DEVICES, {}).items():
        protocol = device_cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = device_cfg.get(CONF_DEVICE_MODEL, "")
        if not _is_switch(protocol, model):
            # If the stored model is a dimmer, clean up any stale switch
            # entity from before the model was changed.
            if _is_dimmer_model(model):
                _remove_stale_switch(ent_reg, entry.entry_id, device_uid)
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
                manufacturer=manufacturer,
                group_uid=device_cfg.get("group_uid") or None,
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
        # Determine the catalog model for the type check.  Three sources,
        # in priority order:
        #   1. _catalog_model from the synthetic event (set by "Add device"
        #      flow — always correct and independent of entry.options timing)
        #   2. Stored catalog model from entry.options (correct after restart)
        #   3. RF event model (fallback — loses -dimmer/-switch distinction)
        stored = entry.options.get(CONF_DEVICES, {}).get(uid, {})
        check_model = (
            params.get("_catalog_model", "")
            or stored.get(CONF_DEVICE_MODEL, "")
            or model
        )
        if not _is_switch(protocol, check_model):
            # Catalog/stored model says dimmer — clean up any stale switch.
            if _is_dimmer_model(check_model):
                _remove_stale_switch(ent_reg, entry.entry_id, uid)
            return
        known.add(uid)
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
            manufacturer=manufacturer,
            group_uid=stored.get("group_uid") or None,
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
        device_id: Any = None,
        house: str = "",
        unit: str = "",
        manufacturer: str = "",
        group_uid: str | None = None,
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
            manufacturer=manufacturer,
            group_uid=group_uid,
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
        _LOGGER.debug(
            "turn_on: uid=%s controller=%s device_id=%r",
            self._device_uid, type(self._controller).__name__, self._telldusd_device_id,
        )
        if self._protocol == "luxorparts" and hasattr(self._controller, "send_raw_command"):
            await self._send_luxorparts_raw("on")
        elif self._telldusd_device_id is not None:
            await self._controller.turn_on(self._telldusd_device_id)
        else:
            _LOGGER.warning(
                "Cannot send on command for %s: no telldusd device ID (UID mismatch?)",
                self._device_uid,
            )
        await self._async_mirror_command("turn_on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug(
            "turn_off: uid=%s controller=%s device_id=%r",
            self._device_uid, type(self._controller).__name__, self._telldusd_device_id,
        )
        if self._protocol == "luxorparts" and hasattr(self._controller, "send_raw_command"):
            await self._send_luxorparts_raw("off")
        elif self._telldusd_device_id is not None:
            await self._controller.turn_off(self._telldusd_device_id)
        else:
            _LOGGER.warning(
                "Cannot send off command for %s: no telldusd device ID (UID mismatch?)",
                self._device_uid,
            )
        await self._async_mirror_command("turn_off")
        self._attr_is_on = False
        self.async_write_ha_state()

    async def _send_luxorparts_raw(self, action: str) -> None:
        """Send raw Luxorparts pulse data via tdSendRawCommand (Duo path).

        Bypasses telldusd protocol registration entirely — sends the raw
        OOK-PWM pulse train directly to the TellStick hardware.
        """
        try:
            house_int = int(self._house) if self._house else 0
            unit_int = int(self._unit) if self._unit else 0
        except (TypeError, ValueError):
            _LOGGER.warning(
                "LX raw TX: invalid house=%r unit=%r", self._house, self._unit,
            )
            return

        codes = LX_GROUND_TRUTH_CODES.get((house_int, unit_int))
        if codes is None:
            _LOGGER.warning(
                "LX raw TX: no ground-truth code for h=%s u=%s",
                self._house, self._unit,
            )
            return

        code = codes.get(action)
        if code is None:
            _LOGGER.warning("LX raw TX: no code for action=%s", action)
            return

        # Extract variant suffix (e.g. "selflearning-switch:lx_t01" → "lx_t01")
        variant = self._model.split(":", 1)[1] if ":" in self._model else ""

        raw_cmd = luxorparts_build_raw_command(code, variant)
        _LOGGER.info(
            "LX raw TX: uid=%s variant=%s action=%s code=0x%x bytes=%d",
            self._device_uid, variant, action, code, len(raw_cmd),
        )
        result = await self._controller.send_raw_command(raw_cmd)
        # telldusd waits only ~25 ms for firmware ACK, but RF transmission
        # takes ~400+ ms.  Result -5 (TELLSTICK_ERROR_COMMUNICATION) means
        # the ACK timed out — the hardware still transmits successfully.
        if result == -5:
            _LOGGER.info(
                "LX raw TX: ACK timeout (expected for long TX), hardware should still transmit"
            )
        elif result != 0:
            _LOGGER.warning("LX raw TX failed: result=%d", result)
        else:
            _LOGGER.info("LX raw TX success: result=%d", result)
