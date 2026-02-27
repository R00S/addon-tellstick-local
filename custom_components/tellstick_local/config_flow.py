"""Config flow for TellStick Local integration."""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

try:
    from homeassistant.config_entries import (
        ConfigSubentryFlow,
        SubentryFlowResult,
    )
except ImportError:
    ConfigSubentryFlow = None  # type: ignore[assignment,misc]
    SubentryFlowResult = dict  # type: ignore[assignment,misc]
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
)
import homeassistant.helpers.config_validation as cv
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
    CONF_IGNORED_UIDS,
    DEFAULT_AUTOMATIC_ADD,
    DEFAULT_COMMAND_PORT,
    DEFAULT_EVENT_PORT,
    DEFAULT_HOST,
    DEVICE_CATALOG_LABELS,
    DEVICE_CATALOG_MAP,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_TELLSTICK_CONTROLLER,
    SENSOR_TYPE_NAMES,
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


def _build_device_label(uid: str, cfg: dict[str, Any]) -> str:
    """Build a human-readable label for a device dropdown entry."""
    name = cfg.get(CONF_DEVICE_NAME, uid)
    protocol = cfg.get(CONF_DEVICE_PROTOCOL, "")
    model = cfg.get(CONF_DEVICE_MODEL, "")
    if uid.startswith("sensor_"):
        sensor_id = cfg.get("sensor_id", "")
        data_type = cfg.get("data_type")
        type_str = (
            SENSOR_TYPE_NAMES.get(data_type, "")
            if data_type is not None
            else ""
        )
        if sensor_id and type_str:
            detail = f"sensor {sensor_id} {type_str}"
        elif sensor_id:
            detail = f"sensor {sensor_id}"
        else:
            detail = f"{protocol}/{model}"
    else:
        house = cfg.get(CONF_DEVICE_HOUSE, "")
        unit = cfg.get(CONF_DEVICE_UNIT, "")
        detail = f"{protocol}/{model}" if model else protocol
        if house:
            detail += f" house:{house}"
        if unit:
            detail += f" unit:{unit}"
    return f"{name} ({detail})" if detail else name


