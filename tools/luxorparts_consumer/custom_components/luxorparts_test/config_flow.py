"""Config flow for the Luxorparts test socket."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import luxorparts
from .const import DOMAIN


def _transmitters(hass) -> list[str]:
    """Return every radio_frequency entity that can send."""
    ent_reg = er.async_get(hass)
    return sorted(
        entry.entity_id
        for entry in ent_reg.entities.values()
        if entry.domain == "radio_frequency" and entry.disabled_by is None
    )


class LuxorpartsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for a transmitter and one of the 24 verified devices."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the single setup step."""
        transmitters = _transmitters(self.hass)
        if not transmitters:
            return self.async_abort(reason="no_transmitters")

        if user_input is not None:
            data = {
                "transmitter": user_input["transmitter"],
                "device": int(user_input["device"]),
            }
            await self.async_set_unique_id(
                f"{data['transmitter']}_{data['device']}"
            )
            self._abort_if_unique_id_configured()
            title = f"Luxorparts LPD {data['device']}"
            return self.async_create_entry(title=title, data=data)

        options = [
            SelectOptionDict(value=str(number), label=label)
            for number, label in luxorparts.LABELS.items()
        ]
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
                vol.Required("device", default="11"): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
