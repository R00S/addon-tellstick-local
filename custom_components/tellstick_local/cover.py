"""Cover platform for TellStick Local integration (motorised blinds/screens).

Handles protocols that use UP/DOWN/STOP commands instead of ON/OFF:
  - ``hasta``   — Hasta motorised blinds (selflearning and selflearningv2)
  - ``brateck`` — Brateck motorised projector screens and blinds

Both protocols support three commands:
  - UP   → open/raise
  - DOWN → close/lower
  - STOP → halt mid-travel

Hasta remotes have exactly three buttons (Up, Down, Stop) which are received
as TDRawDeviceEvents with method:up / method:down / method:stop.  The cover
entity state is updated optimistically from these remote-button events.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

from .client import RawDeviceEvent, TellStickController
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
)
from .entity import TellStickEntity

_LOGGER = logging.getLogger(__name__)

# Protocols whose devices use UP/DOWN/STOP instead of ON/OFF.
# Source: ProtocolHasta.cpp and ProtocolBrateck.cpp — methods() returns
# TELLSTICK_UP | TELLSTICK_DOWN | TELLSTICK_STOP, not TELLSTICK_TURNON.
_COVER_PROTOCOLS = {"hasta", "brateck"}


def _is_cover(protocol: str) -> bool:
    """Return True if this protocol uses UP/DOWN/STOP (cover entity)."""
    return protocol.lower() in _COVER_PROTOCOLS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TellStick cover entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    controller: TellStickController = entry_data[ENTRY_TELLSTICK_CONTROLLER]
    device_id_map: dict[str, Any] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)

    backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
    manufacturer = "TellStick Net/ZNet" if backend != BACKEND_DUO else "TellStick Duo"

    known: set[str] = set()

    # Pre-create entities for stored (manually-added) cover devices
    stored_entities: list[TellStickCover] = []
    for device_uid, device_cfg in entry.options.get(CONF_DEVICES, {}).items():
        protocol = device_cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = device_cfg.get(CONF_DEVICE_MODEL, "")
        if not _is_cover(protocol):
            continue
        known.add(device_uid)
        stored_entities.append(
            TellStickCover(
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
            if er.async_get(hass).async_get_entity_id("cover", DOMAIN, unique_id) is not None:
                return  # entity still active — skip duplicate
            known.discard(uid)  # entity was deleted — fall through to create
        if not _is_cover(protocol):
            return
        known.add(uid)
        stored = entry.options.get(CONF_DEVICES, {}).get(uid, {})
        name = stored.get(CONF_DEVICE_NAME) or f"TellStick {uid}"
        entity = TellStickCover(
            entry_id=entry.entry_id,
            device_uid=uid,
            name=name,
            protocol=protocol,
            model=model,
            controller=controller,
            device_id=device_id_map.get(uid),
            house=params.get("house", ""),
            unit=params.get("unit", ""),
            manufacturer=manufacturer,
        )
        async_add_entities([entity])

    entry.async_on_unload(
        async_dispatcher_connect(hass, new_device_signal, _async_new_device)
    )


class TellStickCover(TellStickEntity, CoverEntity):
    """Representation of a TellStick-controlled blind or motorised screen.

    Hasta remotes have three buttons: Up, Down, Stop.  The entity state is
    updated optimistically when a remote event is received, or when the user
    sends a command from Home Assistant.  Because Hasta/Brateck do not report
    position, ``is_closed`` is set to ``None`` (unknown) until a command is
    observed.
    """

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

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
    ) -> None:
        """Initialize a TellStick cover entity."""
        super().__init__(
            entry_id=entry_id,
            device_uid=device_uid,
            name=name,
            protocol=protocol,
            model=model,
            house=house,
            unit=unit,
            manufacturer=manufacturer,
        )
        self._controller = controller
        self._telldusd_device_id = device_id
        # None = unknown; True = closed; False = open
        self._attr_is_closed: bool | None = None

    @property
    def device_class(self) -> CoverDeviceClass:
        """Return the device class based on protocol."""
        if self._protocol.lower() == "brateck":
            return CoverDeviceClass.SHADE
        return CoverDeviceClass.BLIND

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to events."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            if last.state == "open":
                self._attr_is_closed = False
            elif last.state == "closed":
                self._attr_is_closed = True

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_EVENT.format(self._entry_id),
                self._handle_event,
            )
        )

    @callback
    def _handle_event(self, event: Any) -> None:
        """Update state from an incoming RF event (e.g. remote button press)."""
        if not isinstance(event, RawDeviceEvent):
            return
        if event.device_id != self._device_uid:
            return
        method = event.params.get("method", "")
        if method == "up":
            self._attr_is_closed = False
        elif method == "down":
            self._attr_is_closed = True
        # "stop" leaves the position unknown — don't update is_closed
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (send UP command)."""
        if self._telldusd_device_id is not None:
            await self._controller.up(self._telldusd_device_id)
        else:
            _LOGGER.warning(
                "Cannot send up command for %s: no telldusd device ID",
                self._device_uid,
            )
        await self._async_mirror_command("up")
        self._attr_is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (send DOWN command)."""
        if self._telldusd_device_id is not None:
            await self._controller.down(self._telldusd_device_id)
        else:
            _LOGGER.warning(
                "Cannot send down command for %s: no telldusd device ID",
                self._device_uid,
            )
        await self._async_mirror_command("down")
        self._attr_is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        if self._telldusd_device_id is not None:
            await self._controller.stop(self._telldusd_device_id)
        else:
            _LOGGER.warning(
                "Cannot send stop command for %s: no telldusd device ID",
                self._device_uid,
            )
        await self._async_mirror_command("stop")
