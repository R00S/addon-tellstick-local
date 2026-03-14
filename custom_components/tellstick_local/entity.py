"""Base entity for TellStick Local integration."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN


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
    ) -> None:
        """Initialize a TellStick entity."""
        self._entry_id = entry_id
        self._device_uid = device_uid
        self._protocol = protocol
        self._model = model
        self._house = house
        self._unit = unit

        self._attr_unique_id = f"{entry_id}_{device_uid}"
        # Set name to None so HA treats this entity as the "main feature" of
        # the device.  With _attr_has_entity_name=True and name=None, the
        # friendly name is just the device name (e.g. "Boxarna"), rather than
        # the duplicated "{device} {entity}" form (e.g. "Boxarna Boxarna").
        # Sensor subclasses override this to set a type suffix ("Temperature").
        self._attr_name = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{device_uid}")},
            name=name,
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
