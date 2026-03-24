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
    BACKEND_DUO,
    BACKEND_NET,
    CONF_AUTOMATIC_ADD,
    CONF_BACKEND,
    CONF_COMMAND_PORT,
    CONF_DETECT_SARTANO,
    CONF_DEVICE_HOUSE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    CONF_EVENT_PORT,
    CONF_IGNORED_UIDS,
    CONF_MIRROR_OF,
    DEFAULT_AUTOMATIC_ADD,
    DEFAULT_COMMAND_PORT,
    DEFAULT_DETECT_SARTANO,
    DEFAULT_EVENT_PORT,
    DEFAULT_HOST,
    DEVICE_CATALOG_LABELS,
    DEVICE_CATALOG_MAP,
    DOMAIN,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_MIRRORS,
    ENTRY_TELLSTICK_CONTROLLER,
    PROTOCOL_MODEL_LABELS,
    PROTOCOL_MODEL_MAP,
    SENSOR_TYPE_NAMES,
    SIGNAL_NEW_DEVICE,
    WIDGET_PARAMS,
    build_device_uid,
    normalize_rf_model,
)

SUBENTRY_TYPE_DEVICE = "device"

_LOGGER = logging.getLogger(__name__)

# Prefix used in the discovery dropdown to distinguish "Add to device"
# selections from "Replace device" selections.
_GROUP_PREFIX = "group_"

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


def _extract_sensor_suffix(uid: str) -> str:
    """Extract the data-type suffix from a sensor UID.

    Sensor UIDs have format ``sensor_{sensor_id}_{suffix}`` where suffix
    is ``temperature`` or ``humidity``.  Returns ``"sensor"`` as fallback
    for unexpected formats.
    """
    parts = uid.split("_")
    suffix = parts[2] if len(parts) >= 3 else "sensor"
    return suffix if suffix in ("temperature", "humidity") else "sensor"


def _strip_sensor_suffix(name: str) -> str:
    """Strip a trailing type suffix from a sensor name.

    ``"Vinkällare temperature"`` → ``"Vinkällare"``.
    Returns the name unchanged if no known suffix is found.
    """
    for s in ("temperature", "humidity"):
        if name.lower().endswith(f" {s}"):
            return name[: -(len(s) + 1)]
    return name


