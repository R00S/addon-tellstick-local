"""Config flow for TellStick Local integration."""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.hassio import HassioServiceInfo
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
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    PROTOCOL_DEFAULT_MODELS,
    TX_PROTOCOLS,
    build_device_uid,
)

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
        return TellStickLocalOptionsFlow(config_entry)


class TellStickLocalOptionsFlow(config_entries.OptionsFlow):
    """Handle TellStick Local options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Init options flow."""
        self.config_entry = config_entry
        self._automatic_add: bool = config_entry.options.get(
            CONF_AUTOMATIC_ADD, DEFAULT_AUTOMATIC_ADD
        )
        self._new_device: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        existing_devices: dict[str, Any] = self.config_entry.options.get(
            CONF_DEVICES, {}
        )

        if user_input is not None:
            self._automatic_add = user_input[CONF_AUTOMATIC_ADD]
            if user_input.get("add_device"):
                return await self.async_step_add_device()
            if user_input.get("remove_device") and existing_devices:
                return await self.async_step_remove_device()
            return self.async_create_entry(
                title="",
                data={
                    CONF_AUTOMATIC_ADD: self._automatic_add,
                    CONF_DEVICES: existing_devices,
                },
            )

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_AUTOMATIC_ADD,
                default=self._automatic_add,
            ): bool,
            vol.Optional("add_device", default=False): bool,
        }
        if existing_devices:
            schema_dict[vol.Optional("remove_device", default=False)] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect details for a new self-learning device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            protocol = user_input["protocol"]
            model = user_input.get("model", PROTOCOL_DEFAULT_MODELS.get(protocol, ""))
            house = user_input["house"].strip()
            unit = user_input["unit"].strip()
            if not house or not unit:
                errors["base"] = "invalid_code"
            else:
                self._new_device = {
                    CONF_DEVICE_NAME: user_input["name"],
                    CONF_DEVICE_PROTOCOL: protocol,
                    CONF_DEVICE_MODEL: model,
                    CONF_DEVICE_HOUSE: house,
                    CONF_DEVICE_UNIT: unit,
                }
                return await self.async_step_add_device_confirm()

        # Generate a random 26-bit house code suitable for arctech selflearning
        # (valid range is 1–67108863, i.e. 1–(2^26 - 1))
        default_house = str(secrets.randbelow(67108863) + 1)

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required("protocol", default="arctech"): vol.In(TX_PROTOCOLS),
                    vol.Optional(
                        "model",
                        default=PROTOCOL_DEFAULT_MODELS.get("arctech", ""),
                    ): str,
                    vol.Required("house", default=default_house): str,
                    vol.Required("unit", default="1"): str,
                }
            ),
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

                params: dict[str, str] = {}
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
                    self._new_device[CONF_DEVICE_HOUSE],
                    self._new_device[CONF_DEVICE_UNIT],
                )
                existing_devices = dict(
                    self.config_entry.options.get(CONF_DEVICES, {})
                )
                existing_devices[device_uid] = {
                    CONF_DEVICE_NAME: self._new_device[CONF_DEVICE_NAME],
                    CONF_DEVICE_PROTOCOL: self._new_device[CONF_DEVICE_PROTOCOL],
                    CONF_DEVICE_MODEL: self._new_device.get(CONF_DEVICE_MODEL, ""),
                    CONF_DEVICE_HOUSE: self._new_device[CONF_DEVICE_HOUSE],
                    CONF_DEVICE_UNIT: self._new_device[CONF_DEVICE_UNIT],
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

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a manually-added device."""
        existing_devices: dict[str, Any] = self.config_entry.options.get(
            CONF_DEVICES, {}
        )
        errors: dict[str, str] = {}

        if user_input is not None:
            uid_to_remove = user_input.get("device")
            if uid_to_remove and uid_to_remove in existing_devices:
                # Best-effort removal from telldusd (non-fatal if it fails)
                try:
                    entry_data = self.hass.data[DOMAIN].get(
                        self.config_entry.entry_id, {}
                    )
                    controller: TellStickController | None = entry_data.get(
                        ENTRY_TELLSTICK_CONTROLLER
                    )
                    device_id_map: dict[str, int] = entry_data.get(
                        ENTRY_DEVICE_ID_MAP, {}
                    )
                    if controller and uid_to_remove in device_id_map:
                        await controller.remove_device(device_id_map[uid_to_remove])
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "Could not remove device %s from telldusd", uid_to_remove
                    )

                new_devices = {
                    k: v
                    for k, v in existing_devices.items()
                    if k != uid_to_remove
                }
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_AUTOMATIC_ADD: self._automatic_add,
                        CONF_DEVICES: new_devices,
                    },
                )
            errors["base"] = "invalid_selection"

        device_options = {
            uid: data.get(CONF_DEVICE_NAME, uid)
            for uid, data in existing_devices.items()
        }

        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): vol.In(device_options),
                }
            ),
            errors=errors,
        )
