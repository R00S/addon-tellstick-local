"""Config flow for TellStick Local integration."""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback

try:
    from homeassistant.config_entries import (
        ConfigSubentryFlow,
        SubentryFlowResult,
    )
except ImportError:
    ConfigSubentryFlow = None  # type: ignore[assignment,misc]
    SubentryFlowResult = dict  # type: ignore[assignment,misc]
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult

from .client import RawDeviceEvent, SensorEvent, TellStickController
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
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    SIGNAL_NEW_DEVICE,
    WIDGET_PARAMS,
    build_device_uid,
    normalize_rf_model,
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
        self._rf_discovery: dict[str, Any] = {}

    async def async_step_hassio(
        self, discovery_info: HassioServiceInfo
    ) -> FlowResult:
        """Handle discovery by the Supervisor (app installed → HA auto-offers setup)."""
        await self.async_set_unique_id(discovery_info.uuid)
        self._abort_if_unique_id_configured()

        # discovery_info.slug is the HAOS Supervisor internal hostname
        # (e.g. "e9305338-tellsticklive" for custom-repo apps).
        self._host = discovery_info.slug
        self._command_port = DEFAULT_COMMAND_PORT
        self._event_port = DEFAULT_EVENT_PORT
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
                        CONF_DEVICES: {},
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    # -----------------------------------------------------------------
    # RF device discovery (BLE-like UX)
    # -----------------------------------------------------------------

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """Handle discovery of a new 433 MHz device via RF signal.

        Fired by __init__._handle_raw_event / _handle_sensor_event when an
        unknown device sends an RF signal.  Shows in the 'Discovered' section
        of Settings → Devices & Services, just like BLE devices.
        """
        self._rf_discovery = discovery_info
        device_uid = discovery_info["device_uid"]

        # Deduplicate: one discovery flow per device UID
        await self.async_set_unique_id(f"rf_{device_uid}")
        self._abort_if_unique_id_in_progress()

        # Abort if the device was already added while this flow was pending
        for existing_entry in self._async_current_entries():
            if device_uid in existing_entry.options.get(CONF_DEVICES, {}):
                return self.async_abort(reason="already_added")

        # Set title for the "Discovered" card in the UI
        protocol = discovery_info.get("protocol", "")
        model = discovery_info.get("model", "")
        dev_type = discovery_info.get("type", "device")
        if dev_type == "sensor":
            title = f"Sensor {discovery_info.get('sensor_id', '')} ({protocol}/{model})"
        else:
            house = discovery_info.get("house", "")
            unit = discovery_info.get("unit", "")
            title = f"{protocol}/{model} (house: {house}, unit: {unit})"
        self.context["title_placeholders"] = {"name": title}

        return await self.async_step_confirm_rf_device()

    async def async_step_confirm_rf_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show confirmation form for a discovered 433 MHz device."""
        info = self._rf_discovery
        dev_type = info.get("type", "device")

        if dev_type == "sensor":
            sensor_id = info.get("sensor_id", "")
            suffix = {1: "temperature", 2: "humidity"}.get(
                info.get("data_type", 0), "sensor"
            )
            default_name = f"TellStick sensor {sensor_id} {suffix}"
        else:
            default_name = f"TellStick {info['device_uid']}"

        if user_input is not None:
            # Find the existing config entry to add the device to
            entry_id = info["entry_id"]
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                return self.async_abort(reason="entry_not_found")

            device_uid = info["device_uid"]
            name = user_input.get("name", default_name)

            # Register RF device with telldusd so on/off commands work
            entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
            controller: TellStickController | None = entry_data.get(
                ENTRY_TELLSTICK_CONTROLLER
            )
            device_id_map: dict[str, int] = entry_data.get(
                ENTRY_DEVICE_ID_MAP, {}
            )

            # Store the device in entry.options
            existing_devices = dict(entry.options.get(CONF_DEVICES, {}))
            if dev_type == "sensor":
                existing_devices[device_uid] = {
                    CONF_DEVICE_NAME: name,
                    CONF_DEVICE_PROTOCOL: info.get("protocol", ""),
                    CONF_DEVICE_MODEL: info.get("model", ""),
                    "sensor_id": info.get("sensor_id"),
                    "data_type": info.get("data_type"),
                }
            else:
                existing_devices[device_uid] = {
                    CONF_DEVICE_NAME: name,
                    CONF_DEVICE_PROTOCOL: info.get("protocol", ""),
                    CONF_DEVICE_MODEL: info.get("model", ""),
                    CONF_DEVICE_HOUSE: info.get("house", ""),
                    CONF_DEVICE_UNIT: info.get("unit", ""),
                }
                # Register with telldusd so commands work immediately
                if controller:
                    try:
                        protocol = info.get("protocol", "")
                        model_str = info.get("model", "")
                        house_str = info.get("house", "")
                        unit_str = info.get("unit", "")
                        telldusd_id = await controller.find_or_add_device(
                            name, protocol, model_str, house_str, unit_str,
                        )
                        device_id_map[device_uid] = telldusd_id
                    except Exception:  # noqa: BLE001
                        _LOGGER.warning(
                            "Could not register discovered device %s with telldusd",
                            device_uid,
                        )
            new_options = dict(entry.options)
            new_options[CONF_DEVICES] = existing_devices
            self.hass.config_entries.async_update_entry(
                entry, options=new_options
            )

            # Fire SIGNAL_NEW_DEVICE so platforms create the entity immediately
            if dev_type == "sensor":
                synthetic = SensorEvent(
                    protocol=info.get("protocol", ""),
                    model=info.get("model", ""),
                    sensor_id=info.get("sensor_id", 0),
                    data_type=info.get("data_type", 0),
                    value="",
                )
            else:
                protocol = info.get("protocol", "")
                model_str = info.get("model", "")
                house_str = info.get("house", "")
                unit_str = info.get("unit", "")
                synthetic = RawDeviceEvent(
                    raw=(
                        f"class:command;protocol:{protocol};model:{model_str};"
                        f"house:{house_str};unit:{unit_str};method:turnon;"
                    ),
                    controller_id=0,
                )
            async_dispatcher_send(
                self.hass,
                SIGNAL_NEW_DEVICE.format(entry.entry_id),
                synthetic,
            )

            return self.async_abort(reason="device_added")

        return self.async_show_form(
            step_id="confirm_rf_device",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=default_name): str,
                }
            ),
            description_placeholders={
                "protocol": info.get("protocol", ""),
                "model": info.get("model", ""),
                "house": info.get("house", ""),
                "unit": info.get("unit", ""),
                "device_uid": info["device_uid"],
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return TellStickLocalOptionsFlow()

    if ConfigSubentryFlow is not None:

        @classmethod  # type: ignore[misc]
        @callback
        def async_get_supported_subentry_types(
            cls, config_entry: ConfigEntry
        ) -> dict[str, type[ConfigSubentryFlow]]:
            """Return subentries supported by this handler."""
            return {SUBENTRY_TYPE_DEVICE: TellStickLocalAddDeviceFlow}


class TellStickLocalOptionsFlow(config_entries.OptionsFlow):
    """Handle options for TellStick Local."""

    _edit_uid: str = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show options menu."""
        devices = self.config_entry.options.get(CONF_DEVICES, {})
        menu_options = ["settings"]
        if devices:
            menu_options.append("edit_device")
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure integration settings."""
        if user_input is not None:
            new_options = dict(self.config_entry.options)
            new_options[CONF_AUTOMATIC_ADD] = user_input[CONF_AUTOMATIC_ADD]
            return self.async_create_entry(title="", data=new_options)

        current = self.config_entry.options.get(
            CONF_AUTOMATIC_ADD, DEFAULT_AUTOMATIC_ADD
        )
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTOMATIC_ADD, default=current): bool,
                }
            ),
        )

    async def async_step_edit_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a device to view/edit."""
        devices = self.config_entry.options.get(CONF_DEVICES, {})
        if not devices:
            return self.async_abort(reason="no_devices")

        if user_input is not None:
            self._edit_uid = user_input["device"]
            return await self.async_step_device_detail()

        # Build device selector: "name (protocol/model house:X unit:Y)"
        labels: dict[str, str] = {}
        for uid, cfg in devices.items():
            name = cfg.get(CONF_DEVICE_NAME, uid)
            protocol = cfg.get(CONF_DEVICE_PROTOCOL, "")
            model = cfg.get(CONF_DEVICE_MODEL, "")
            house = cfg.get(CONF_DEVICE_HOUSE, "")
            unit = cfg.get(CONF_DEVICE_UNIT, "")
            detail = f"{protocol}/{model}" if model else protocol
            if house:
                detail += f" house:{house}"
            if unit:
                detail += f" unit:{unit}"
            labels[uid] = f"{name} ({detail})" if detail else name

        return self.async_show_form(
            step_id="edit_device",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): vol.In(labels),
                }
            ),
        )

    async def async_step_device_detail(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """View and edit device house/unit codes."""
        uid = self._edit_uid
        devices = dict(self.config_entry.options.get(CONF_DEVICES, {}))
        cfg = dict(devices.get(uid, {}))

        if user_input is not None:
            # Update the device config
            cfg[CONF_DEVICE_NAME] = user_input["name"]
            if "house" in user_input:
                cfg[CONF_DEVICE_HOUSE] = str(user_input["house"])
            if "unit" in user_input:
                cfg[CONF_DEVICE_UNIT] = str(user_input["unit"])
            # Update params dict if present
            if "params" in cfg:
                params = dict(cfg["params"])
                if "house" in user_input:
                    params["house"] = str(user_input["house"])
                if "unit" in user_input:
                    params["unit"] = str(user_input["unit"])
                cfg["params"] = params
            devices[uid] = cfg
            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = devices
            return self.async_create_entry(title="", data=new_options)

        name = cfg.get(CONF_DEVICE_NAME, uid)
        house = cfg.get(CONF_DEVICE_HOUSE, "")
        unit = cfg.get(CONF_DEVICE_UNIT, "")
        protocol = cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = cfg.get(CONF_DEVICE_MODEL, "")

        schema_dict: dict[Any, Any] = {
            vol.Required("name", default=name): str,
        }
        # Only show house/unit for non-sensor devices
        if not uid.startswith("sensor_"):
            schema_dict[vol.Optional("house", default=house)] = str
            schema_dict[vol.Optional("unit", default=unit)] = str

        return self.async_show_form(
            step_id="device_detail",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "device_uid": uid,
                "protocol": protocol,
                "model": model,
            },
        )