@callback
def _migrate_device_uid(
    hass: HomeAssistant,
    entry: ConfigEntry,
    old_uid: str,
    new_uid: str,
    new_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Migrate a device from old_uid to new_uid, preserving entity/history.

    Updates entity registry, device registry, and runtime maps.
    Returns the updated options dict (caller must save it).
    """
    entry_id = entry.entry_id

    # Update entity registry unique_id
    ent_reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry_id):
        if entity_entry.unique_id == f"{entry_id}_{old_uid}":
            ent_reg.async_update_entity(
                entity_entry.entity_id,
                new_unique_id=f"{entry_id}_{new_uid}",
            )

    # Update device registry identifiers
    dev_reg = dr.async_get(hass)
    device_entry = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"{entry_id}_{old_uid}")}
    )
    if device_entry:
        dev_reg.async_update_device(
            device_entry.id,
            new_identifiers={(DOMAIN, f"{entry_id}_{new_uid}")},
        )

    # Update runtime maps
    entry_data = hass.data.get(DOMAIN, {}).get(entry_id, {})
    device_id_map: dict[str, int] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
    if old_uid in device_id_map:
        device_id_map[new_uid] = device_id_map.pop(old_uid)
    discovered: set[str] = entry_data.get("_discovered_uids", set())
    discovered.discard(old_uid)
    discovered.add(new_uid)

    # Build updated options
    devices = dict(entry.options.get(CONF_DEVICES, {}))
    devices.pop(old_uid, None)
    devices[new_uid] = new_cfg
    new_options = dict(entry.options)
    new_options[CONF_DEVICES] = devices
    return new_options


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

        # Deduplicate: async_set_unique_id aborts if another flow with the
        # same unique_id is already in progress, and _abort_if_unique_id_configured
        # aborts if a config entry (including "ignored" entries) already has it.
        await self.async_set_unique_id(f"rf_{device_uid}")
        self._abort_if_unique_id_configured()

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

        return await self.async_step_add_rf_device()

    async def async_step_add_rf_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show form to name and add a discovered 433 MHz device."""
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

            # Handle ignore checkbox
            if user_input.get("ignore", False):
                ignored = dict(entry.options.get(CONF_IGNORED_UIDS, {}))
                ignored[device_uid] = (
                    f"{info.get('protocol', '')}/{info.get('model', '')} "
                    f"{device_uid}"
                )
                new_options = dict(entry.options)
                new_options[CONF_IGNORED_UIDS] = ignored
                self.hass.config_entries.async_update_entry(
                    entry, options=new_options
                )
                return self.async_abort(reason="device_ignored")
            name = user_input.get("name", default_name)
            replace_uid = user_input.get("replace_device", "")

            if replace_uid:
                # Replace existing device — migrate UID + preserve history
                old_cfg = dict(
                    entry.options.get(CONF_DEVICES, {}).get(replace_uid, {})
                )
                old_name = old_cfg.get(CONF_DEVICE_NAME, replace_uid)
                # Keep old name if user didn't change the default
                if name == default_name:
                    name = old_name

                # Build new config from the discovered signal
                if dev_type == "sensor":
                    new_cfg = {
                        CONF_DEVICE_NAME: name,
                        CONF_DEVICE_PROTOCOL: info.get("protocol", ""),
                        CONF_DEVICE_MODEL: info.get("model", ""),
                        "sensor_id": info.get("sensor_id"),
                        "data_type": info.get("data_type"),
                    }
                else:
                    new_cfg = {
                        CONF_DEVICE_NAME: name,
                        CONF_DEVICE_PROTOCOL: info.get("protocol", ""),
                        CONF_DEVICE_MODEL: info.get("model", ""),
                        CONF_DEVICE_HOUSE: info.get("house", ""),
                        CONF_DEVICE_UNIT: info.get("unit", ""),
                    }

                new_options = _migrate_device_uid(
                    self.hass, entry, replace_uid, device_uid, new_cfg
                )
                # Ignore old UID to prevent re-detection
                ignored = dict(new_options.get(CONF_IGNORED_UIDS, {}))
                ignored[replace_uid] = old_name
                new_options[CONF_IGNORED_UIDS] = ignored
                self.hass.config_entries.async_update_entry(
                    entry, options=new_options
                )
                # Reload so running entities are recreated with the new ID.
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(entry.entry_id)
                )

                # Register with telldusd if needed
                entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
                controller: TellStickController | None = entry_data.get(
                    ENTRY_TELLSTICK_CONTROLLER
                )
                device_id_map: dict[str, int] = entry_data.get(
                    ENTRY_DEVICE_ID_MAP, {}
                )
                if controller and dev_type != "sensor":
                    try:
                        telldusd_id = await controller.find_or_add_device(
                            name,
                            info.get("protocol", ""),
                            info.get("model", ""),
                            info.get("house", ""),
                            info.get("unit", ""),
                        )
                        device_id_map[device_uid] = telldusd_id
                    except Exception:  # noqa: BLE001
                        _LOGGER.warning(
                            "Could not register replaced device %s", device_uid
                        )

                return self.async_abort(reason="device_replaced")

            # Standard add-as-new flow (unchanged)
            entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
            controller = entry_data.get(ENTRY_TELLSTICK_CONTROLLER)
            device_id_map = entry_data.get(ENTRY_DEVICE_ID_MAP, {})

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

        # Build form schema
        schema_dict: dict[Any, Any] = {
            vol.Required("name", default=default_name): str,
        }

        # Add "replace existing device" dropdown if compatible devices exist
        entry_id = info.get("entry_id")
        entry = (
            self.hass.config_entries.async_get_entry(entry_id)
            if entry_id
            else None
        )
        if entry:
            devices = entry.options.get(CONF_DEVICES, {})
            # Filter to compatible type: sensors only replace sensors of the
            # same data_type (temperature ↔ temperature, humidity ↔ humidity).
            # This prevents accidentally migrating a humidity sensor onto a
            # temperature entity (issue #33).
            is_sensor = dev_type == "sensor"
            discovered_data_type = info.get("data_type") if is_sensor else None
            compatible = {
                uid: cfg
                for uid, cfg in devices.items()
                if uid.startswith("sensor_") == is_sensor
                and (
                    not is_sensor
                    or cfg.get("data_type") == discovered_data_type
                )
            }
            if compatible:
                replace_options = {"": "— Add as new device —"}
                for uid, cfg in compatible.items():
                    replace_options[uid] = _build_device_label(uid, cfg)
                schema_dict[
                    vol.Optional("replace_device", default="")
                ] = vol.In(replace_options)

        # Ignore checkbox — at the bottom so add is the primary action
        schema_dict[vol.Optional("ignore", default=False)] = bool

        return self.async_show_form(
            step_id="add_rf_device",
            data_schema=vol.Schema(schema_dict),
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
        ignored = self.config_entry.options.get(CONF_IGNORED_UIDS, {})
        menu_options = ["settings"]
        if devices:
            menu_options.append("manage_device")
            menu_options.append("remove_devices")
        if ignored:
            menu_options.append("manage_ignored")
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

    # -----------------------------------------------------------------
    # Manage a device (picker → action sub-menu → edit/teach/delete)
    # -----------------------------------------------------------------

    async def async_step_manage_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a device to manage."""
        devices = self.config_entry.options.get(CONF_DEVICES, {})
        if not devices:
            return self.async_abort(reason="no_devices")

        if user_input is not None:
            self._edit_uid = user_input["device"]
            return await self.async_step_device_actions()

        labels: dict[str, str] = {}
        for uid, cfg in devices.items():
            labels[uid] = _build_device_label(uid, cfg)

        return self.async_show_form(
            step_id="manage_device",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): vol.In(labels),
                }
            ),
        )

    async def async_step_device_actions(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show device action sub-menu."""
        uid = self._edit_uid
        devices = self.config_entry.options.get(CONF_DEVICES, {})
        cfg = devices.get(uid, {})
        name = cfg.get(CONF_DEVICE_NAME, uid)

        menu_options = ["device_detail"]
        menu_options.append("delete_device")

        return self.async_show_menu(
            step_id="device_actions",
            menu_options=menu_options,
            description_placeholders={"name": name},
        )

    async def async_step_device_detail(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """View and edit device parameters (name, house/unit, or sensor_id)."""
        uid = self._edit_uid
        devices = dict(self.config_entry.options.get(CONF_DEVICES, {}))
        cfg = dict(devices.get(uid, {}))

        if user_input is not None:
            cfg[CONF_DEVICE_NAME] = user_input["name"]

            if uid.startswith("sensor_"):
                # Sensor: check if sensor_id changed → UID migration
                old_sensor_id = cfg.get("sensor_id", 0)
                new_sensor_id = user_input.get("sensor_id", old_sensor_id)
                try:
                    old_id_int = int(old_sensor_id)
                    new_id_int = int(new_sensor_id)
                except (ValueError, TypeError):
                    old_id_int = 0
                    new_id_int = 0
                if new_id_int != old_id_int:
                    cfg["sensor_id"] = new_id_int
                    suffix = uid.rsplit("_", 1)[-1]  # "temperature"/"humidity"
                    if suffix not in ("temperature", "humidity"):
                        suffix = "sensor"
                    new_uid = f"sensor_{new_id_int}_{suffix}"
                    new_options = _migrate_device_uid(
                        self.hass, self.config_entry, uid, new_uid, cfg
                    )
                    # Reload so the running entity picks up the new sensor_id.
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(
                            self.config_entry.entry_id
                        )
                    )
                    return self.async_create_entry(title="", data=new_options)
            else:
                # Device: check if house/unit changed → UID migration
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
                new_uid = build_device_uid(
                    cfg.get(CONF_DEVICE_PROTOCOL, ""),
                    cfg.get(CONF_DEVICE_MODEL, ""),
                    cfg.get(CONF_DEVICE_HOUSE, ""),
                    cfg.get(CONF_DEVICE_UNIT, ""),
                )
                if new_uid != uid:
                    new_options = _migrate_device_uid(
                        self.hass, self.config_entry, uid, new_uid, cfg
                    )
                    # Reload so the running entity picks up the new house/unit.
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(
                            self.config_entry.entry_id
                        )
                    )
                    return self.async_create_entry(title="", data=new_options)

            # No UID change — just update in place
            devices[uid] = cfg
            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = devices
            return self.async_create_entry(title="", data=new_options)

        name = cfg.get(CONF_DEVICE_NAME, uid)
        protocol = cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = cfg.get(CONF_DEVICE_MODEL, "")

        schema_dict: dict[Any, Any] = {
            vol.Required("name", default=name): str,
        }
        if uid.startswith("sensor_"):
            sensor_id = cfg.get("sensor_id", 0)
            schema_dict[vol.Required("sensor_id", default=sensor_id)] = int
        else:
            house = cfg.get(CONF_DEVICE_HOUSE, "")
            unit = cfg.get(CONF_DEVICE_UNIT, "")
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

    async def async_step_teach_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Send a learn/teach signal for a self-learning device."""
        uid = self._edit_uid
        devices = self.config_entry.options.get(CONF_DEVICES, {})
        cfg = devices.get(uid, {})
        errors: dict[str, str] = {}

        if user_input is not None:
            entry_data = self.hass.data.get(DOMAIN, {}).get(
                self.config_entry.entry_id, {}
            )
            controller: TellStickController | None = entry_data.get(
                ENTRY_TELLSTICK_CONTROLLER
            )
            device_id_map: dict[str, int] = entry_data.get(
                ENTRY_DEVICE_ID_MAP, {}
            )
            telldusd_id = device_id_map.get(uid)

            if controller and telldusd_id is not None:
                try:
                    await controller.learn(telldusd_id)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Failed to send learn signal for %s", uid)
                    errors["base"] = "teach_failed"
                else:
                    return self.async_abort(reason="teach_sent")
            else:
                errors["base"] = "teach_failed"

        return self.async_show_form(
            step_id="teach_device",
            description_placeholders={
                "name": cfg.get(CONF_DEVICE_NAME, uid),
                "protocol": cfg.get(CONF_DEVICE_PROTOCOL, ""),
                "model": cfg.get(CONF_DEVICE_MODEL, ""),
            },
            errors=errors,
        )

    async def async_step_delete_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Delete a device with optional ignore."""
        uid = self._edit_uid
        devices = self.config_entry.options.get(CONF_DEVICES, {})
        cfg = devices.get(uid, {})

        if user_input is not None:
            ignore = user_input.get("ignore", True)

            # Remove from telldusd
            entry_data = self.hass.data.get(DOMAIN, {}).get(
                self.config_entry.entry_id, {}
            )
            controller: TellStickController | None = entry_data.get(
                ENTRY_TELLSTICK_CONTROLLER
            )
            device_id_map: dict[str, int] = entry_data.get(
                ENTRY_DEVICE_ID_MAP, {}
            )
            if controller and uid in device_id_map:
                try:
                    await controller.remove_device(device_id_map[uid])
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Could not remove %s from telldusd", uid)
                device_id_map.pop(uid, None)

            # Remove from device registry
            dev_reg = dr.async_get(self.hass)
            device_entry = dev_reg.async_get_device(
                identifiers={
                    (DOMAIN, f"{self.config_entry.entry_id}_{uid}")
                }
            )
            if device_entry:
                dev_reg.async_remove_device(device_entry.id)

            # Update options
            new_devices = dict(devices)
            new_devices.pop(uid, None)
            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = new_devices

            if ignore:
                ignored = dict(new_options.get(CONF_IGNORED_UIDS, {}))
                ignored[uid] = cfg.get(CONF_DEVICE_NAME, uid)
                new_options[CONF_IGNORED_UIDS] = ignored

            # Allow re-discovery if not ignoring
            discovered: set[str] = entry_data.get("_discovered_uids", set())
            discovered.discard(uid)

            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="delete_device",
            data_schema=vol.Schema(
                {
                    vol.Required("ignore", default=True): bool,
                }
            ),
            description_placeholders={
                "name": cfg.get(CONF_DEVICE_NAME, uid),
            },
        )

    # -----------------------------------------------------------------
    # Remove multiple devices
    # -----------------------------------------------------------------

    async def async_step_remove_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Multi-select removal of devices."""
        devices = self.config_entry.options.get(CONF_DEVICES, {})
        if not devices:
            return self.async_abort(reason="no_devices")

        if user_input is not None:
            selected = user_input.get("devices", [])
            ignore = user_input.get("ignore", True)

            if not selected:
                return self.async_create_entry(
                    title="", data=dict(self.config_entry.options)
                )

            entry_data = self.hass.data.get(DOMAIN, {}).get(
                self.config_entry.entry_id, {}
            )
            controller: TellStickController | None = entry_data.get(
                ENTRY_TELLSTICK_CONTROLLER
            )
            device_id_map: dict[str, int] = entry_data.get(
                ENTRY_DEVICE_ID_MAP, {}
            )
            dev_reg = dr.async_get(self.hass)
            discovered: set[str] = entry_data.get("_discovered_uids", set())

            new_devices = dict(devices)
            ignored = dict(
                self.config_entry.options.get(CONF_IGNORED_UIDS, {})
            )

            for uid in selected:
                cfg = new_devices.pop(uid, {})

                # Remove from telldusd
                if controller and uid in device_id_map:
                    try:
                        await controller.remove_device(device_id_map[uid])
                    except Exception:  # noqa: BLE001
                        pass
                    device_id_map.pop(uid, None)

                # Remove from device registry
                device_entry = dev_reg.async_get_device(
                    identifiers={
                        (DOMAIN, f"{self.config_entry.entry_id}_{uid}")
                    }
                )
                if device_entry:
                    dev_reg.async_remove_device(device_entry.id)

                if ignore:
                    ignored[uid] = cfg.get(CONF_DEVICE_NAME, uid)

                discovered.discard(uid)

            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = new_devices
            if ignore:
                new_options[CONF_IGNORED_UIDS] = ignored
            return self.async_create_entry(title="", data=new_options)

        labels: dict[str, str] = {}
        for uid, cfg in devices.items():
            labels[uid] = _build_device_label(uid, cfg)

        return self.async_show_form(
            step_id="remove_devices",
            data_schema=vol.Schema(
                {
                    vol.Required("devices"): cv.multi_select(labels),
                    vol.Required("ignore", default=True): bool,
                }
            ),
        )

    # -----------------------------------------------------------------
    # Manage ignored devices (un-ignore)
    # -----------------------------------------------------------------

    async def async_step_manage_ignored(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Un-ignore previously ignored devices so they can be re-detected."""
        ignored = dict(self.config_entry.options.get(CONF_IGNORED_UIDS, {}))
        if not ignored:
            return self.async_abort(reason="no_ignored")

        if user_input is not None:
            to_unignore = user_input.get("devices", [])
            for uid in to_unignore:
                ignored.pop(uid, None)

            new_options = dict(self.config_entry.options)
            new_options[CONF_IGNORED_UIDS] = ignored

            # Allow re-discovery for un-ignored UIDs
            entry_data = self.hass.data.get(DOMAIN, {}).get(
                self.config_entry.entry_id, {}
            )
            discovered: set[str] = entry_data.get("_discovered_uids", set())
            for uid in to_unignore:
                discovered.discard(uid)

            return self.async_create_entry(title="", data=new_options)

        labels: dict[str, str] = {uid: name for uid, name in ignored.items()}

        return self.async_show_form(
            step_id="manage_ignored",
            data_schema=vol.Schema(
                {
                    vol.Required("devices"): cv.multi_select(labels),
                }
            ),
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
