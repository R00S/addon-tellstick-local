"""Config flow for the Luxorparts test socket."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import DOMAIN


def _transmitters(hass) -> list[str]:
    """Return every radio_frequency entity that looks like a transmitter."""
    ent_reg = er.async_get(hass)
    found: list[str] = []
    for entry in ent_reg.entities.values():
        if entry.domain != "radio_frequency" or entry.disabled_by is not None:
            continue
        found.append(entry.entity_id)
    return sorted(found)


class LuxorpartsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for a transmitter and the house/unit code to pair with."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the single setup step."""
        transmitters = _transmitters(self.hass)
        if not transmitters:
            return self.async_abort(reason="no_transmitters")

        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input['transmitter']}_{user_input['house']}"
                f"_{user_input['unit']}"
            )
            self._abort_if_unique_id_configured()
            title = f"Luxorparts {user_input['house']}/{user_input['unit']}"
            return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required("transmitter", default=transmitters[0]): (
                    EntitySelector(
                        EntitySelectorConfig(
                            include_entities=transmitters,
                            multiple=False,
                        )
                    )
                ),
                vol.Required("house", default=1): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=65535, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required("unit", default=1): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=16, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