_SubentryBase = ConfigSubentryFlow if ConfigSubentryFlow is not None else config_entries.OptionsFlow


class TellStickLocalAddDeviceFlow(_SubentryBase):  # type: ignore[misc]
    """Handle adding a 433 MHz device via the 'Add device' button."""

    _device_type: str = ""
    _new_device: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 1: Pick device type and name."""
        if user_input is not None:
            self._device_type = user_input["device_type"]
            protocol, model, _widget = DEVICE_CATALOG_MAP[self._device_type]
            self._new_device = {
                CONF_DEVICE_NAME: user_input["name"],
                CONF_DEVICE_PROTOCOL: protocol,
                CONF_DEVICE_MODEL: model,
            }
            return await self.async_step_params()

        return self.async_show_form(
            step_id="user",
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

    async def async_step_params(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
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
                return await self.async_step_confirm()

        # Collect house codes already used by stored devices
        entry = self._get_entry()
        existing_devices: dict[str, Any] = entry.options.get(CONF_DEVICES, {})
        used_house_codes = {
            dev.get(CONF_DEVICE_HOUSE, "")
            for dev in existing_devices.values()
            if dev.get(CONF_DEVICE_HOUSE)
        }

        schema = _build_params_schema(widget, used_house_codes)
        return self.async_show_form(
            step_id="params",
            data_schema=schema,
            description_placeholders={
                "device_type": self._device_type,
            },
            errors=errors,
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Send the RF teach/pairing signal after user puts device in learn mode."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entry = self._get_entry()
            try:
                entry_data = self.hass.data[DOMAIN].get(entry.entry_id, {})
                controller: TellStickController | None = entry_data.get(
                    ENTRY_TELLSTICK_CONTROLLER
                )
                if controller is None:
                    raise RuntimeError("Controller not available")

                # Use actual telldusd parameter names from the widget
                params = dict(self._new_device.get("params", {}))
                if not params:
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
                await controller.learn(telldusd_id)
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

                # Store telldusd_id in runtime map so the entity can
                # send commands immediately (without a restart)
                device_id_map: dict[str, int] = entry_data.get(
                    ENTRY_DEVICE_ID_MAP, {}
                )
                device_id_map[device_uid] = telldusd_id

                # Store in entry.options[CONF_DEVICES]
                existing_devices = dict(entry.options.get(CONF_DEVICES, {}))
                existing_devices[device_uid] = {
                    CONF_DEVICE_NAME: self._new_device[CONF_DEVICE_NAME],
                    CONF_DEVICE_PROTOCOL: self._new_device[CONF_DEVICE_PROTOCOL],
                    CONF_DEVICE_MODEL: self._new_device.get(CONF_DEVICE_MODEL, ""),
                    CONF_DEVICE_HOUSE: self._new_device.get(CONF_DEVICE_HOUSE, ""),
                    CONF_DEVICE_UNIT: self._new_device.get(CONF_DEVICE_UNIT, ""),
                    "params": self._new_device.get("params", {}),
                }
                new_options = dict(entry.options)
                new_options[CONF_DEVICES] = existing_devices
                self.hass.config_entries.async_update_entry(
                    entry, options=new_options
                )

                # Dispatch a synthetic event so platforms create the entity.
                # Use the RF-normalized model name so that the UID computed
                # from the event matches the one stored in device_id_map.
                protocol = self._new_device[CONF_DEVICE_PROTOCOL]
                rf_model = normalize_rf_model(
                    self._new_device.get(CONF_DEVICE_MODEL, "")
                )
                house_str = self._new_device.get(CONF_DEVICE_HOUSE, "")
                unit_str = self._new_device.get(CONF_DEVICE_UNIT, "")
                synthetic = RawDeviceEvent(
                    raw=(
                        f"class:command;protocol:{protocol};model:{rf_model};"
                        f"house:{house_str};unit:{unit_str};method:turnon;"
                    ),
                    controller_id=0,
                )
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_NEW_DEVICE.format(entry.entry_id),
                    synthetic,
                )

                # Don't create a subentry record
                return self.async_abort(reason="device_added")

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._new_device.get(CONF_DEVICE_NAME, ""),
                "protocol": self._new_device.get(CONF_DEVICE_PROTOCOL, ""),
                "model": self._new_device.get(CONF_DEVICE_MODEL, ""),
                "house": self._new_device.get(CONF_DEVICE_HOUSE, ""),
                "unit": self._new_device.get(CONF_DEVICE_UNIT, ""),
            },
            errors=errors,
        )
