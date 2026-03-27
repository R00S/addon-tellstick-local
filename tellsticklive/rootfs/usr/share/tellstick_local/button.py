"""Button platform for TellStick Local integration.

Provides:
- **Send learn signal** button on each non-sensor device.
- **EF test — sequence ALL** buttons (one for raw variants, one for native
  variants) that fire all encoding variants in sequence with 2 s delays,
  so testers can watch the TellStick LED to see which variant(s) make
  the hardware blink.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import RawDeviceEvent
from .const import (
    CONF_DEVICE_HOUSE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PROTOCOL,
    CONF_DEVICE_UNIT,
    CONF_DEVICES,
    DOMAIN,
    EF_TEST_NATIVE_VARIANTS,
    EF_TEST_RAW_VARIANTS,
    EF_TEST_VARIANTS,
    ENTRY_DEVICE_ID_MAP,
    ENTRY_MIRRORS,
    ENTRY_TELLSTICK_CONTROLLER,
    SIGNAL_NEW_DEVICE,
)

_LOGGER = logging.getLogger(__name__)

# Delay between variants when running the "sequence ALL" test (seconds).
_EF_SEQ_DELAY = 2.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TellStick learn button entities."""
    new_device_signal = SIGNAL_NEW_DEVICE.format(entry.entry_id)

    known: set[str] = set()

    # Pre-create button entities for stored non-sensor devices
    stored_entities: list[ButtonEntity] = []
    for device_uid, device_cfg in entry.options.get(CONF_DEVICES, {}).items():
        if device_uid.startswith("sensor_"):
            continue
        known.add(device_uid)

        model = device_cfg.get(CONF_DEVICE_MODEL, "")

        # EF test "sequence ALL" markers → create the appropriate sequence button
        _EF_SEQ_MODELS: dict[str, tuple[list[tuple[str, str]], str]] = {
            "ef_test_sequence": (EF_TEST_VARIANTS, "ef_test_sequence"),
            "ef_test_raw_sequence": (EF_TEST_RAW_VARIANTS, "ef_test_raw_sequence"),
            "ef_test_native_sequence": (EF_TEST_NATIVE_VARIANTS, "ef_test_native_sequence"),
        }

        # EF test "sequence ALL" marker → create the sequence button
        if model in _EF_SEQ_MODELS:
            variants_list, translation_key = _EF_SEQ_MODELS[model]
            stored_entities.append(
                EFTestSequenceButton(
                    entry_id=entry.entry_id,
                    device_uid=device_uid,
                    name=device_cfg.get(CONF_DEVICE_NAME, "EF test — sequence ALL"),
                    house=device_cfg.get(CONF_DEVICE_HOUSE, "100"),
                    unit=device_cfg.get(CONF_DEVICE_UNIT, "1"),
                    group_uid=device_cfg.get("group_uid") or None,
                    variants_list=variants_list,
                    translation_key_override=translation_key,
                )
            )
            continue

        # Normal device → learn button
        stored_entities.append(
            TellStickLearnButton(
                entry_id=entry.entry_id,
                device_uid=device_uid,
                name=device_cfg.get(CONF_DEVICE_NAME, f"TellStick {device_uid}"),
                protocol=device_cfg.get(CONF_DEVICE_PROTOCOL, ""),
                model=model,
                group_uid=device_cfg.get("group_uid") or None,
            )
        )
    if stored_entities:
        async_add_entities(stored_entities)

    @callback
    def _async_new_device(event: Any) -> None:
        if not isinstance(event, RawDeviceEvent):
            return
        params = event.params
        uid = event.device_id
        if not uid or uid in known:
            return
        # Sensors don't get learn buttons
        if uid.startswith("sensor_"):
            return
        known.add(uid)
        stored = entry.options.get(CONF_DEVICES, {}).get(uid, {})
        name = stored.get(CONF_DEVICE_NAME) or f"TellStick {uid}"
        entity = TellStickLearnButton(
            entry_id=entry.entry_id,
            device_uid=uid,
            name=name,
            protocol=params.get("protocol", ""),
            model=params.get("model", ""),
            group_uid=stored.get("group_uid") or None,
        )
        async_add_entities([entity])

    entry.async_on_unload(
        async_dispatcher_connect(hass, new_device_signal, _async_new_device)
    )


