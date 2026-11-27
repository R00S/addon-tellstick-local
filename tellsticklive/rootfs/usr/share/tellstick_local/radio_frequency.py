"""Radio frequency transmitter platform — TellStick as a generic RF sender.

Home Assistant's ``radio_frequency`` building block (2026.5+) lets device
integrations send raw OOK commands through a transmitter they do not own: the
user picks a transmitter, and the integration hands over a
``RadioFrequencyCommand`` carrying signed microsecond timings.

Registering a TellStick here means *any* such integration — the built-in Novy
Cooker Hood and Honeywell String Lights, third-party ones, and whatever is
added later — can transmit through a TellStick without this project
implementing a single protocol of its own.  We only translate timings into
the Duo / Net v1 pulse wire format.

Only raw-capable hardware is exposed: a Duo, or an original TellStick Net
(v1).  A Net v2 / ZNet drops raw frames in its firmware and must never appear
as a selectable transmitter, and mirror entries are infrastructure — they are
never offered, because a command sent to a mirror would not be mirrored.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

try:
    from homeassistant.components.radio_frequency import (
        RadioFrequencyTransmitterEntity,
    )
    from rf_protocols import RadioFrequencyCommand

    RF_TRANSMITTER_AVAILABLE = True
except ImportError:  # Home Assistant older than 2026.5
    # The manifest asks for 2026.5, but Home Assistant does not enforce that
    # key for custom integrations.  Without this guard the whole integration
    # would fail to set up on an older Core; with it, only this optional
    # feature is skipped.
    RF_TRANSMITTER_AVAILABLE = False

    class RadioFrequencyTransmitterEntity:  # type: ignore[no-redef]
        """Stand-in base so this module still imports on older Core."""

    RadioFrequencyCommand = Any  # type: ignore[misc,assignment]

from .const import (
    BACKEND_DUO,
    CONF_BACKEND,
    CONF_MIRROR_OF,
    DOMAIN,
    ENTRY_TELLSTICK_CONTROLLER,
    NET_V1_MAX_PULSES,
    timings_to_raw_frame,
)
from .entity import async_mirror_raw_command

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# The TellStick front end is a 433.92 MHz OOK device.  Home Assistant filters
# transmitters by frequency for the consumer, so a 315 or 868 MHz device never
# sees this one.
SUPPORTED_FREQUENCY_RANGES: list[tuple[int, int]] = [(433_050_000, 434_790_000)]

# tdSendRawCommand answers -5 (TELLSTICK_ERROR_COMMUNICATION) when the
# firmware ACK times out on a long transmission; the hardware still sends it.
_ACK_TIMEOUT = -5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Expose a raw-capable TellStick as a radio frequency transmitter."""
    if not RF_TRANSMITTER_AVAILABLE:
        _LOGGER.debug(
            "Radio frequency transmitters need Home Assistant 2026.5 or newer; "
            "skipping for %s",
            entry.title,
        )
        return

    if entry.data.get(CONF_MIRROR_OF):
        # A mirror has no devices of its own and is never a send target; the
        # primary's transmitter already replicates every frame to it.
        return

    controller = (
        hass.data.get(DOMAIN, {})
        .get(entry.entry_id, {})
        .get(ENTRY_TELLSTICK_CONTROLLER)
    )
    supports_raw = getattr(controller, "supports_raw_pulses", None)
    if supports_raw is None or not await supports_raw():
        _LOGGER.debug(
            "TellStick %s cannot send raw pulses; not exposed as an RF transmitter",
            entry.title,
        )
        return

    _async_register_transmitter(hass, entry)
    async_add_entities([TellStickRadioFrequency(entry, controller)])


