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
    CONF_DEVICE_TYPE,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    GENERIC_RF_TYPE_LIGHT,
    PROTOCOL_GENERIC_RF,
    SIGNAL_EVENT,
    SIGNAL_NEW_DEVICE,
    TELLSTICK_DIM,
    TELLSTICK_TURNOFF,
    TELLSTICK_TURNON,
    generic_rf_build_raw_command,
)
from .entity import TellStickEntity

_LOGGER = logging.getLogger(__name__)

# Exact model names that map to a dimmable light entity.
_DIMMER_MODELS = {
    "selflearning-dimmer",
}


def _is_dimmer(protocol: str, model: str, device_cfg: dict | None = None) -> bool:
    """Check if a device should be a dimmer/light entity."""
    if protocol.lower() == PROTOCOL_GENERIC_RF:
        # For Generic RF devices, check device_type
        # Default to False for backward compatibility (existing Generic RF are switches)
        if device_cfg:
            device_type = device_cfg.get(CONF_DEVICE_TYPE, "")
            return device_type == GENERIC_RF_TYPE_LIGHT
        return False  # Backward compat: Generic RF without device_type are switches
    base = model.split(":")[0].lower() if ":" in model else model.lower()
    return base in _DIMMER_MODELS


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
    """Set up TellStick light (dimmer) entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    controller: TellStickController = entry_data[ENTRY_TELLSTICK_CONTROLLER]
    device_id_map: dict[str, Any] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)

    backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
    manufacturer = "TellStick Net/ZNet" if backend != BACKEND_DUO else "TellStick Duo"

    known: set[str] = set()

    # Pre-create entities for stored (manually-added) dimmer devices
    ent_reg = er.async_get(hass)
    stored_entities: list[TellStickLight] = []
    for device_uid, device_cfg in entry.options.get(CONF_DEVICES, {}).items():
        protocol = device_cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = device_cfg.get(CONF_DEVICE_MODEL, "")
        if not _is_dimmer(protocol, model, device_cfg):
            continue
        # Clean up stale switch entity for this UID — the device was
        # (re-)added as a dimmer, so any old switch entity must go.
        _remove_stale_switch(ent_reg, entry.entry_id, device_uid)
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
                manufacturer=manufacturer,
                group_uid=device_cfg.get("group_uid") or None,
                timings_on=device_cfg.get("timings_on"),
                timings_off=device_cfg.get("timings_off"),
                timings_dim_levels=device_cfg.get("timings_dim_levels"),
                repeat_count=device_cfg.get("repeat_count", 10),
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
        if not _is_dimmer(protocol, check_model, stored):
            return
        # Clean up stale switch entity for this UID — the device was
        # (re-)added as a dimmer, so any old switch entity must go.
        _remove_stale_switch(ent_reg, entry.entry_id, uid)
        known.add(uid)
        name = stored.get(CONF_DEVICE_NAME) or f"TellStick {uid}"
        # Use stored catalog model for display (shows "selflearning-dimmer"
        # instead of raw RF "selflearning" in the device info).
        display_model = (
            params.get("_catalog_model", "")
            or stored.get(CONF_DEVICE_MODEL, "")
            or model
        )
        entity = TellStickLight(
            entry_id=entry.entry_id,
            device_uid=uid,
            name=name,
            protocol=protocol,
            model=display_model,
            controller=controller,
            device_id=device_id_map.get(uid),
            house=params.get("house", ""),
            unit=params.get("unit", params.get("code", "")),
            manufacturer=manufacturer,
            group_uid=stored.get("group_uid") or None,
            timings_on=stored.get("timings_on"),
            timings_off=stored.get("timings_off"),
            timings_dim_levels=stored.get("timings_dim_levels"),
            repeat_count=stored.get("repeat_count", 10),
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
        manufacturer: str = "",
        group_uid: str | None = None,
        timings_on: list[int] | None = None,
        timings_off: list[int] | None = None,
        timings_dim_levels: dict[int, list[int]] | None = None,
        repeat_count: int = 10,
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
            manufacturer=manufacturer,
            group_uid=group_uid,
        )
        self._controller = controller
        self._telldusd_device_id = device_id
        self._attr_is_on = False
        self._attr_brightness: int | None = None
        # Generic RF support
        self._timings_on = timings_on
        self._timings_off = timings_off
        self._timings_dim_levels = timings_dim_levels or {}
        self._repeat_count = repeat_count

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
        if self._protocol == PROTOCOL_GENERIC_RF and hasattr(self._controller, "send_raw_command"):
            if ATTR_BRIGHTNESS in kwargs:
                level = int(kwargs[ATTR_BRIGHTNESS])
                await self._send_generic_rf_raw("dim", level)
                self._attr_brightness = level
            else:
                await self._send_generic_rf_raw("on")
            await self._async_mirror_command("turn_on")
        elif self._telldusd_device_id is not None:
            if ATTR_BRIGHTNESS in kwargs:
                level = int(kwargs[ATTR_BRIGHTNESS])
                await self._controller.dim(self._telldusd_device_id, level)
                self._attr_brightness = level
                await self._async_mirror_command("dim", level)
            else:
                await self._controller.turn_on(self._telldusd_device_id)
                await self._async_mirror_command("turn_on")
        else:
            _LOGGER.warning(
                "Cannot send on command for %s: no telldusd device ID (UID mismatch?)",
                self._device_uid,
            )
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        if self._protocol == PROTOCOL_GENERIC_RF and hasattr(self._controller, "send_raw_command"):
            await self._send_generic_rf_raw("off")
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

    async def _send_generic_rf_raw(self, action: str, brightness: int | None = None) -> None:
        """Send a Generic RF raw OOK pulse command for a light/dimmer.

        For ON/OFF actions, uses the stored timings_on/timings_off.
        For DIM actions, first tries to find a matching dim level in timings_dim_levels,
        otherwise falls back to ON timing.

        Args:
            action: "on", "off", or "dim"
            brightness: Brightness level (0-255) when action is "dim"
        """
        timings = None
        
        if action == "dim" and brightness is not None:
            # Convert brightness (0-255) to percentage (0-100) and find closest level
            percentage = int((brightness / 255) * 100)
            # Try to find the closest dim level we have recorded
            if self._timings_dim_levels:
                closest_level = min(
                    self._timings_dim_levels.keys(),
                    key=lambda x: abs(x - percentage)
                )
                # Use the closest level if it's within 15% of the requested level
                if abs(closest_level - percentage) <= 15:
                    timings = self._timings_dim_levels[closest_level]
                    _LOGGER.debug(
                        "Generic RF dim: using recorded level %d%% for requested %d%%",
                        closest_level, percentage
                    )
        
        if timings is None:
            # Fall back to on/off timings
            if action == "off" and self._timings_off:
                timings = self._timings_off
            elif self._timings_on:
                timings = self._timings_on
        
        if not timings:
            _LOGGER.warning(
                "Generic RF raw TX: no timings stored for %s action=%s",
                self._device_uid, action,
            )
            return

        raw_cmd = generic_rf_build_raw_command(timings, self._repeat_count)
        _LOGGER.info(
            "Generic RF raw TX: uid=%s action=%s brightness=%s timings=%d bytes=%d",
            self._device_uid, action, brightness, len(timings), len(raw_cmd),
        )
        result = await self._controller.send_raw_command(raw_cmd)
        if result == -5:
            _LOGGER.info(
                "Generic RF raw TX: ACK timeout (expected for long TX), hardware should still transmit"
            )
        elif result != 0:
            _LOGGER.warning(
                "Generic RF raw TX failed: uid=%s result=%d", self._device_uid, result
            )