class TellStickLearnButton(ButtonEntity):
    """Button to send a learn/pairing signal for a TellStick device.

    Appears on the device page so users can trigger pairing without
    navigating to the integration's options flow.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:broadcast"
    _attr_translation_key = "learn"

    def __init__(
        self,
        entry_id: str,
        device_uid: str,
        name: str,
        protocol: str,
        model: str,
        group_uid: str | None = None,
    ) -> None:
        """Initialize the learn button."""
        self._entry_id = entry_id
        self._device_uid = device_uid
        self._attr_unique_id = f"{entry_id}_{device_uid}_learn"
        if group_uid:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_group_{group_uid}")},
                name=group_uid,
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_{device_uid}")},
            )

    async def async_press(self) -> None:
        """Send learn signal when pressed."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        controller: Any = entry_data.get(
            ENTRY_TELLSTICK_CONTROLLER
        )
        device_id_map: dict[str, Any] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})
        device_or_id = device_id_map.get(self._device_uid)

        if controller is None or device_or_id is None:
            _LOGGER.error(
                "Cannot send learn signal for %s: controller or device ID unavailable",
                self._device_uid,
            )
            return

        _LOGGER.debug("Sending learn signal for %s (id/dict %s)", self._device_uid, device_or_id)
        await controller.learn(device_or_id)

        # Also send learn signal to all mirrors
        for mirror in entry_data.get(ENTRY_MIRRORS, []):
            mirror_device_id = mirror["device_id_map"].get(self._device_uid)
            if mirror_device_id is not None:
                try:
                    await mirror["controller"].learn(mirror_device_id)
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "Mirror learn command failed for %s",
                        self._device_uid,
                        exc_info=True,
                    )


# ---------------------------------------------------------------------------
# EF test — sequence ALL button
# ---------------------------------------------------------------------------


class EFTestSequenceButton(ButtonEntity):
    """Button that fires all everflourish encoding variants in sequence.

    When pressed, iterates through every variant in the provided list, sends a
    ``turn_on`` command for that variant, waits ``_EF_SEQ_DELAY`` seconds,
    then moves to the next.  The tester watches the TellStick LED to see
    which variant(s) cause the hardware to blink.

    Progress is logged and visible via the entity's ``extra_state_attributes``
    (shows the variant currently being tested and the overall progress).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:playlist-play"

    def __init__(
        self,
        entry_id: str,
        device_uid: str,
        name: str,
        house: str,
        unit: str,
        group_uid: str | None = None,
        variants_list: list[tuple[str, str]] | None = None,
        translation_key_override: str = "ef_test_sequence",
    ) -> None:
        """Initialize the EF sequence button."""
        self._entry_id = entry_id
        self._device_uid = device_uid
        self._house = house
        self._unit = unit
        self._variants = variants_list or EF_TEST_VARIANTS
        self._attr_translation_key = translation_key_override
        self._attr_unique_id = f"{entry_id}_{device_uid}_ef_seq"
        self._running = False
        self._current_variant = ""
        self._progress = ""
        if group_uid:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_group_{group_uid}")},
                name=group_uid,
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_{device_uid}")},
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose current test progress."""
        return {
            "running": self._running,
            "current_variant": self._current_variant,
            "progress": self._progress,
        }

    async def async_press(self) -> None:
        """Fire all EF variants in sequence with delays."""
        if self._running:
            _LOGGER.warning("EF test sequence already running — ignoring press")
            return

        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        controller: Any = entry_data.get(ENTRY_TELLSTICK_CONTROLLER)
        device_id_map: dict[str, Any] = entry_data.get(ENTRY_DEVICE_ID_MAP, {})

        if controller is None:
            _LOGGER.error("EF test sequence: controller not available")
            return

        self._running = True
        total = len(self._variants)

        try:
            for idx, (variant_suffix, label) in enumerate(self._variants, 1):
                self._current_variant = f"{variant_suffix}: {label}"
                self._progress = f"{idx}/{total}"
                self.async_write_ha_state()

                # Build the device dict for this variant
                model = f"selflearning-switch:{variant_suffix}"
                # Use same custom UID format as config_flow ef_test_device step
                device_uid = f"ef_test_{variant_suffix}_{self._house}_{self._unit}"
                device_dict = device_id_map.get(device_uid)

                if device_dict is None:
                    # Build one on the fly if not in the map
                    device_dict = {
                        "protocol": "everflourish",
                        "model": model,
                        "house": self._house,
                        "unit": self._unit,
                    }

                _LOGGER.info(
                    "EF test sequence %d/%d: sending turn_on via %s (%s)",
                    idx, total, variant_suffix, label,
                )
                try:
                    await controller.turn_on(device_dict)
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "EF test sequence: variant %s failed", variant_suffix,
                        exc_info=True,
                    )

                # Wait between variants so the tester can see each blink
                if idx < total:
                    await asyncio.sleep(_EF_SEQ_DELAY)
        finally:
            self._running = False
            self._current_variant = "done"
            self._progress = f"{total}/{total}"
            self.async_write_ha_state()
            _LOGGER.info("EF test sequence completed (%d variants)", total)
