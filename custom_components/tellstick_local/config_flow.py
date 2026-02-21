"""Config flow for TellStick Local integration."""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult

from .client import TellStickController
from .const import (
    CONF_AUTOMATIC_ADD,
    CONF_COMMAND_PORT,
    CONF_DEVICE_HOUSE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    CONF_EVENT_PORT,
    DEFAULT_AUTOMATIC_ADD,
    DEFAULT_COMMAND_PORT,
    DEFAULT_EVENT_PORT,
    DEFAULT_HOST,
    DEVICE_CATALOG_LABELS,
    DEVICE_CATALOG_MAP,
    DOMAIN,
    ENTRY_TELLSTICK_CONTROLLER,
    WIDGET_PARAMS,
    build_device_uid,
)

SUBENTRY_TYPE_DEVICE = "device"

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_COMMAND_PORT, default=DEFAULT_COMMAND_PORT): vol.All(
            int, vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_EVENT_PORT, default=DEFAULT_EVENT_PORT): vol.All(
            int, vol.Range(min=1, max=65535)
        ),
    }
)


def _build_params_schema(
    widget: int, used_house_codes: set[str] | None = None
) -> vol.Schema:
    """Build a voluptuous schema for the given widget's parameter fields.

    For self-learning devices (fields with ``random=True``), a random value is
    generated that does not collide with any code in *used_house_codes*.
    """
    fields = WIDGET_PARAMS[widget]
    used = used_house_codes or set()
    schema_dict: dict[Any, Any] = {}
    for spec in fields:
        name = spec["name"]
        ptype = spec["type"]
        default = spec.get("default")

        if ptype == "int":
            lo, hi = spec["min"], spec["max"]
            if spec.get("random") and hi > 1:
                # Generate a random value not already used by another device
                for _ in range(100):
                    candidate = secrets.randbelow(hi - lo + 1) + lo
                    if str(candidate) not in used:
                        break
                default = candidate
            schema_dict[vol.Required(name, default=default)] = vol.All(
                int, vol.Range(min=lo, max=hi)
            )
        elif ptype == "letter":
            letters = [chr(c) for c in range(ord(spec["min"]), ord(spec["max"]) + 1)]
            schema_dict[vol.Required(name, default=default)] = vol.In(letters)
        elif ptype == "str":
            schema_dict[vol.Required(name, default=default)] = str
        elif ptype == "bool":
            schema_dict[vol.Required(name, default=default)] = bool

    return vol.Schema(schema_dict)


async def _validate_connection(host: str, command_port: int, event_port: int) -> None:
    """Raise if we cannot reach the telldusd sockets."""
    ctrl = TellStickController(
        host=host, command_port=command_port, event_port=event_port
    )
    try:
        await asyncio.wait_for(ctrl.connect(), timeout=5)
    finally:
        await ctrl.disconnect()


class TellStickLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TellStick Local."""

    VERSION = 1

    def __init__(self) -> None:
        """Init config flow."""
        self._host: str = DEFAULT_HOST
        self._command_port: int = DEFAULT_COMMAND_PORT
        self._event_port: int = DEFAULT_EVENT_PORT
        self._hassio_discovery: bool = False

    async def async_step_hassio(
        self, discovery_info: HassioServiceInfo
    ) -> FlowResult:
        """Handle discovery by the Supervisor (app installed → HA auto-offers setup)."""
        await self.async_set_unique_id(discovery_info.uuid)
        self._abort_if_unique_id_configured()

        self._host = discovery_info.config.get("host", DEFAULT_HOST)
        self._command_port = discovery_info.config.get(
            "port", DEFAULT_COMMAND_PORT
        )
        # Event port is always command port + 1
        self._event_port = self._command_port + 1
        self._hassio_discovery = True

        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm the Supervisor-discovered setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _validate_connection(
                    self._host, self._command_port, self._event_port
                )
            except (asyncio.TimeoutError, OSError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during connection validation")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="TellStick Local",
                    data={
                        CONF_HOST: self._host,
                        CONF_COMMAND_PORT: self._command_port,
                        CONF_EVENT_PORT: self._event_port,
                    },
                    options={
                        CONF_AUTOMATIC_ADD: DEFAULT_AUTOMATIC_ADD,
                        CONF_DEVICES: {},
                    },
                )

        return self.async_show_form(
            step_id="hassio_confirm",
            description_placeholders={
                "addon": "TellStick Local",
                "host": self._host,
                "command_port": str(self._command_port),
                "event_port": str(self._event_port),
            },
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            cmd_port = user_input[CONF_COMMAND_PORT]
            evt_port = user_input[CONF_EVENT_PORT]

            # Prevent duplicate entries for the same host:port
            await self.async_set_unique_id(f"{host}:{cmd_port}")
            self._abort_if_unique_id_configured()

            try:
                await _validate_connection(host, cmd_port, evt_port)
            except asyncio.TimeoutError:
                errors["base"] = "cannot_connect"
            except OSError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during connection validation")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"TellStick Local ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_COMMAND_PORT: cmd_port,
                        CONF_EVENT_PORT: evt_port,
                    },
                    options={
                        CONF_AUTOMATIC_ADD: DEFAULT_AUTOMATIC_ADD,
                        CONF_DEVICES: {},
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TellStickLocalOptionsFlow:
        """Return the options flow."""
        return TellStickLocalOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this handler."""
        return {SUBENTRY_TYPE_DEVICE: TellStickLocalAddDeviceFlow}