def _build_device_label(
    uid: str, cfg: dict[str, Any], *, sensor_grouped: bool = False
) -> str:
    """Build a human-readable label for a device dropdown entry.

    When *sensor_grouped* is True, the label omits the data_type suffix
    because the dropdown shows one entry per physical sensor_id.
    """
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
        if sensor_grouped:
            # Strip type suffix from name for grouped display
            name = _strip_sensor_suffix(name)
            detail = f"sensor {sensor_id}" if sensor_id else f"{protocol}/{model}"
        elif sensor_id and type_str:
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

    # Update device registry identifiers.
    # Sensors use a shared device identifier: sensor_{sensor_id} (no type
    # suffix).  Temperature + humidity entities share one HA device.
    dev_reg = dr.async_get(hass)
    if old_uid.startswith("sensor_"):
        old_parts = old_uid.split("_")
        new_parts = new_uid.split("_")
        old_dev_key = f"sensor_{old_parts[1]}" if len(old_parts) >= 2 else old_uid
        new_dev_key = f"sensor_{new_parts[1]}" if len(new_parts) >= 2 else new_uid
    else:
        old_dev_key = old_uid
        new_dev_key = new_uid

    device_entry = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"{entry_id}_{old_dev_key}")}
    )
    if device_entry:
        dev_reg.async_update_device(
            device_entry.id,
            new_identifiers={(DOMAIN, f"{entry_id}_{new_dev_key}")},
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


@callback
def _migrate_sensor_companion(
    hass: HomeAssistant,
    entry: ConfigEntry,
    old_sensor_id: str,
    new_sensor_id: str,
    primary_suffix: str,
    new_options: dict[str, Any],
) -> dict[str, Any]:
    """Migrate the companion sensor entity (temp↔hum) for a sensor pair.

    When a temperature sensor is migrated, this also migrates the
    corresponding humidity entity (and vice versa), so both entities
    move atomically to the new sensor_id.

    ``new_options`` must already contain the primary migration's changes
    (from ``_migrate_device_uid``).  Returns the further-updated options.
    """
    entry_id = entry.entry_id
    devices = new_options.get(CONF_DEVICES, {})

    # Find companion suffixes that have stored entries
    companions = [
        s for s in ("temperature", "humidity")
        if s != primary_suffix and f"sensor_{old_sensor_id}_{s}" in devices
    ]
    if not companions:
        return new_options

    ent_reg = er.async_get(hass)
    entry_data = hass.data.get(DOMAIN, {}).get(entry_id, {})
    discovered: set[str] = entry_data.get("_discovered_uids", set())

    for comp_suffix in companions:
        comp_old_uid = f"sensor_{old_sensor_id}_{comp_suffix}"
        comp_new_uid = f"sensor_{new_sensor_id}_{comp_suffix}"

        # Update companion entity unique_id in the entity registry.
        # If the update fails (e.g. new unique_id already exists),
        # remove the orphaned old entity to prevent "unavailable" ghosts.
        for ent in er.async_entries_for_config_entry(ent_reg, entry_id):
            if ent.unique_id == f"{entry_id}_{comp_old_uid}":
                try:
                    ent_reg.async_update_entity(
                        ent.entity_id,
                        new_unique_id=f"{entry_id}_{comp_new_uid}",
                    )
                except ValueError:
                    _LOGGER.warning(
                        "Companion entity %s: unique_id conflict, removing orphan",
                        ent.entity_id,
                    )
                    ent_reg.async_remove(ent.entity_id)
                break
        else:
            _LOGGER.debug(
                "Companion entity for %s not found in entity registry",
                comp_old_uid,
            )

        # Update companion in options (read from current new_options each time)
        cur_devices = new_options.get(CONF_DEVICES, {})
        comp_cfg = dict(cur_devices[comp_old_uid])
        comp_cfg["sensor_id"] = int(new_sensor_id)
        devs = dict(cur_devices)
        devs.pop(comp_old_uid, None)
        devs[comp_new_uid] = comp_cfg
        new_options = dict(new_options)
        new_options[CONF_DEVICES] = devs

        # Update discovered set — mark both old and new as handled so
        # pending discovery flows for the companion are suppressed.
        discovered.discard(comp_old_uid)
        discovered.add(comp_new_uid)
        # Also mark the sensor_id-level dedup key
        discovered.add(f"sensor_{new_sensor_id}")

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
        # Net/ZNet specific state
        self._net_mac: str = ""
        self._net_discovered: list[tuple[str, str, str]] = []  # (ip, mac, raw)
        # Pending entry data for mirror step (set before showing mirror_setup)
        self._pending_backend: str = ""
        self._pending_title: str = ""
        self._pending_data: dict[str, Any] = {}
        self._pending_options: dict[str, Any] = {}

    def _get_existing_primary_entries(self) -> list[ConfigEntry]:
        """Return existing non-mirror TellStick entries (any backend type)."""
        return [
            e
            for e in self._async_current_entries()
            if not e.data.get(CONF_MIRROR_OF)
        ]

    async def _async_create_or_mirror(
        self,
        title: str,
        data: dict[str, Any],
        options: dict[str, Any],
    ) -> FlowResult:
        """Create the entry directly or show the mirror step if primaries exist.

        When there are existing non-mirror TellStick entries, the user gets the
        option to set this new TellStick up as a mirror/range extender for one
        of them.  The primary and mirror can be different backend types (e.g.
        a Net/ZNet can mirror a Duo and vice versa).
        """
        primaries = self._get_existing_primary_entries()
        if not primaries:
            # No existing entries — create as standalone (no mirror option)
            return self.async_create_entry(
                title=title, data=data, options=options,
            )

        # Save pending entry data so mirror_setup can create the entry
        self._pending_title = title
        self._pending_data = data
        self._pending_options = options
        return await self.async_step_mirror_setup()

    async def async_step_mirror_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask if this TellStick should be a mirror/range extender."""
        if user_input is not None:
            mirror_of = user_input.get(CONF_MIRROR_OF, "")
            if mirror_of:
                # Set up as mirror — store mirror_of in entry data
                self._pending_data[CONF_MIRROR_OF] = mirror_of
                primary = self.hass.config_entries.async_get_entry(mirror_of)
                primary_title = primary.title if primary else mirror_of
                return self.async_create_entry(
                    title=f"{self._pending_title} (mirror of {primary_title})",
                    data=self._pending_data,
                    options={},  # mirrors don't store devices
                )
            # Standalone — create without mirror_of
            return self.async_create_entry(
                title=self._pending_title,
                data=self._pending_data,
                options=self._pending_options,
            )

        primaries = self._get_existing_primary_entries()
        mirror_options: dict[str, str] = {"": "— No, set up as standalone —"}
        for entry in primaries:
            mirror_options[entry.entry_id] = entry.title
        return self.async_show_form(
            step_id="mirror_setup",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_MIRROR_OF, default=""): vol.In(
                        mirror_options
                    ),
                }
            ),
        )

    async def async_step_hassio(
        self, discovery_info: HassioServiceInfo
    ) -> FlowResult:
        """Handle discovery by the Supervisor (app installed → HA auto-offers setup)."""
        # discovery_info.slug is the HAOS Supervisor internal hostname
        # (e.g. "e9305338-tellsticklive" for custom-repo apps).
        slug = discovery_info.slug

        # Use a stable slug:port unique_id rather than discovery_info.uuid.
        # The Supervisor UUID can change when the add-on is reinstalled or
        # updated, which previously caused a *new* Duo entry to be created
        # alongside the existing (possibly disabled) one — the old entry with
        # all stored devices became orphaned and effectively disappeared.
        await self.async_set_unique_id(f"{slug}:{DEFAULT_COMMAND_PORT}")
        self._abort_if_unique_id_configured()

        # Fallback: also check by host for entries created before this change
        # (those used discovery_info.uuid as unique_id, so the set_unique_id
        # check above won't find them).  Abort if any Duo entry for this slug
        # already exists regardless of its state (loaded, disabled, error…).
        for existing in self._async_current_entries():
            if (
                existing.data.get(CONF_BACKEND, BACKEND_DUO) == BACKEND_DUO
                and existing.data.get(CONF_HOST) == slug
            ):
                return self.async_abort(reason="already_configured")

        self._host = slug
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
                return await self._async_create_or_mirror(
                    title="TellStick Duo",
                    data={
                        CONF_BACKEND: BACKEND_DUO,
                        CONF_HOST: self._host,
                        CONF_COMMAND_PORT: self._command_port,
                        CONF_EVENT_PORT: self._event_port,
                    },
                    options={CONF_DEVICES: {}},
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
        """Show backend type selection (TellStick Duo vs Net/ZNet)."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["duo", "net"],
        )

    async def async_step_duo(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual setup for TellStick Duo (TCP via telldusd socat bridges)."""
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
                return await self._async_create_or_mirror(
                    title=f"TellStick Duo ({host})",
                    data={
                        CONF_BACKEND: BACKEND_DUO,
                        CONF_HOST: host,
                        CONF_COMMAND_PORT: cmd_port,
                        CONF_EVENT_PORT: evt_port,
                    },
                    options={CONF_DEVICES: {}},
                )

        return self.async_show_form(
            step_id="duo",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_net(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start TellStick Net/ZNet setup — run UDP discovery first."""
        return await self.async_step_net_discovery()

    async def async_step_net_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Discover TellStick Net/ZNet devices via UDP broadcast or manual IP entry.

        If the UDP discovery finds devices, shows a dropdown to pick one or
        enter an IP manually.  If no devices are found, shows the manual IP
        entry form directly.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # User may have selected a discovered IP or typed one manually.
            # "discovered_ip" comes from the found-devices dropdown; "" means manual.
            host = user_input.get("discovered_ip", "").strip()
            if not host:
                host = user_input.get(CONF_HOST, "").strip()

            if not host:
                errors[CONF_HOST] = "required"
            else:
                # Find the MAC for the selected discovered IP (if any)
                mac = ""
                for disc_ip, disc_mac, _raw in self._net_discovered:
                    if disc_ip == host:
                        mac = disc_mac
                        break
                self._host = host
                self._net_mac = mac
                return await self.async_step_net_confirm()

        # Try UDP discovery; time-box to 2 s (non-blocking)
        self._net_discovered = []
        try:
            from .net_client import discover  # noqa: PLC0415

            async for ip, mac, product in discover(timeout=2.0):
                self._net_discovered.append((ip, mac, product))
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Net discovery error (non-fatal): %s", err)

        # Build schema — add a dropdown when devices were found
        if self._net_discovered:
            device_options: dict[str, str] = {}
            for ip, mac, product in self._net_discovered:
                label = f"{product} — {ip}" + (f" [{mac}]" if mac else "")
                device_options[ip] = label
            device_options[""] = "— Enter IP address manually —"
            schema = vol.Schema(
                {
                    vol.Optional("discovered_ip", default=""): vol.In(device_options),
                    vol.Optional(CONF_HOST, default=""): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_HOST, default=""): str,
                }
            )

        return self.async_show_form(
            step_id="net_discovery",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "found_count": str(len(self._net_discovered)),
            },
        )

    async def async_step_net_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm the selected TellStick Net/ZNet device and create the entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Re-read host from form if the user typed it manually in discovery step
            host = user_input.get(CONF_HOST, self._host).strip() or self._host
            if not host:
                errors[CONF_HOST] = "required"
            else:
                self._host = host
                self._net_mac = user_input.get("mac", self._net_mac).strip()

                # Validate: try sending a reglistener packet
                from .net_client import TellStickNetController  # noqa: PLC0415

                test_ctrl = TellStickNetController(
                    host=self._host, mac=self._net_mac
                )
                try:
                    await asyncio.wait_for(test_ctrl.connect(), timeout=5)
                    reachable = await test_ctrl.ping()
                except (asyncio.TimeoutError, OSError):
                    reachable = False
                finally:
                    await test_ctrl.disconnect()

                if not reachable:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(
                        f"net_{self._host}_{self._net_mac or self._host}"
                    )
                    self._abort_if_unique_id_configured()

                    return await self._async_create_or_mirror(
                        title=f"TellStick Net/ZNet ({self._host})",
                        data={
                            CONF_BACKEND: BACKEND_NET,
                            CONF_HOST: self._host,
                            "mac": self._net_mac,
                        },
                        options={CONF_DEVICES: {}},
                    )

        return self.async_show_form(
            step_id="net_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._host): str,
                    vol.Optional("mac", default=self._net_mac): str,
                }
            ),
            description_placeholders={
                "host": self._host or "?",
                "mac": self._net_mac or "?",
            },
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

            # Re-check: if the device was already stored (e.g. companion
            # migration added it while this flow was pending), abort.
            if device_uid in entry.options.get(CONF_DEVICES, {}):
                return self.async_abort(reason="already_added")

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

            if replace_uid.startswith(_GROUP_PREFIX):
                # ── Add to existing device (group) ──────────────────
                # The user wants this sensor to appear as an entity
                # within an existing sensor device (e.g. indoor + outdoor
                # probes of the same weather station).
                target_uid = replace_uid[len(_GROUP_PREFIX):]
                target_cfg = entry.options.get(CONF_DEVICES, {}).get(
                    target_uid, {}
                )
                target_sensor_id = target_cfg.get("sensor_id")

                existing_devices = dict(
                    entry.options.get(CONF_DEVICES, {})
                )
                existing_devices[device_uid] = {
                    CONF_DEVICE_NAME: name,
                    CONF_DEVICE_PROTOCOL: info.get("protocol", ""),
                    CONF_DEVICE_MODEL: info.get("model", ""),
                    "sensor_id": info.get("sensor_id"),
                    "data_type": info.get("data_type"),
                    "group_sensor_id": target_sensor_id,
                }
                new_options = dict(entry.options)
                new_options[CONF_DEVICES] = existing_devices
                self.hass.config_entries.async_update_entry(
                    entry, options=new_options
                )

                # Fire SIGNAL_NEW_DEVICE so the entity is created now
                synthetic = SensorEvent(
                    protocol=info.get("protocol", ""),
                    model=info.get("model", ""),
                    sensor_id=info.get("sensor_id", 0),
                    data_type=info.get("data_type", 0),
                    value="",
                )
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_NEW_DEVICE.format(entry.entry_id),
                    synthetic,
                )

                return self.async_abort(reason="device_added")

            if replace_uid:
                # Replace existing device — migrate UID + preserve history
                replace_cfg = dict(
                    entry.options.get(CONF_DEVICES, {}).get(replace_uid, {})
                )

                if dev_type == "sensor":
                    # Sensor replacement: the replace dropdown groups by
                    # sensor_id, so replace_uid may point to ANY data_type
                    # entry (temperature or humidity).  We must match old
                    # entries by data type to avoid cross-wiring entities.
                    # Issue #33.
                    old_sid = str(replace_cfg.get("sensor_id", ""))
                    new_sid = str(info.get("sensor_id", ""))
                    disc_suffix = _extract_sensor_suffix(device_uid)

                    # Find the old entry that matches the discovery data type
                    all_devices = entry.options.get(CONF_DEVICES, {})
                    correct_old_uid = (
                        f"sensor_{old_sid}_{disc_suffix}"
                        if old_sid and disc_suffix
                        else replace_uid
                    )
                    if correct_old_uid in all_devices:
                        matched_cfg = dict(all_devices[correct_old_uid])
                        matched_name = matched_cfg.get(
                            CONF_DEVICE_NAME, correct_old_uid
                        )
                    else:
                        correct_old_uid = replace_uid
                        matched_name = replace_cfg.get(
                            CONF_DEVICE_NAME, replace_uid
                        )

                    if name == default_name:
                        name = matched_name

                    new_cfg = {
                        CONF_DEVICE_NAME: name,
                        CONF_DEVICE_PROTOCOL: info.get("protocol", ""),
                        CONF_DEVICE_MODEL: info.get("model", ""),
                        "sensor_id": info.get("sensor_id"),
                        "data_type": info.get("data_type"),
                    }

                    new_options = _migrate_device_uid(
                        self.hass, entry, correct_old_uid, device_uid,
                        new_cfg,
                    )

                    # No ignored-list entry for sensors — the old sensor_id
                    # is gone after battery replacement and won't re-appear.

                    # Migrate companion (temp↔hum) so the user doesn't have
                    # to merge twice.
                    if old_sid and new_sid and old_sid != new_sid:
                        new_options = _migrate_sensor_companion(
                            self.hass, entry,
                            old_sid, new_sid,
                            disc_suffix, new_options,
                        )
                else:
                    old_name = replace_cfg.get(
                        CONF_DEVICE_NAME, replace_uid
                    )
                    if name == default_name:
                        name = old_name

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
                    ignored = dict(
                        new_options.get(CONF_IGNORED_UIDS, {})
                    )
                    ignored[replace_uid] = old_name
                    new_options[CONF_IGNORED_UIDS] = ignored

                self.hass.config_entries.async_update_entry(
                    entry, options=new_options
                )
                # Reload so running entities are recreated with the new ID.
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(entry.entry_id)
                )

                # Register with telldusd / Net controller if needed
                entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
                controller: Any = entry_data.get(
                    ENTRY_TELLSTICK_CONTROLLER
                )
                device_id_map: dict[str, Any] = entry_data.get(
                    ENTRY_DEVICE_ID_MAP, {}
                )
                if controller and dev_type != "sensor":
                    backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
                    if backend == BACKEND_NET:
                        device_id_map[device_uid] = {
                            CONF_DEVICE_PROTOCOL: info.get("protocol", ""),
                            CONF_DEVICE_MODEL: info.get("model", ""),
                            CONF_DEVICE_HOUSE: info.get("house", ""),
                            CONF_DEVICE_UNIT: info.get("unit", ""),
                        }
                    else:
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
                # Register with telldusd or Net controller so commands work immediately
                if controller:
                    backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
                    if backend == BACKEND_NET:
                        device_id_map[device_uid] = {
                            CONF_DEVICE_PROTOCOL: info.get("protocol", ""),
                            CONF_DEVICE_MODEL: info.get("model", ""),
                            CONF_DEVICE_HOUSE: info.get("house", ""),
                            CONF_DEVICE_UNIT: info.get("unit", ""),
                        }
                    else:
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
                    # Register on all mirror controllers too
                    from . import _register_device_on_mirror  # noqa: PLC0415

                    for mirror in entry_data.get(ENTRY_MIRRORS, []):
                        await _register_device_on_mirror(
                            mirror,
                            device_uid,
                            name,
                            info.get("protocol", ""),
                            info.get("model", ""),
                            info.get("house", ""),
                            info.get("unit", ""),
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
            is_sensor = dev_type == "sensor"
            if is_sensor:
                # Group sensors by sensor_id for the replace dropdown.
                # Temp+hum entities share one physical sensor; show one
                # entry per sensor_id so the user picks once and the
                # companion migration handles both.  Issue #33.
                seen_ids: set[int] = set()
                compatible: dict[str, dict[str, Any]] = {}
                for uid, cfg in devices.items():
                    if not uid.startswith("sensor_"):
                        continue
                    sid = cfg.get("sensor_id")
                    if sid is None or sid in seen_ids:
                        continue
                    seen_ids.add(sid)
                    compatible[uid] = cfg
            else:
                compatible = {
                    uid: cfg
                    for uid, cfg in devices.items()
                    if not uid.startswith("sensor_")
                }
            if compatible:
                replace_options = {"": "— Add as new device —"}
                for uid, cfg in compatible.items():
                    label = _build_device_label(
                        uid, cfg, sensor_grouped=is_sensor
                    )
                    if is_sensor:
                        replace_options[f"{_GROUP_PREFIX}{uid}"] = (
                            f"Add to: {label}"
                        )
                    replace_options[uid] = f"Replace: {label}"
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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow changing the connection settings of an existing entry.

        Shown as "Reconfigure" in the config entry gear menu.  Lets users
        update the hostname (or IP address) and ports without losing stored
        device configuration — for example when switching between the stable
        and dev channel add-ons, which have different Supervisor hostnames.
        """
        entry = self._get_reconfigure_entry()
        backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
        errors: dict[str, str] = {}

        if user_input is not None:
            new_host = user_input[CONF_HOST].strip()
            new_data = dict(entry.data)
            new_data[CONF_HOST] = new_host
            if backend == BACKEND_DUO:
                new_data[CONF_COMMAND_PORT] = user_input[CONF_COMMAND_PORT]
                new_data[CONF_EVENT_PORT] = user_input[CONF_EVENT_PORT]
                try:
                    await _validate_connection(
                        new_host,
                        user_input[CONF_COMMAND_PORT],
                        user_input[CONF_EVENT_PORT],
                    )
                except (asyncio.TimeoutError, OSError):
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error during reconfigure validation")
                    errors["base"] = "unknown"
            if not errors:
                # Update the unique_id to match the new host if it was
                # host-based (set by async_step_hassio / async_step_duo).
                old_host = entry.data.get(CONF_HOST, "")
                old_cmd = entry.data.get(CONF_COMMAND_PORT, DEFAULT_COMMAND_PORT)
                if entry.unique_id == f"{old_host}:{old_cmd}":
                    new_cmd = new_data.get(CONF_COMMAND_PORT, DEFAULT_COMMAND_PORT)
                    await self.async_set_unique_id(f"{new_host}:{new_cmd}")
                    self._abort_if_unique_id_configured(
                        updates={CONF_HOST: new_host}
                    )
                return self.async_update_reload_and_abort(
                    entry, data=new_data, reason="reconfigure_successful"
                )

        current_host = entry.data.get(CONF_HOST, "")
        if backend == BACKEND_DUO:
            schema = vol.Schema(
                {
                    vol.Required(CONF_HOST, default=current_host): str,
                    vol.Required(
                        CONF_COMMAND_PORT,
                        default=entry.data.get(
                            CONF_COMMAND_PORT, DEFAULT_COMMAND_PORT
                        ),
                    ): vol.All(int, vol.Range(min=1, max=65535)),
                    vol.Required(
                        CONF_EVENT_PORT,
                        default=entry.data.get(
                            CONF_EVENT_PORT, DEFAULT_EVENT_PORT
                        ),
                    ): vol.All(int, vol.Range(min=1, max=65535)),
                }
            )
        else:
            schema = vol.Schema({vol.Required(CONF_HOST, default=current_host): str})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
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
    _move_target_entry_id: str = ""

    def _get_other_primary_entries(self) -> list[ConfigEntry]:
        """Return primary TellStick entries other than this one."""
        return [
            e
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != self.config_entry.entry_id
            and not e.data.get(CONF_MIRROR_OF)
        ]

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
            new_options[CONF_DETECT_SARTANO] = user_input[CONF_DETECT_SARTANO]
            return self.async_create_entry(title="", data=new_options)

        current_auto = self.config_entry.options.get(
            CONF_AUTOMATIC_ADD, DEFAULT_AUTOMATIC_ADD
        )
        current_sartano = self.config_entry.options.get(
            CONF_DETECT_SARTANO, DEFAULT_DETECT_SARTANO
        )
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTOMATIC_ADD, default=current_auto): bool,
                    vol.Required(CONF_DETECT_SARTANO, default=current_sartano): bool,
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

        # Group sensors by sensor_id so one physical sensor shows once.
        labels: dict[str, str] = {}
        seen_sensor_ids: set[int] = set()
        for uid, cfg in devices.items():
            if uid.startswith("sensor_"):
                sid = cfg.get("sensor_id")
                if sid is not None and sid in seen_sensor_ids:
                    continue
                if sid is not None:
                    seen_sensor_ids.add(sid)
                labels[uid] = _build_device_label(
                    uid, cfg, sensor_grouped=True
                )
            else:
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

        # Show base name for grouped sensors
        if uid.startswith("sensor_"):
            name = _strip_sensor_suffix(name)

        menu_options = ["device_detail"]
        # Allow moving to another instance when other primary entries exist
        if self._get_other_primary_entries():
            menu_options.append("move_device")
        # Allow grouping for non-sensor devices
        if not uid.startswith("sensor_"):
            menu_options.append("group_device")
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
            if uid.startswith("sensor_"):
                base_name = user_input["name"]
                old_sensor_id = cfg.get("sensor_id", 0)
                new_sensor_id = user_input.get("sensor_id", old_sensor_id)
                try:
                    old_id_int = int(old_sensor_id)
                    new_id_int = int(new_sensor_id)
                except (ValueError, TypeError):
                    old_id_int = 0
                    new_id_int = 0

                # Update name for ALL entries of this sensor_id.
                # base_name is the device name without type suffix; each
                # entry gets "base_name temperature" / "base_name humidity".
                for e_uid, e_cfg in list(devices.items()):
                    if not e_uid.startswith("sensor_"):
                        continue
                    if e_cfg.get("sensor_id") != old_id_int:
                        continue
                    e_suffix = _extract_sensor_suffix(e_uid)
                    e_cfg = dict(e_cfg)
                    e_cfg[CONF_DEVICE_NAME] = f"{base_name} {e_suffix}"
                    devices[e_uid] = e_cfg

                # Re-read cfg after name update
                cfg = dict(devices.get(uid, cfg))

                if new_id_int != old_id_int:
                    cfg["sensor_id"] = new_id_int
                    suffix = _extract_sensor_suffix(uid)
                    new_uid = f"sensor_{new_id_int}_{suffix}"
                    # Write name-updated devices back before migration
                    temp_options = dict(self.config_entry.options)
                    temp_options[CONF_DEVICES] = devices
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, options=temp_options
                    )
                    new_options = _migrate_device_uid(
                        self.hass, self.config_entry, uid, new_uid, cfg
                    )
                    # Also migrate companion entity (temp↔hum) so both
                    # entities move atomically (issue #33).
                    new_options = _migrate_sensor_companion(
                        self.hass, self.config_entry,
                        str(old_id_int), str(new_id_int),
                        suffix, new_options,
                    )
                    # Reload so the running entity picks up the new sensor_id.
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(
                            self.config_entry.entry_id
                        )
                    )
                    return self.async_create_entry(title="", data=new_options)
            else:
                cfg[CONF_DEVICE_NAME] = user_input["name"]
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

            # Immediately reflect the new name in HA's device registry so
            # the Devices & Services list updates without requiring a reload.
            # We set name_by_user (user-controlled override) because this
            # rename is an explicit user action.  Issue #33.
            dev_reg_local = dr.async_get(self.hass)
            if uid.startswith("sensor_"):
                sensor_id_val = cfg.get("sensor_id", 0)
                dev_key_local = f"sensor_{sensor_id_val}"
                # For sensors, user_input["name"] is the base name (without
                # the temperature/humidity suffix).
                display_name = user_input["name"]
            else:
                dev_key_local = uid
                display_name = cfg.get(CONF_DEVICE_NAME, uid)
            dev_entry_local = dev_reg_local.async_get_device(
                identifiers={
                    (DOMAIN, f"{self.config_entry.entry_id}_{dev_key_local}")
                }
            )
            if dev_entry_local:
                dev_reg_local.async_update_device(
                    dev_entry_local.id, name_by_user=display_name
                )

            return self.async_create_entry(title="", data=new_options)

        name = cfg.get(CONF_DEVICE_NAME, uid)
        protocol = cfg.get(CONF_DEVICE_PROTOCOL, "")
        model = cfg.get(CONF_DEVICE_MODEL, "")

        if uid.startswith("sensor_"):
            # Show base name (without type suffix) for grouped display
            name = _strip_sensor_suffix(name)
            sensor_id = cfg.get("sensor_id", 0)
            schema_dict: dict[Any, Any] = {
                vol.Required("name", default=name): str,
                vol.Required("sensor_id", default=sensor_id): int,
            }
        else:
            house = cfg.get(CONF_DEVICE_HOUSE, "")
            unit = cfg.get(CONF_DEVICE_UNIT, "")
            schema_dict = {
                vol.Required("name", default=name): str,
                vol.Optional("house", default=house): str,
                vol.Optional("unit", default=unit): str,
            }

        return self.async_show_form(
            step_id="device_detail",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "device_uid": uid,
                "protocol": protocol,
                "model": model,
            },
        )

    # -----------------------------------------------------------------
    # Move device to another TellStick instance
    # -----------------------------------------------------------------

    async def async_step_move_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select the target TellStick instance to move this device to."""
        uid = self._edit_uid
        devices = self.config_entry.options.get(CONF_DEVICES, {})
        cfg = devices.get(uid, {})
        name = cfg.get(CONF_DEVICE_NAME, uid)
        if uid.startswith("sensor_"):
            name = _strip_sensor_suffix(name)

        if user_input is not None:
            self._move_target_entry_id = user_input["target_entry"]
            return await self.async_step_move_device_confirm()

        primaries = self._get_other_primary_entries()
        options: dict[str, str] = {e.entry_id: e.title for e in primaries}

        return self.async_show_form(
            step_id="move_device",
            data_schema=vol.Schema(
                {vol.Required("target_entry"): vol.In(options)}
            ),
            description_placeholders={"name": name},
        )

    async def async_step_move_device_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm moving the device to the selected instance."""
        uid = self._edit_uid
        src_entry = self.config_entry
        dst_entry_id = self._move_target_entry_id
        dst_entry = self.hass.config_entries.async_get_entry(dst_entry_id)

        src_devices = dict(src_entry.options.get(CONF_DEVICES, {}))
        cfg = dict(src_devices.get(uid, {}))
        name = cfg.get(CONF_DEVICE_NAME, uid)
        if uid.startswith("sensor_"):
            name = _strip_sensor_suffix(name)

        if user_input is not None and dst_entry is not None:
            dst_devices = dict(dst_entry.options.get(CONF_DEVICES, {}))

            # Collect all UIDs to move (sensors: include companion entries)
            uids_to_move = [uid]
            if uid.startswith("sensor_"):
                sensor_id = src_devices.get(uid, {}).get("sensor_id")
                if sensor_id is not None:
                    for o_uid, o_cfg in src_devices.items():
                        if (
                            o_uid != uid
                            and o_uid.startswith("sensor_")
                            and o_cfg.get("sensor_id") == sensor_id
                        ):
                            uids_to_move.append(o_uid)

            # Copy device configs to destination and remove from source
            for move_uid in uids_to_move:
                dst_devices[move_uid] = src_devices.pop(move_uid, {})

            # Update entity registry — change unique_id and config_entry_id
            # so the entity keeps its entity_id and state history.
            ent_reg = er.async_get(self.hass)
            for ent in list(
                er.async_entries_for_config_entry(ent_reg, src_entry.entry_id)
            ):
                for move_uid in uids_to_move:
                    if ent.unique_id == f"{src_entry.entry_id}_{move_uid}":
                        new_unique_id = f"{dst_entry_id}_{move_uid}"
                        try:
                            ent_reg.async_update_entity(
                                ent.entity_id,
                                new_unique_id=new_unique_id,
                                config_entry_id=dst_entry_id,
                            )
                        except Exception:  # noqa: BLE001
                            _LOGGER.warning(
                                "Could not update entity registry for %s during move",
                                ent.entity_id,
                            )

            # Persist updated options on both entries
            new_src_opts = dict(src_entry.options)
            new_src_opts[CONF_DEVICES] = src_devices
            self.hass.config_entries.async_update_entry(
                src_entry, options=new_src_opts
            )
            new_dst_opts = dict(dst_entry.options)
            new_dst_opts[CONF_DEVICES] = dst_devices
            self.hass.config_entries.async_update_entry(
                dst_entry, options=new_dst_opts
            )

            # Reload both entries so entities are correctly placed
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(src_entry.entry_id)
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(dst_entry_id)
            )
            return self.async_abort(reason="device_moved")

        dst_title = dst_entry.title if dst_entry else dst_entry_id
        return self.async_show_form(
            step_id="move_device_confirm",
            description_placeholders={
                "name": name,
                "src": src_entry.title,
                "dst": dst_title,
            },
        )

    # -----------------------------------------------------------------
    # Group device under a shared HA device
    # -----------------------------------------------------------------

    async def async_step_group_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set or clear a device group for this device."""
        uid = self._edit_uid
        devices = dict(self.config_entry.options.get(CONF_DEVICES, {}))
        cfg = dict(devices.get(uid, {}))
        name = cfg.get(CONF_DEVICE_NAME, uid)

        if user_input is not None:
            group_uid = user_input.get("group_uid", "").strip()
            if group_uid:
                cfg["group_uid"] = group_uid
            else:
                cfg.pop("group_uid", None)
            devices[uid] = cfg
            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = devices
            # Reload so the entity picks up the updated device_info grouping
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
            )
            return self.async_create_entry(title="", data=new_options)

        # Suggest existing group names from all devices for convenience
        current_group = cfg.get("group_uid", "")
        existing_groups: list[str] = sorted(
            {
                d_cfg["group_uid"]
                for d_cfg in devices.values()
                if d_cfg.get("group_uid")
            }
        )

        return self.async_show_form(
            step_id="group_device",
            data_schema=vol.Schema(
                {
                    vol.Optional("group_uid", default=current_group): str,
                }
            ),
            description_placeholders={
                "name": name,
                "existing_groups": ", ".join(existing_groups) or "—",
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
            controller: Any = entry_data.get(
                ENTRY_TELLSTICK_CONTROLLER
            )
            device_id_map: dict[str, Any] = entry_data.get(
                ENTRY_DEVICE_ID_MAP, {}
            )
            device_or_id = device_id_map.get(uid)

            if controller and device_or_id is not None:
                try:
                    await controller.learn(device_or_id)
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

            entry_data = self.hass.data.get(DOMAIN, {}).get(
                self.config_entry.entry_id, {}
            )
            controller: Any = entry_data.get(
                ENTRY_TELLSTICK_CONTROLLER
            )
            device_id_map: dict[str, Any] = entry_data.get(
                ENTRY_DEVICE_ID_MAP, {}
            )
            discovered: set[str] = entry_data.get("_discovered_uids", set())
            dev_reg = dr.async_get(self.hass)
            ent_reg = er.async_get(self.hass)
            entry_id = self.config_entry.entry_id

            # For sensors: collect all entries for the same sensor_id
            # (temp + hum share one physical device).
            uids_to_remove = [uid]
            if uid.startswith("sensor_"):
                sensor_id = cfg.get("sensor_id")
                if sensor_id is not None:
                    for other_uid, other_cfg in devices.items():
                        if (
                            other_uid != uid
                            and other_uid.startswith("sensor_")
                            and other_cfg.get("sensor_id") == sensor_id
                        ):
                            uids_to_remove.append(other_uid)

            new_devices = dict(devices)
            ignored = dict(
                self.config_entry.options.get(CONF_IGNORED_UIDS, {})
            )

            for remove_uid in uids_to_remove:
                remove_cfg = new_devices.pop(remove_uid, {})

                # Remove from telldusd
                if controller and remove_uid in device_id_map:
                    try:
                        await controller.remove_device(
                            device_id_map[remove_uid]
                        )
                    except Exception:  # noqa: BLE001
                        _LOGGER.warning(
                            "Could not remove %s from telldusd", remove_uid
                        )
                    device_id_map.pop(remove_uid, None)

                if ignore:
                    ignored[remove_uid] = remove_cfg.get(
                        CONF_DEVICE_NAME, remove_uid
                    )

                discovered.discard(remove_uid)

            # Remove entity registry entries so that if the same device is
            # later re-added with a new name it gets fresh entity_ids instead
            # of inheriting the old ones.  Single pass for all removed UIDs.
            # Issue #33.
            remove_unique_ids = {
                f"{entry_id}_{r}" for r in uids_to_remove
            }
            for ent in list(
                er.async_entries_for_config_entry(ent_reg, entry_id)
            ):
                if ent.unique_id in remove_unique_ids:
                    try:
                        ent_reg.async_remove(ent.entity_id)
                        # Clear the DeletedRegistryEntry tombstone so that if
                        # the same device is re-added later, HA creates a fresh
                        # entity_id instead of restoring the old one.  Issue #33.
                        ent_reg.deleted_entities.pop(
                            (ent.domain, ent.platform, ent.unique_id), None
                        )
                    except Exception:  # noqa: BLE001
                        _LOGGER.warning(
                            "Could not remove entity %s from registry",
                            ent.entity_id,
                        )

            # Remove from device registry.  Sensors use a shared device
            # identifier: sensor_{sensor_id} (no type suffix).
            if uid.startswith("sensor_"):
                sensor_id = cfg.get("sensor_id")
                dev_key = f"sensor_{sensor_id}" if sensor_id else uid
            else:
                dev_key = uid
            device_entry = dev_reg.async_get_device(
                identifiers={
                    (DOMAIN, f"{self.config_entry.entry_id}_{dev_key}")
                }
            )
            if device_entry:
                dev_id = device_entry.id
                dev_reg.async_remove_device(dev_id)
                # Clear the device tombstone so the old area, labels, and
                # name_by_user are not resurrected when the device is re-added.
                # HA 2025.6+ stores these in DeletedDeviceEntry and
                # to_device_entry() restores them on re-add.  Issue #33.
                dev_reg.deleted_devices.pop(dev_id, None)

            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = new_devices
            if ignore:
                new_options[CONF_IGNORED_UIDS] = ignored

            return self.async_create_entry(title="", data=new_options)

        # Show base name for grouped sensors
        name = cfg.get(CONF_DEVICE_NAME, uid)
        if uid.startswith("sensor_"):
            name = _strip_sensor_suffix(name)

        return self.async_show_form(
            step_id="delete_device",
            data_schema=vol.Schema(
                {
                    vol.Required("ignore", default=True): bool,
                }
            ),
            description_placeholders={
                "name": name,
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
            controller: Any = entry_data.get(
                ENTRY_TELLSTICK_CONTROLLER
            )
            device_id_map: dict[str, Any] = entry_data.get(
                ENTRY_DEVICE_ID_MAP, {}
            )
            dev_reg = dr.async_get(self.hass)
            ent_reg = er.async_get(self.hass)
            entry_id = self.config_entry.entry_id
            discovered: set[str] = entry_data.get("_discovered_uids", set())

            new_devices = dict(devices)
            ignored = dict(
                self.config_entry.options.get(CONF_IGNORED_UIDS, {})
            )

            # Expand selection to include companion sensor entries
            all_uids: list[str] = []
            for uid in selected:
                all_uids.append(uid)
                if uid.startswith("sensor_"):
                    sel_cfg = new_devices.get(uid, {})
                    sid = sel_cfg.get("sensor_id")
                    if sid is not None:
                        for o_uid, o_cfg in new_devices.items():
                            if (
                                o_uid != uid
                                and o_uid.startswith("sensor_")
                                and o_cfg.get("sensor_id") == sid
                                and o_uid not in all_uids
                            ):
                                all_uids.append(o_uid)

            for uid in all_uids:
                cfg = new_devices.pop(uid, {})

                # Remove from telldusd
                if controller and uid in device_id_map:
                    try:
                        await controller.remove_device(device_id_map[uid])
                    except Exception:  # noqa: BLE001
                        pass
                    device_id_map.pop(uid, None)

                # Remove from device registry.  Sensors use shared device
                # identifier: sensor_{sensor_id} (no type suffix).
                if uid.startswith("sensor_"):
                    sensor_id = cfg.get("sensor_id")
                    dev_key = f"sensor_{sensor_id}" if sensor_id else uid
                else:
                    dev_key = uid
                device_entry = dev_reg.async_get_device(
                    identifiers={
                        (DOMAIN, f"{self.config_entry.entry_id}_{dev_key}")
                    }
                )
                if device_entry:
                    dev_id = device_entry.id
                    dev_reg.async_remove_device(dev_id)
                    # Clear tombstone so area/labels/name_by_user are not
                    # resurrected on re-add (HA 2025.6+).  Issue #33.
                    dev_reg.deleted_devices.pop(dev_id, None)

                if ignore:
                    ignored[uid] = cfg.get(CONF_DEVICE_NAME, uid)

                discovered.discard(uid)
                # Also clear the per-sensor-id dedup key so re-discovery fires
                # on the next event.  The discovery flow (automatic_add=False)
                # adds "sensor_{id}" to _discovered_uids; only discarding the
                # specific "sensor_{id}_{suffix}" leaves that key blocking
                # future discovery.  UID format: sensor_{sensor_id}_{suffix}.
                if uid.startswith("sensor_"):
                    parts = uid.split("_", 2)
                    if len(parts) >= 2:
                        discovered.discard(f"sensor_{parts[1]}")

            # Remove entity registry entries so that if the same device is
            # later re-added with a new name it gets fresh entity_ids instead
            # of inheriting the old ones.  Single pass for all removed UIDs.
            # Issue #33.
            remove_unique_ids = {f"{entry_id}_{u}" for u in all_uids}
            for ent in list(
                er.async_entries_for_config_entry(ent_reg, entry_id)
            ):
                if ent.unique_id in remove_unique_ids:
                    try:
                        ent_reg.async_remove(ent.entity_id)
                        # Clear the DeletedRegistryEntry tombstone so that if
                        # the same device is re-added later, HA creates a fresh
                        # entity_id instead of restoring the old one.  Issue #33.
                        ent_reg.deleted_entities.pop(
                            (ent.domain, ent.platform, ent.unique_id), None
                        )
                    except Exception:  # noqa: BLE001
                        _LOGGER.warning(
                            "Could not remove entity %s from registry",
                            ent.entity_id,
                        )

            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = new_devices
            if ignore:
                new_options[CONF_IGNORED_UIDS] = ignored
            return self.async_create_entry(title="", data=new_options)

        # Group sensors by sensor_id in the multi-select
        labels: dict[str, str] = {}
        seen_sensor_ids: set[int] = set()
        for uid, cfg in devices.items():
            if uid.startswith("sensor_"):
                sid = cfg.get("sensor_id")
                if sid is not None and sid in seen_sensor_ids:
                    continue
                if sid is not None:
                    seen_sensor_ids.add(sid)
                labels[uid] = _build_device_label(
                    uid, cfg, sensor_grouped=True
                )
            else:
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
            seen_proto_models: dict[str, float] = entry_data.get(
                "_discovered_protocol_models", {}
            )
            for uid in to_unignore:
                discovered.discard(uid)
                if uid.startswith("sensor_"):
                    # Also clear the per-sensor-id dedup key so re-discovery
                    # fires when automatic_add is off.  The discovery flow adds
                    # "sensor_{id}" (no suffix) to _discovered_uids; discarding
                    # only the specific "sensor_{id}_{suffix}" UID leaves that
                    # key in place and silently blocks the next event.
                    # UID format: sensor_{sensor_id}_{suffix}.
                    parts = uid.split("_", 2)
                    if len(parts) >= 2:
                        discovered.discard(f"sensor_{parts[1]}")
                else:
                    # Clear protocol+model deduplication so re-discovery can fire.
                    # UID format: "{protocol}_{model}_{house}_{unit}".
                    # proto_model_key used in _fire_device_discovery is "{protocol}_{model}".
                    parts = uid.split("_", 2)
                    if len(parts) >= 2:
                        seen_proto_models.pop(f"{parts[0]}_{parts[1]}", None)

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
    _widget_id: int = 8  # populated by by_brand / by_protocol step

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 0: Choose how to find the device — by brand or by protocol."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["by_brand", "by_protocol"],
        )

    async def async_step_by_brand(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Search by brand name (existing catalog)."""
        if user_input is not None:
            self._device_type = user_input["device_type"]
            protocol, model, widget = DEVICE_CATALOG_MAP[self._device_type]
            self._widget_id = widget
            self._new_device = {
                CONF_DEVICE_NAME: user_input["name"],
                CONF_DEVICE_PROTOCOL: protocol,
                CONF_DEVICE_MODEL: model,
            }
            return await self.async_step_params()

        return self.async_show_form(
            step_id="by_brand",
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

    async def async_step_by_protocol(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Search by protocol name."""
        if user_input is not None:
            self._device_type = user_input["device_type"]
            protocol, model, widget = PROTOCOL_MODEL_MAP[self._device_type]
            self._widget_id = widget
            self._new_device = {
                CONF_DEVICE_NAME: user_input["name"],
                CONF_DEVICE_PROTOCOL: protocol,
                CONF_DEVICE_MODEL: model,
            }
            return await self.async_step_params()

        return self.async_show_form(
            step_id="by_protocol",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required(
                        "device_type",
                        default=PROTOCOL_MODEL_LABELS[0],
                    ): vol.In(PROTOCOL_MODEL_LABELS),
                }
            ),
        )

    async def async_step_params(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 2: Enter device-specific parameters with correct ranges."""
        errors: dict[str, str] = {}
        widget = self._widget_id

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
        """Send the RF teach/pairing signal after user puts device in learn mode.

        Works for both backends:
        - **Duo**: registers the device with telldusd (``add_device`` → int ID),
          sends a LEARN signal via that ID, stores the int in ``device_id_map``.
        - **Net/ZNet**: no telldusd registry; builds a device dict from the
          stored parameters and sends a LEARN RF command directly via UDP.
          Stores the device dict in ``device_id_map`` so all subsequent
          turn_on / turn_off / dim calls work.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            entry = self._get_entry()
            backend = entry.data.get(CONF_BACKEND, BACKEND_DUO)
            try:
                entry_data = self.hass.data[DOMAIN].get(entry.entry_id, {})
                controller: Any = entry_data.get(
                    ENTRY_TELLSTICK_CONTROLLER
                )
                if controller is None:
                    raise RuntimeError("Controller not available")

                if backend == BACKEND_NET:
                    # Net backend: no device registry.  Build the device dict
                    # and send the learn/teach RF command directly.
                    device_dict: dict[str, Any] = {
                        CONF_DEVICE_PROTOCOL: self._new_device[CONF_DEVICE_PROTOCOL],
                        CONF_DEVICE_MODEL: self._new_device.get(CONF_DEVICE_MODEL, ""),
                        CONF_DEVICE_HOUSE: self._new_device.get(CONF_DEVICE_HOUSE, ""),
                        CONF_DEVICE_UNIT: self._new_device.get(CONF_DEVICE_UNIT, ""),
                    }
                    await controller.learn(device_dict)
                    device_id_map_entry: Any = device_dict
                else:
                    # Duo backend: register with telldusd, then send LEARN.
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
                    device_id_map_entry = telldusd_id

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

                # Store device ID / dict in runtime map so the entity can
                # send commands immediately (without a restart).
                device_id_map: dict[str, Any] = entry_data.get(
                    ENTRY_DEVICE_ID_MAP, {}
                )
                device_id_map[device_uid] = device_id_map_entry

                # Register on all mirror controllers too
                from . import _register_device_on_mirror  # noqa: PLC0415

                for mirror in entry_data.get(ENTRY_MIRRORS, []):
                    await _register_device_on_mirror(
                        mirror,
                        device_uid,
                        self._new_device[CONF_DEVICE_NAME],
                        self._new_device[CONF_DEVICE_PROTOCOL],
                        self._new_device.get(CONF_DEVICE_MODEL, ""),
                        self._new_device.get(CONF_DEVICE_HOUSE, ""),
                        self._new_device.get(CONF_DEVICE_UNIT, ""),
                    )

                # Persist in entry.options[CONF_DEVICES]
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

                # Dispatch a synthetic RawDeviceEvent so platforms create the
                # entity immediately.  Use the RF-normalized model name so
                # the UID built from the event matches the one in device_id_map.
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
