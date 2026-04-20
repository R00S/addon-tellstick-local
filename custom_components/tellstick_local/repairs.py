"""Repair flows for TellStick Local."""
from __future__ import annotations

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import ISSUE_RESTART


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a fix flow for a TellStick Local repair issue."""
    if issue_id == ISSUE_RESTART:
        return RestartRepairFlow()
    raise ValueError(f"Unknown issue {issue_id}")


class RestartRepairFlow(RepairsFlow):
    """Repair flow that restarts Home Assistant to load the new integration."""

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> dict:
        """Show a confirmation form; restart HA when the user confirms."""
        if user_input is not None:
            # Schedule restart after this coroutine returns so the flow
            # response reaches the frontend before HA shuts down.
            self.hass.async_create_task(
                self.hass.services.async_call("homeassistant", "restart")
            )
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))
