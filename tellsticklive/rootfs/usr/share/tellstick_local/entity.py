"""Base entity for TellStick Local integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, ENTRY_MIRRORS

_LOGGER = logging.getLogger(__name__)


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
        """
        if not self.hass:
            return
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        mirrors: list[dict[str, Any]] = entry_data.get(ENTRY_MIRRORS, [])
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
