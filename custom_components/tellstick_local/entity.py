"""Base entity for TellStick Local integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, ENTRY_MIRRORS

_LOGGER = logging.getLogger(__name__)

# Delay between primary RF command and mirror RF command.
#
# telldusd (Duo path) returns from turn_on/turn_off as soon as the TellStick
# firmware ACKs the USB command (~2–5 ms), which happens BEFORE the RF
# transmission is complete.  Without this delay, the mirror fires while the
# primary is still on air, causing 433 MHz RF collision → receiver decodes
# nothing and the user sees "the Duo is sending corrupted packets".
#
# Sizing: rtl_433 captures of a real Comen press show one full transmission
# burst is up to ~533 ms wide (telldus-core ProtocolNexa repeats × pulse
# train).  At the previous value of 0.35 s the ZNet started TX'ing while the
# Duo had ~170 ms of repeats remaining, jamming all overlapping frames at
# the receiver.  0.7 s clears the burst with comfortable margin and is also
# safe for shorter arctech/everflourish bursts (no harm in a longer wait —
# the mirror is a reinforcement TX, not the primary).
#
# The ZNet UDP path also returns before RF is done (no UDP ACK), so the delay
# is needed for all backend combinations.
_RF_MIRROR_DELAY_S = 0.7


async def async_mirror_raw_command(
    hass: Any,
    entry_id: str,
    raw_command: bytes,
    device_uid: str = "",
) -> None:
    """Send a raw pulse command to every mirror controller of an entry.

    The protocols this integration builds itself — Luxorparts, Generic RF
    record & replay and the Tuya/Kjell curtain motor — are transmitted with
    ``send_raw_command()``, which bypasses device registration entirely.  The
    regular mirror dispatcher passes a telldusd id or a protocol/model/house/
    unit dict, neither of which can carry them, so the pulse train is
    replicated here instead.  It is device-independent: the frame already
    contains everything the receiver needs.

    A mirror that cannot transmit raw pulses (ZNet / Net v2) is skipped by its
    own ``send_raw_command`` (called with ``quiet=True`` so a mirror on an
    unsupported backend does not warn on every command).
    """
    if hass is None or not raw_command:
        return
    entry_data = hass.data.get(DOMAIN, {}).get(entry_id, {})
    mirrors: list[dict[str, Any]] = entry_data.get(ENTRY_MIRRORS, [])
    if not mirrors:
        return
    # Same RF collision window as the per-device mirror dispatch.
    await asyncio.sleep(_RF_MIRROR_DELAY_S)
    for mirror in mirrors:
        controller = mirror.get("controller")
        send_raw = getattr(controller, "send_raw_command", None)
        if send_raw is None:
            _LOGGER.debug(
                "Mirror %s cannot send raw pulses; skipping %s",
                mirror.get("entry_id", "?"),
                device_uid or "raw device",
            )
            continue
        try:
            result = await send_raw(raw_command, quiet=True)
        except Exception:  # noqa: BLE001 — one bad mirror must not break the rest
            _LOGGER.warning(
                "Mirror raw command failed for %s",
                device_uid or "raw device",
                exc_info=True,
            )
            continue
        # -5 is the Duo's expected ACK timeout for a long raw transmission.
        if result not in (0, -5):
            _LOGGER.debug(
                "Mirror raw TX for %s returned %s",
                device_uid or "raw device",
                result,
            )


class TellStickEntity(RestoreEntity):
    """Base entity for TellStick devices."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        device_uid: str,
        name: str,
        protocol: str,
        model: str,
        house: str = "",
        unit: str = "",
        manufacturer: str = "",
        group_uid: str | None = None,
    ) -> None:
        """Initialize a TellStick entity."""
        self._entry_id = entry_id
        self._device_uid = device_uid
        self._protocol = protocol
        self._model = model
        self._house = house
        self._unit = unit

        self._attr_unique_id = f"{entry_id}_{device_uid}"
        if group_uid:
            # Entity belongs to a shared group device.  The entity name is the
            # device's own name; the HA device is identified by the group name.
            # With _attr_has_entity_name=True, the frontend shows
            # "{group_uid} {name}" (e.g. "Living Room Switch A").
            self._attr_name = name
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_group_{group_uid}")},
                name=group_uid,
                manufacturer=manufacturer or None,
            )
        else:
            # Standalone: entity IS the "main feature" of its own device.
            # With _attr_has_entity_name=True and name=None, the friendly name
            # is just the device name (e.g. "Boxarna"), not "Boxarna Boxarna".
            # Sensor subclasses override this to set a type suffix ("Temperature").
            self._attr_name = None
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_{device_uid}")},
                name=name,
                manufacturer=manufacturer or None,
                model=f"{protocol}/{model}" if model else protocol,
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose device parameters as state attributes for debugging."""
        attrs: dict[str, Any] = {
            "device_uid": self._device_uid,
            "protocol": self._protocol,
            "model": self._model,
        }
        if self._house:
            attrs["house"] = self._house
        if self._unit:
            attrs["unit"] = self._unit
        return attrs

    async def _async_mirror_command(self, command: str, *args: Any) -> None:
        """Send a command to all mirror controllers for this device.

        Mirror TellStick entries share the primary's devices and replicate
        commands.  The device_id argument is resolved from each mirror's
        device_id_map, so callers pass only additional arguments
        (e.g. brightness level for ``dim``).

        A short RF collision-avoidance delay is inserted before the first mirror
        command.  Both the Duo (telldusd TCP) and ZNet (UDP) return from their
        send call before the 433 MHz RF transmission is complete, so without the
        delay the mirror would transmit simultaneously with the primary, causing
        RF interference that prevents the receiver from decoding either signal.
        """
        if not self.hass:
            return
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        mirrors: list[dict[str, Any]] = entry_data.get(ENTRY_MIRRORS, [])
        if not mirrors:
            return
        # Wait for the primary RF transmission to finish before the mirror sends.
        await asyncio.sleep(_RF_MIRROR_DELAY_S)
        for mirror in mirrors:
            mirror_device_id = mirror["device_id_map"].get(self._device_uid)
            if mirror_device_id is None:
                continue
            try:
                method = getattr(mirror["controller"], command)
                await method(mirror_device_id, *args)
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Mirror command %s failed for %s",
                    command, self._device_uid,
                    exc_info=True,
                )

    async def _async_mirror_raw(self, raw_command: bytes) -> None:
        """Send a raw pulse command to every mirror controller.

        Used by the platforms that build their own pulse trains (Luxorparts,
        Generic RF replay, curtain motor) instead of going through a protocol
        registration — see :func:`async_mirror_raw_command`.
        """
        await async_mirror_raw_command(
            self.hass, self._entry_id, raw_command, self._device_uid
        )