class TellStickLocalOptionsFlow(config_entries.OptionsFlow):
    """Handle TellStick Local options."""

    def __init__(self) -> None:
        """Init options flow."""
        self._automatic_add: bool = DEFAULT_AUTOMATIC_ADD
        self._device_type: str = ""
        self._new_device: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show detection mode settings (sprocket → direct form, no menu)."""
        existing_devices: dict[str, Any] = self.config_entry.options.get(
            CONF_DEVICES, {}
        )
        self._automatic_add = self.config_entry.options.get(
            CONF_AUTOMATIC_ADD, DEFAULT_AUTOMATIC_ADD
        )

        if user_input is not None:
            # Save detection mode setting
            self._automatic_add = user_input[CONF_AUTOMATIC_ADD]

            # If user checked "pair a new device", redirect to add_device flow
            if user_input.get("add_device"):
                return await self.async_step_add_device()

            return self.async_create_entry(
                title="",
                data={
                    CONF_AUTOMATIC_ADD: self._automatic_add,
                    CONF_DEVICES: existing_devices,
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTOMATIC_ADD,
                        default=self._automatic_add,
                    ): bool,
                    vol.Optional("add_device", default=False): bool,
                }
            ),
        )

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Pick device type and name."""
        if user_input is not None:
            self._device_type = user_input["device_type"]
            protocol, model, _widget = DEVICE_CATALOG_MAP[self._device_type]
            self._new_device = {
                CONF_DEVICE_NAME: user_input["name"],
                CONF_DEVICE_PROTOCOL: protocol,
                CONF_DEVICE_MODEL: model,
            }
            return await self.async_step_add_device_params()

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required(
                        "device_type",
                        default=DEVICE_CATALOG_LABELS[0],
                    ): vol.In(DEVICE_CATALOG_LABELS),
                }
            ),
        )

    async def async_step_add_device_params(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Enter device-specific parameters with correct ranges."""
        errors: dict[str, str] = {}
        _protocol, _model, widget = DEVICE_CATALOG_MAP[self._device_type]

        if user_input is not None:
            # Validate non-empty string fields
            fields = WIDGET_PARAMS[widget]
            valid = True
            for spec in fields:
                name = spec["name"]
                if spec["type"] == "str" and not str(user_input.get(name, "")).strip():
                    valid = False
            if not valid:
                errors["base"] = "invalid_code"
            else:
                # Store the telldusd parameter values
                params: dict[str, str] = {}
                for spec in fields:
                    name = spec["name"]
                    params[name] = str(user_input[name])

                # Map to house/unit for UID generation (backward compat)
                self._new_device[CONF_DEVICE_HOUSE] = params.get(
                    "house", params.get("code", params.get("system", ""))
                )
                self._new_device[CONF_DEVICE_UNIT] = params.get(
                    "unit", params.get("units", "")
                )
                self._new_device["params"] = params
                return await self.async_step_add_device_confirm()

        # Collect house codes already used by stored devices
        existing_devices: dict[str, Any] = self.config_entry.options.get(
            CONF_DEVICES, {}
        )
        used_house_codes = {
            dev.get(CONF_DEVICE_HOUSE, "")
            for dev in existing_devices.values()
            if dev.get(CONF_DEVICE_HOUSE)
        }

        schema = _build_params_schema(widget, used_house_codes)
        return self.async_show_form(
            step_id="add_device_params",
            data_schema=schema,
            description_placeholders={
                "device_type": self._device_type,
            },
            errors=errors,
        )

    async def async_step_add_device_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Send the RF teach/pairing signal after user puts device in learn mode."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                entry_data = self.hass.data[DOMAIN].get(
                    self.config_entry.entry_id, {}
                )
                controller: TellStickController | None = entry_data.get(
                    ENTRY_TELLSTICK_CONTROLLER
                )
                if controller is None:
                    raise RuntimeError("Controller not available")

                # Use actual telldusd parameter names from the widget
                params = dict(self._new_device.get("params", {}))
                if not params:
                    # Backward compat: fall back to house/unit
                    if house := self._new_device.get(CONF_DEVICE_HOUSE):
                        params["house"] = house
                    if unit := self._new_device.get(CONF_DEVICE_UNIT):
                        params["unit"] = unit

                telldusd_id = await controller.add_device(
                    self._new_device[CONF_DEVICE_NAME],
                    self._new_device[CONF_DEVICE_PROTOCOL],
                    self._new_device.get(CONF_DEVICE_MODEL, ""),
                    params,
                )
                # Send the RF teach signal – receiver must already be in learn mode
                await controller.turn_on(telldusd_id)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Failed to teach device")
                errors["base"] = "teach_failed"
            else:
                device_uid = build_device_uid(
                    self._new_device[CONF_DEVICE_PROTOCOL],
                    self._new_device.get(CONF_DEVICE_MODEL, ""),
                    self._new_device.get(CONF_DEVICE_HOUSE, ""),
                    self._new_device.get(CONF_DEVICE_UNIT, ""),
                )
                existing_devices = dict(
                    self.config_entry.options.get(CONF_DEVICES, {})
                )
                existing_devices[device_uid] = {
                    CONF_DEVICE_NAME: self._new_device[CONF_DEVICE_NAME],
                    CONF_DEVICE_PROTOCOL: self._new_device[CONF_DEVICE_PROTOCOL],
                    CONF_DEVICE_MODEL: self._new_device.get(CONF_DEVICE_MODEL, ""),
                    CONF_DEVICE_HOUSE: self._new_device.get(CONF_DEVICE_HOUSE, ""),
                    CONF_DEVICE_UNIT: self._new_device.get(CONF_DEVICE_UNIT, ""),
                    "params": self._new_device.get("params", {}),
                }
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_AUTOMATIC_ADD: self._automatic_add,
                        CONF_DEVICES: existing_devices,
                    },
                )

        return self.async_show_form(
            step_id="add_device_confirm",
            description_placeholders={
                "name": self._new_device.get(CONF_DEVICE_NAME, ""),
                "protocol": self._new_device.get(CONF_DEVICE_PROTOCOL, ""),
                "model": self._new_device.get(CONF_DEVICE_MODEL, ""),
                "house": self._new_device.get(CONF_DEVICE_HOUSE, ""),
                "unit": self._new_device.get(CONF_DEVICE_UNIT, ""),
            },
            errors=errors,
        )


