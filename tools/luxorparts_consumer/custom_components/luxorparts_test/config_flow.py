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
            # NumberSelector hands back floats (11.0); the protocol is integer.
            data = {
                **user_input,
                "house": int(user_input["house"]),
                "unit": int(user_input["unit"]),
            }
            await self.async_set_unique_id(
                f"{data['transmitter']}_{data['house']}_{data['unit']}"
            )
            self._abort_if_unique_id_configured()
            title = f"Luxorparts {data['house']}/{data['unit']}"
            return self.async_create_entry(title=title, data=data)

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