@callback
def _async_register_transmitter(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register the transmitter entity enabled, before it is added.

    Home Assistant registers an entity of a config entry that has
    ``pref_disable_new_entities`` set as ``disabled_by=integration``.  A
    disabled entity is not added to the state machine, so no consumer
    integration could ever pick it — the feature would silently do nothing.
    Claiming the registry entry ourselves with ``disabled_by=None`` keeps it
    enabled regardless of that preference, and an entry left disabled by an
    earlier build is switched back on and picked up by a single reload.
    """
    ent_reg = er.async_get(hass)
    unique_id = f"{entry.entry_id}_rf_transmitter"
    entity_id = ent_reg.async_get_entity_id("radio_frequency", DOMAIN, unique_id)
    if entity_id is None:
        ent_reg.async_get_or_create(
            "radio_frequency",
            DOMAIN,
            unique_id,
            config_entry=entry,
            disabled_by=None,
            has_entity_name=True,
            suggested_object_id=f"{entry.title} rf transmitter",
        )
        return

    registry_entry = ent_reg.async_get(entity_id)
    if (
        registry_entry is not None
        and registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    ):
        _LOGGER.info(
            "Re-enabling disabled RF transmitter %s and reloading to add it",
            entity_id,
        )
        ent_reg.async_update_entity(entity_id, disabled_by=None)
        hass.config_entries.async_schedule_reload(entry.entry_id)


class TellStickRadioFrequency(RadioFrequencyTransmitterEntity):
    """A TellStick exposed as a raw OOK transmitter."""

    _attr_has_entity_name = True
    _attr_translation_key = "rf_transmitter"

    def __init__(self, entry: ConfigEntry, controller: Any) -> None:
        """Initialise the transmitter."""
        super().__init__()
        self._entry_id = entry.entry_id
        self._controller = controller
        self._is_duo = entry.data.get(CONF_BACKEND) == BACKEND_DUO
        # A Duo has no payload ceiling; a Net v1 packet is 199 bytes.
        self._max_pulses = None if self._is_duo else NET_V1_MAX_PULSES
        self._attr_unique_id = f"{entry.entry_id}_rf_transmitter"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_hub")},
            name=entry.title,
            manufacturer="Telldus",
            model="TellStick Duo" if self._is_duo else "TellStick Net",
        )

    @property
    def supported_frequency_ranges(self) -> list[tuple[int, int]]:
        """Return the RF band this TellStick can transmit on."""
        return SUPPORTED_FREQUENCY_RANGES

    async def async_send_command(self, command: RadioFrequencyCommand) -> None:
        """Transmit a radio frequency command through the TellStick."""
        timings = command.get_raw_timings()
        try:
            frame = timings_to_raw_frame(
                timings,
                command.repeat_count,
                max_pulses=self._max_pulses,
            )
        except ValueError as err:
            _LOGGER.warning(
                "RF transmitter %s cannot send this command (%s): %s",
                self.entity_id,
                err,
                "no timings" if not timings else "frame exceeds the backend limit",
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="frame_too_long" if timings else "no_timings",
                translation_placeholders={
                    "pulses": len(timings),
                    "limit": self._max_pulses or len(timings),
                },
            ) from err

        result = await self._controller.send_raw_command(frame)
        if result not in (0, _ACK_TIMEOUT):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="transmit_failed",
                translation_placeholders={"result": result},
            )
        if result == _ACK_TIMEOUT:
            _LOGGER.debug(
                "RF transmitter %s: ACK timeout on a long transmission "
                "(the hardware still sends it)",
                self.entity_id,
            )

        _LOGGER.debug(
            "RF transmitter %s: sent %d timings as %d bytes "
            "(repeat=%s, %s Hz, backend=%s)",
            self.entity_id,
            len(timings),
            len(frame),
            command.repeat_count,
            command.frequency,
            "duo" if self._is_duo else "net-v1",
        )

        # Mirrors reinforce our own devices' commands, so they must reinforce
        # these too.  The helper sleeps the RF-collision window and is a no-op
        # when the entry has no mirrors.
        await async_mirror_raw_command(self.hass, self._entry_id, frame)
