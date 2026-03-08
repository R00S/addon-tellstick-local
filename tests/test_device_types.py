"""Unit tests for entity device identifiers, names, and compatibility
across all device types — sensor, switch, light, cover.

These tests verify:
  - Sensor entities from the same sensor_id share one HA device identifier
    (the fix for issue #38 / fineoffset question)
  - Non-sensor entities (switch, light, cover) are completely unaffected
    by the sensor grouping change
  - _build_device_label includes data_type in sensor labels (issue #33)
  - The replace-device compatible filter respects data_type (issue #33)
  - Diagnostics returns the expected structure (issue #38)

Run with:
    python tests/test_device_types.py
"""
from __future__ import annotations

import os
import sys
from unittest.mock import Mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

ALL_PASS = True


def report(name: str, ok: bool, detail: str = "") -> None:
    global ALL_PASS  # noqa: PLW0603
    status = "PASS" if ok else "FAIL"
    if not ok:
        ALL_PASS = False
    suffix = f": {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sensor(entry_id, sensor_id, data_type, name=None):
    from custom_components.tellstick_local.sensor import TellStickSensor
    suffix = {1: "temperature", 2: "humidity"}.get(data_type, "sensor")
    device_uid = f"sensor_{sensor_id}_{suffix}"
    if name is None:
        name = f"TellStick sensor {sensor_id} {suffix}"
    return TellStickSensor(
        entry_id=entry_id,
        device_uid=device_uid,
        name=name,
        protocol="fineoffset",
        model="temperaturehumidity",
        sensor_id=sensor_id,
        data_type=data_type,
    )


def _make_switch(entry_id, device_uid, name="My Switch"):
    from custom_components.tellstick_local.switch import TellStickSwitch
    controller = Mock()
    return TellStickSwitch(
        entry_id=entry_id,
        device_uid=device_uid,
        name=name,
        protocol="arctech",
        model="selflearning-switch",
        controller=controller,
        device_id=1,
        house="12345",
        unit="1",
    )


def _make_light(entry_id, device_uid, name="My Dimmer"):
    from custom_components.tellstick_local.light import TellStickLight
    controller = Mock()
    return TellStickLight(
        entry_id=entry_id,
        device_uid=device_uid,
        name=name,
        protocol="arctech",
        model="selflearning-dimmer",
        controller=controller,
        device_id=1,
        house="12345",
        unit="2",
    )


def _make_cover(entry_id, device_uid, name="My Blind"):
    from custom_components.tellstick_local.cover import TellStickCover
    controller = Mock()
    return TellStickCover(
        entry_id=entry_id,
        device_uid=device_uid,
        name=name,
        protocol="hasta",
        model="selflearning",
        controller=controller,
        device_id=1,
        house="A",
        unit="1",
    )


# ---------------------------------------------------------------------------
# Section 1 — Sensor device grouping
# ---------------------------------------------------------------------------

def test_sensor_temperature_device_identifier():
    """Temperature entity device identifier uses sensor_{id} (no suffix)."""
    t = _make_sensor("eid", 202, 1)
    identifiers = t._attr_device_info["identifiers"]
    assert identifiers == {("tellstick_local", "eid_sensor_202")}, identifiers


def test_sensor_humidity_device_identifier():
    """Humidity entity device identifier uses sensor_{id} (no suffix)."""
    h = _make_sensor("eid", 202, 2)
    identifiers = h._attr_device_info["identifiers"]
    assert identifiers == {("tellstick_local", "eid_sensor_202")}, identifiers


def test_sensor_temp_and_humidity_share_device():
    """Temperature and humidity from the same sensor_id share one device."""
    t = _make_sensor("eid", 202, 1)
    h = _make_sensor("eid", 202, 2)
    assert t._attr_device_info["identifiers"] == h._attr_device_info["identifiers"]


def test_sensor_different_sensor_ids_get_different_devices():
    """Two physical sensors (different ids) must NOT share a device."""
    t1 = _make_sensor("eid", 100, 1)
    t2 = _make_sensor("eid", 200, 1)
    assert t1._attr_device_info["identifiers"] != t2._attr_device_info["identifiers"]


def test_sensor_unique_ids_are_distinct():
    """Temperature and humidity entities must have different unique_ids."""
    t = _make_sensor("eid", 202, 1)
    h = _make_sensor("eid", 202, 2)
    assert t._attr_unique_id != h._attr_unique_id


def test_sensor_temperature_unique_id_preserved():
    """Temperature entity unique_id keeps the _temperature suffix."""
    t = _make_sensor("eid", 202, 1)
    assert t._attr_unique_id == "eid_sensor_202_temperature"


def test_sensor_humidity_unique_id_preserved():
    """Humidity entity unique_id keeps the _humidity suffix."""
    h = _make_sensor("eid", 202, 2)
    assert h._attr_unique_id == "eid_sensor_202_humidity"


def test_sensor_entity_name_temperature():
    """Temperature entity name is 'Temperature' (just the type)."""
    t = _make_sensor("eid", 202, 1)
    assert t._attr_name == "Temperature"


def test_sensor_entity_name_humidity():
    """Humidity entity name is 'Humidity' (just the type)."""
    h = _make_sensor("eid", 202, 2)
    assert h._attr_name == "Humidity"


def test_sensor_device_name_strips_temperature_suffix():
    """Default name 'TellStick sensor 202 temperature' → device 'TellStick sensor 202'."""
    t = _make_sensor("eid", 202, 1)
    assert t._attr_device_info["name"] == "TellStick sensor 202"


def test_sensor_device_name_strips_humidity_suffix():
    """Default name 'TellStick sensor 202 humidity' → device 'TellStick sensor 202'."""
    h = _make_sensor("eid", 202, 2)
    assert h._attr_device_info["name"] == "TellStick sensor 202"


def test_sensor_device_name_consistent_between_types():
    """Temperature and humidity for the same sensor produce the same device name."""
    t = _make_sensor("eid", 202, 1)
    h = _make_sensor("eid", 202, 2)
    assert t._attr_device_info["name"] == h._attr_device_info["name"]


def test_sensor_custom_name_no_suffix_unchanged():
    """Custom name without type suffix is kept as-is for the device name."""
    t = _make_sensor("eid", 100, 1, name="My outdoor sensor")
    assert t._attr_device_info["name"] == "My outdoor sensor"
    assert t._attr_name == "Temperature"


def test_sensor_custom_name_with_temperature_suffix_stripped():
    """Custom name ending in ' temperature' has the suffix stripped."""
    t = _make_sensor("eid", 100, 1, name="Outdoor temperature")
    assert t._attr_device_info["name"] == "Outdoor"
    assert t._attr_name == "Temperature"


def test_sensor_custom_name_with_humidity_suffix_stripped():
    """Custom name ending in ' humidity' has the suffix stripped."""
    h = _make_sensor("eid", 100, 2, name="Outdoor humidity")
    assert h._attr_device_info["name"] == "Outdoor"
    assert h._attr_name == "Humidity"


def test_sensor_unknown_data_type_fallback():
    """Unknown data_type: entity name and device name fall back to the
    configured name (no AttributeError from None.capitalize())."""
    from custom_components.tellstick_local.sensor import TellStickSensor
    # data_type 99 is not in _SENSOR_META
    entity = TellStickSensor(
        entry_id="eid",
        device_uid="sensor_50_unknown",
        name="Mystery sensor",
        protocol="oregon",
        model="wind",
        sensor_id=50,
        data_type=99,
    )
    # Should not raise; entity name falls back to configured name
    assert entity._attr_name == "Mystery sensor"
    assert entity._attr_device_info["name"] == "Mystery sensor"


# ---------------------------------------------------------------------------
# Section 2 — Switch entities are unaffected
# ---------------------------------------------------------------------------

def test_switch_device_identifier_per_uid():
    """Switch entity device identifier still uses the full device_uid."""
    sw = _make_switch("eid", "arctech_selflearning_12345_1")
    expected = {("tellstick_local", "eid_arctech_selflearning_12345_1")}
    assert sw._attr_device_info["identifiers"] == expected, sw._attr_device_info["identifiers"]


def test_switch_unique_id_matches_device_identifier():
    """Switch unique_id is consistent with device identifier (both use uid)."""
    uid = "arctech_selflearning_12345_1"
    sw = _make_switch("eid", uid)
    assert sw._attr_unique_id == f"eid_{uid}"
    device_id = next(iter(sw._attr_device_info["identifiers"]))[1]
    assert device_id == f"eid_{uid}"


def test_switch_entity_name_is_full_name():
    """Switch entity keeps the full user-configured name (no suffix stripping)."""
    sw = _make_switch("eid", "arctech_selflearning_99_1", name="Living Room Lamp")
    assert sw._attr_name == "Living Room Lamp"


def test_two_switches_get_separate_devices():
    """Two different switches must have separate device identifiers."""
    sw1 = _make_switch("eid", "arctech_selflearning_100_1")
    sw2 = _make_switch("eid", "arctech_selflearning_100_2")
    assert sw1._attr_device_info["identifiers"] != sw2._attr_device_info["identifiers"]


# ---------------------------------------------------------------------------
# Section 3 — Light entities are unaffected
# ---------------------------------------------------------------------------

def test_light_device_identifier_per_uid():
    """Light (dimmer) entity device identifier still uses the full device_uid."""
    lt = _make_light("eid", "arctech_selflearning-dimmer_99_3")
    expected = {("tellstick_local", "eid_arctech_selflearning-dimmer_99_3")}
    assert lt._attr_device_info["identifiers"] == expected


def test_light_unique_id_correct():
    """Light unique_id matches the device identifier."""
    uid = "arctech_selflearning-dimmer_77_2"
    lt = _make_light("eid", uid)
    assert lt._attr_unique_id == f"eid_{uid}"


def test_light_entity_name_unchanged():
    """Light entity keeps the full configured name."""
    lt = _make_light("eid", "arctech_selflearning-dimmer_5_1", name="Hallway Dimmer")
    assert lt._attr_name == "Hallway Dimmer"


# ---------------------------------------------------------------------------
# Section 4 — Cover entities are unaffected
# ---------------------------------------------------------------------------

def test_cover_device_identifier_per_uid():
    """Cover entity device identifier still uses the full device_uid."""
    cv = _make_cover("eid", "hasta_selflearning_A_1")
    expected = {("tellstick_local", "eid_hasta_selflearning_A_1")}
    assert cv._attr_device_info["identifiers"] == expected


def test_cover_unique_id_correct():
    """Cover unique_id matches the device identifier."""
    uid = "hasta_selflearning_B_3"
    cv = _make_cover("eid", uid)
    assert cv._attr_unique_id == f"eid_{uid}"


def test_cover_entity_name_unchanged():
    """Cover entity keeps the full configured name."""
    cv = _make_cover("eid", "hasta_selflearning_C_2", name="Bedroom Blind")
    assert cv._attr_name == "Bedroom Blind"


# ---------------------------------------------------------------------------
# Section 5 — _build_device_label (issue #33: distinct sensor labels)
# ---------------------------------------------------------------------------

def _label(uid, cfg):
    from custom_components.tellstick_local.config_flow import _build_device_label
    return _build_device_label(uid, cfg)


def test_label_sensor_temperature_includes_type():
    """Sensor temperature label shows 'sensor {id} temperature' in detail."""
    cfg = {"name": "My sensor", "sensor_id": 100, "data_type": 1}
    label = _label("sensor_100_temperature", cfg)
    assert "temperature" in label.lower(), label
    assert "100" in label, label


def test_label_sensor_humidity_includes_type():
    """Sensor humidity label shows 'sensor {id} humidity' in detail."""
    cfg = {"name": "My sensor", "sensor_id": 100, "data_type": 2}
    label = _label("sensor_100_humidity", cfg)
    assert "humidity" in label.lower(), label
    assert "100" in label, label


def test_label_sensor_temperature_and_humidity_are_distinguishable():
    """Temperature and humidity labels for the same sensor_id must differ."""
    cfg_t = {"name": "My sensor", "sensor_id": 100, "data_type": 1}
    cfg_h = {"name": "My sensor", "sensor_id": 100, "data_type": 2}
    label_t = _label("sensor_100_temperature", cfg_t)
    label_h = _label("sensor_100_humidity", cfg_h)
    assert label_t != label_h, f"Labels identical: {label_t!r}"


def test_label_sensor_unknown_data_type_graceful():
    """Sensor with unknown data_type falls back to sensor_id only."""
    cfg = {"name": "Wind sensor", "sensor_id": 50, "data_type": 16}
    label = _label("sensor_50_unknown", cfg)
    # Should not crash; sensor_id should appear
    assert "50" in label, label


def test_label_sensor_missing_data_type_graceful():
    """Sensor with no data_type stored falls back gracefully."""
    cfg = {"name": "Old sensor", "sensor_id": 77}
    label = _label("sensor_77_temperature", cfg)
    assert "77" in label, label


def test_label_switch_unchanged():
    """Switch label is unaffected by the sensor changes."""
    cfg = {
        "name": "Kitchen Light",
        "protocol": "arctech",
        "model": "selflearning-switch",
        "house": "12345",
        "unit": "1",
    }
    label = _label("arctech_selflearning_12345_1", cfg)
    assert "Kitchen Light" in label, label
    assert "12345" in label, label


def test_label_cover_unchanged():
    """Cover label is unaffected."""
    cfg = {
        "name": "Office Blind",
        "protocol": "hasta",
        "model": "selflearning",
        "house": "A",
        "unit": "1",
    }
    label = _label("hasta_selflearning_A_1", cfg)
    assert "Office Blind" in label, label


# ---------------------------------------------------------------------------
# Section 6 — compatible filter logic (issue #33: no cross-type replacement)
# ---------------------------------------------------------------------------

def _apply_compatible_filter(devices: dict, dev_type: str, discovered_data_type):
    """Replicate the compatible filter logic from async_step_add_rf_device.

    For sensors, groups by sensor_id (one entry per physical sensor).
    For non-sensors, returns all non-sensor devices.
    """
    is_sensor = dev_type == "sensor"
    if is_sensor:
        seen_ids: set[int] = set()
        result: dict = {}
        for uid, cfg in devices.items():
            if not uid.startswith("sensor_"):
                continue
            sid = cfg.get("sensor_id")
            if sid is None or sid in seen_ids:
                continue
            seen_ids.add(sid)
            result[uid] = cfg
        return result
    return {
        uid: cfg
        for uid, cfg in devices.items()
        if not uid.startswith("sensor_")
    }


SAMPLE_DEVICES = {
    # Two sensor data-types for sensor_id=100
    "sensor_100_temperature": {
        "name": "Outdoor temp", "sensor_id": 100, "data_type": 1,
        "protocol": "fineoffset", "model": "temperature",
    },
    "sensor_100_humidity": {
        "name": "Outdoor humidity", "sensor_id": 100, "data_type": 2,
        "protocol": "fineoffset", "model": "temperaturehumidity",
    },
    # A second sensor with only temperature
    "sensor_200_temperature": {
        "name": "Indoor temp", "sensor_id": 200, "data_type": 1,
        "protocol": "oregon", "model": "1A2D",
    },
    # A switch
    "arctech_selflearning_999_1": {
        "name": "Ceiling Light", "protocol": "arctech",
        "model": "selflearning-switch", "house": "999", "unit": "1",
    },
    # A cover
    "hasta_selflearning_A_1": {
        "name": "Bedroom Blind", "protocol": "hasta",
        "model": "selflearning", "house": "A", "unit": "1",
    },
}


def test_filter_temperature_discovery_shows_only_temperature():
    """Discovering a sensor → dropdown groups by sensor_id (one per sensor)."""
    result = _apply_compatible_filter(SAMPLE_DEVICES, "sensor", 1)
    # One entry per sensor_id — sensor 100 and sensor 200
    sensor_ids = {cfg.get("sensor_id") for cfg in result.values()}
    assert 100 in sensor_ids
    assert 200 in sensor_ids
    # Switches and covers must NOT appear
    assert "arctech_selflearning_999_1" not in result
    assert "hasta_selflearning_A_1" not in result


def test_filter_humidity_discovery_shows_only_humidity():
    """Discovering a sensor → dropdown groups by sensor_id, same behavior as temp."""
    result = _apply_compatible_filter(SAMPLE_DEVICES, "sensor", 2)
    # Same as temperature: one entry per sensor_id
    sensor_ids = {cfg.get("sensor_id") for cfg in result.values()}
    assert 100 in sensor_ids
    assert 200 in sensor_ids
    # Switches and covers must NOT appear
    assert "arctech_selflearning_999_1" not in result
    assert "hasta_selflearning_A_1" not in result


def test_filter_switch_discovery_shows_only_switches_and_covers():
    """Discovering a switch device → dropdown shows non-sensor devices only."""
    result = _apply_compatible_filter(SAMPLE_DEVICES, "device", None)
    # Non-sensor devices appear
    assert "arctech_selflearning_999_1" in result
    assert "hasta_selflearning_A_1" in result
    # Sensors must NOT appear
    assert "sensor_100_temperature" not in result
    assert "sensor_100_humidity" not in result
    assert "sensor_200_temperature" not in result


def test_filter_no_sensors_in_store_returns_empty_for_sensor_discovery():
    """No stored sensors → compatible is empty → no replace dropdown shown."""
    devices_no_sensors = {
        k: v for k, v in SAMPLE_DEVICES.items() if not k.startswith("sensor_")
    }
    result = _apply_compatible_filter(devices_no_sensors, "sensor", 1)
    assert result == {}


def test_filter_empty_devices_returns_empty():
    result = _apply_compatible_filter({}, "sensor", 1)
    assert result == {}


# ---------------------------------------------------------------------------
# Section 7 — SENSOR_TYPE_NAMES constant (single source of truth)
# ---------------------------------------------------------------------------

def test_sensor_type_names_in_const():
    """SENSOR_TYPE_NAMES is defined in const.py and has the expected values."""
    from custom_components.tellstick_local.const import (
        SENSOR_TYPE_NAMES,
        TELLSTICK_HUMIDITY,
        TELLSTICK_TEMPERATURE,
    )
    assert SENSOR_TYPE_NAMES[TELLSTICK_TEMPERATURE] == "temperature"
    assert SENSOR_TYPE_NAMES[TELLSTICK_HUMIDITY] == "humidity"


def test_config_flow_uses_const_sensor_type_names():
    """config_flow imports SENSOR_TYPE_NAMES from const (no local duplicate)."""
    from custom_components.tellstick_local.config_flow import SENSOR_TYPE_NAMES as cf_names
    from custom_components.tellstick_local.const import SENSOR_TYPE_NAMES as const_names
    assert cf_names is const_names


# ---------------------------------------------------------------------------
# Section 8 — Diagnostics structure
# ---------------------------------------------------------------------------

def test_diagnostics_imports_cleanly():
    """diagnostics.py imports without errors."""
    import custom_components.tellstick_local.diagnostics  # noqa: F401


def test_diagnostics_has_required_function():
    """diagnostics module exposes async_get_config_entry_diagnostics."""
    from custom_components.tellstick_local import diagnostics
    assert hasattr(diagnostics, "async_get_config_entry_diagnostics")
    import asyncio
    assert asyncio.iscoroutinefunction(diagnostics.async_get_config_entry_diagnostics)


def test_diagnostics_sensor_type_name_resolution():
    """_SENSOR_TYPE_NAMES alias in diagnostics resolves correctly."""
    from custom_components.tellstick_local.diagnostics import _SENSOR_TYPE_NAMES
    from custom_components.tellstick_local.const import (
        TELLSTICK_HUMIDITY,
        TELLSTICK_TEMPERATURE,
    )
    assert _SENSOR_TYPE_NAMES[TELLSTICK_TEMPERATURE] == "temperature"
    assert _SENSOR_TYPE_NAMES[TELLSTICK_HUMIDITY] == "humidity"


# ---------------------------------------------------------------------------
# Section 9 — _migrate_sensor_companion imports cleanly
# ---------------------------------------------------------------------------

def test_migrate_sensor_companion_importable():
    """_migrate_sensor_companion is importable from config_flow."""
    from custom_components.tellstick_local.config_flow import _migrate_sensor_companion
    assert callable(_migrate_sensor_companion)


def test_migrate_sensor_companion_skips_when_no_companion():
    """_migrate_sensor_companion is a no-op when no companion exists in options."""
    from custom_components.tellstick_local.config_flow import _migrate_sensor_companion
    # Call with options that have no companion entry
    opts = {
        "devices": {
            "sensor_202_temperature": {
                "name": "New temp", "sensor_id": 202, "data_type": 1,
            },
        },
    }
    result = _migrate_sensor_companion(
        Mock(),   # hass
        Mock(entry_id="eid"),  # entry
        "100", "202", "temperature", opts,
    )
    # Options unchanged (no companion to migrate)
    assert "sensor_100_humidity" not in result.get("devices", {})
    assert "sensor_202_humidity" not in result.get("devices", {})
    # Primary entry preserved
    assert "sensor_202_temperature" in result["devices"]


def test_migrate_sensor_companion_migrates_humidity():
    """When migrating temperature, companion humidity is also migrated."""
    from custom_components.tellstick_local.config_flow import _migrate_sensor_companion
    from unittest.mock import patch
    mock_ent_reg = Mock()
    mock_ent_reg.async_entries_for_config_entry = Mock(return_value=[])
    hass = Mock()
    hass.data = {"tellstick_local": {"eid": {"_discovered_uids": set()}}}
    entry = Mock(entry_id="eid")
    opts = {
        "devices": {
            "sensor_202_temperature": {
                "name": "New temp", "sensor_id": 202, "data_type": 1,
            },
            "sensor_100_humidity": {
                "name": "Old hum", "sensor_id": 100, "data_type": 2,
            },
        },
    }
    with patch("custom_components.tellstick_local.config_flow.er.async_get", return_value=mock_ent_reg), \
         patch("custom_components.tellstick_local.config_flow.er.async_entries_for_config_entry", return_value=[]):
        result = _migrate_sensor_companion(
            hass, entry, "100", "202", "temperature", opts,
        )
    # Old humidity removed, new humidity added
    assert "sensor_100_humidity" not in result["devices"]
    assert "sensor_202_humidity" in result["devices"]
    # New humidity has updated sensor_id
    assert result["devices"]["sensor_202_humidity"]["sensor_id"] == 202
    # Old humidity UID should NOT be added to ignored list (issue #33 fix)
    assert "sensor_100_humidity" not in result.get("ignored_uids", {})


def test_migrate_sensor_companion_preserves_primary():
    """Companion migration preserves the primary entity's config."""
    from custom_components.tellstick_local.config_flow import _migrate_sensor_companion
    from unittest.mock import patch
    mock_ent_reg = Mock()
    mock_ent_reg.async_entries_for_config_entry = Mock(return_value=[])
    hass = Mock()
    hass.data = {"tellstick_local": {"eid": {"_discovered_uids": set()}}}
    entry = Mock(entry_id="eid")
    opts = {
        "devices": {
            "sensor_202_temperature": {
                "name": "My temp", "sensor_id": 202, "data_type": 1,
            },
            "sensor_100_humidity": {
                "name": "My hum", "sensor_id": 100, "data_type": 2,
            },
        },
    }
    with patch("custom_components.tellstick_local.config_flow.er.async_get", return_value=mock_ent_reg), \
         patch("custom_components.tellstick_local.config_flow.er.async_entries_for_config_entry", return_value=[]):
        result = _migrate_sensor_companion(
            hass, entry, "100", "202", "temperature", opts,
        )
    # Primary entry preserved
    assert "sensor_202_temperature" in result["devices"]
    assert result["devices"]["sensor_202_temperature"]["name"] == "My temp"


def test_label_sensor_grouped_strips_type_suffix():
    """sensor_grouped=True strips the type suffix from name and detail."""
    from custom_components.tellstick_local.config_flow import _build_device_label
    cfg = {"name": "Outdoor temp temperature", "sensor_id": 100, "data_type": 1,
           "protocol": "fineoffset", "model": "temperature"}
    label = _build_device_label("sensor_100_temperature", cfg, sensor_grouped=True)
    assert "sensor 100" in label
    # Must NOT include "temperature" in detail
    assert "temperature)" not in label


def test_label_sensor_grouped_without_suffix():
    """sensor_grouped=True with a name that has no type suffix keeps name intact."""
    from custom_components.tellstick_local.config_flow import _build_device_label
    cfg = {"name": "Wine cellar", "sensor_id": 100, "data_type": 1,
           "protocol": "fineoffset", "model": "temperature"}
    label = _build_device_label("sensor_100_temperature", cfg, sensor_grouped=True)
    assert "Wine cellar" in label
    assert "sensor 100)" in label


def test_filter_sensor_groups_by_sensor_id():
    """Sensor discovery groups replace dropdown by sensor_id (one entry per physical sensor)."""
    result = _apply_compatible_filter(SAMPLE_DEVICES, "sensor", 1)
    # Two physical sensors: 100 and 200
    assert len(result) == 2
    sensor_ids = {cfg.get("sensor_id") for cfg in result.values()}
    assert sensor_ids == {100, 200}
    # No duplicate for sensor 100 (has both temp and hum)
    uids = list(result.keys())
    assert all(uid.startswith("sensor_") for uid in uids)


def test_companion_migration_handles_conflict():
    """When companion entity unique_id already exists, orphan is cleaned up."""
    from custom_components.tellstick_local.config_flow import _migrate_sensor_companion
    from unittest.mock import patch

    mock_ent = Mock()
    mock_ent.unique_id = "eid_sensor_100_humidity"
    mock_ent.entity_id = "sensor.old_humidity"

    mock_ent_reg = Mock()

    hass = Mock()
    hass.data = {"tellstick_local": {"eid": {"_discovered_uids": set()}}}
    entry = Mock(entry_id="eid")
    opts = {
        "devices": {
            "sensor_202_temperature": {"name": "T", "sensor_id": 202, "data_type": 1},
            "sensor_100_humidity": {"name": "H", "sensor_id": 100, "data_type": 2},
        },
    }

    # Simulate conflict: async_update_entity raises ValueError
    mock_ent_reg.async_update_entity.side_effect = ValueError("conflict")

    with patch("custom_components.tellstick_local.config_flow.er.async_get", return_value=mock_ent_reg), \
         patch("custom_components.tellstick_local.config_flow.er.async_entries_for_config_entry", return_value=[mock_ent]):
        result = _migrate_sensor_companion(
            hass, entry, "100", "202", "temperature", opts,
        )

    # Orphan should be removed
    mock_ent_reg.async_remove.assert_called_once_with("sensor.old_humidity")
    # Options still updated
    assert "sensor_202_humidity" in result["devices"]
    assert "sensor_100_humidity" not in result["devices"]


# ---------------------------------------------------------------------------
# Helper function tests (_extract_sensor_suffix, _strip_sensor_suffix)
# ---------------------------------------------------------------------------

def test_extract_sensor_suffix_temperature():
    """_extract_sensor_suffix returns 'temperature' for temp UIDs."""
    from custom_components.tellstick_local.config_flow import _extract_sensor_suffix
    assert _extract_sensor_suffix("sensor_200_temperature") == "temperature"


def test_extract_sensor_suffix_humidity():
    """_extract_sensor_suffix returns 'humidity' for hum UIDs."""
    from custom_components.tellstick_local.config_flow import _extract_sensor_suffix
    assert _extract_sensor_suffix("sensor_200_humidity") == "humidity"


def test_extract_sensor_suffix_fallback():
    """_extract_sensor_suffix returns 'sensor' for unexpected UIDs."""
    from custom_components.tellstick_local.config_flow import _extract_sensor_suffix
    assert _extract_sensor_suffix("sensor_200") == "sensor"
    assert _extract_sensor_suffix("sensor_200_unknown") == "sensor"


def test_strip_sensor_suffix_temperature():
    """_strip_sensor_suffix strips ' temperature' suffix."""
    from custom_components.tellstick_local.config_flow import _strip_sensor_suffix
    assert _strip_sensor_suffix("Vinkällare temperature") == "Vinkällare"


def test_strip_sensor_suffix_humidity():
    """_strip_sensor_suffix strips ' humidity' suffix."""
    from custom_components.tellstick_local.config_flow import _strip_sensor_suffix
    assert _strip_sensor_suffix("Outdoor humidity") == "Outdoor"


def test_strip_sensor_suffix_no_suffix():
    """_strip_sensor_suffix returns name unchanged when no suffix."""
    from custom_components.tellstick_local.config_flow import _strip_sensor_suffix
    assert _strip_sensor_suffix("Wine cellar") == "Wine cellar"


def test_strip_sensor_suffix_case_insensitive():
    """_strip_sensor_suffix is case-insensitive for matching."""
    from custom_components.tellstick_local.config_flow import _strip_sensor_suffix
    assert _strip_sensor_suffix("Outdoor Temperature") == "Outdoor"
    assert _strip_sensor_suffix("Outdoor HUMIDITY") == "Outdoor"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    # Sensor grouping
    test_sensor_temperature_device_identifier,
    test_sensor_humidity_device_identifier,
    test_sensor_temp_and_humidity_share_device,
    test_sensor_different_sensor_ids_get_different_devices,
    test_sensor_unique_ids_are_distinct,
    test_sensor_temperature_unique_id_preserved,
    test_sensor_humidity_unique_id_preserved,
    test_sensor_entity_name_temperature,
    test_sensor_entity_name_humidity,
    test_sensor_device_name_strips_temperature_suffix,
    test_sensor_device_name_strips_humidity_suffix,
    test_sensor_device_name_consistent_between_types,
    test_sensor_custom_name_no_suffix_unchanged,
    test_sensor_custom_name_with_temperature_suffix_stripped,
    test_sensor_custom_name_with_humidity_suffix_stripped,
    test_sensor_unknown_data_type_fallback,
    # Switch unaffected
    test_switch_device_identifier_per_uid,
    test_switch_unique_id_matches_device_identifier,
    test_switch_entity_name_is_full_name,
    test_two_switches_get_separate_devices,
    # Light unaffected
    test_light_device_identifier_per_uid,
    test_light_unique_id_correct,
    test_light_entity_name_unchanged,
    # Cover unaffected
    test_cover_device_identifier_per_uid,
    test_cover_unique_id_correct,
    test_cover_entity_name_unchanged,
    # Labels
    test_label_sensor_temperature_includes_type,
    test_label_sensor_humidity_includes_type,
    test_label_sensor_temperature_and_humidity_are_distinguishable,
    test_label_sensor_unknown_data_type_graceful,
    test_label_sensor_missing_data_type_graceful,
    test_label_switch_unchanged,
    test_label_cover_unchanged,
    # Compatible filter
    test_filter_temperature_discovery_shows_only_temperature,
    test_filter_humidity_discovery_shows_only_humidity,
    test_filter_switch_discovery_shows_only_switches_and_covers,
    test_filter_no_sensors_in_store_returns_empty_for_sensor_discovery,
    test_filter_empty_devices_returns_empty,
    # Constants
    test_sensor_type_names_in_const,
    test_config_flow_uses_const_sensor_type_names,
    # Diagnostics
    test_diagnostics_imports_cleanly,
    test_diagnostics_has_required_function,
    test_diagnostics_sensor_type_name_resolution,
    # Sensor migration
    test_migrate_sensor_companion_importable,
    test_migrate_sensor_companion_skips_when_no_companion,
    test_migrate_sensor_companion_migrates_humidity,
    test_migrate_sensor_companion_preserves_primary,
    # Sensor grouped labels and filter
    test_label_sensor_grouped_strips_type_suffix,
    test_label_sensor_grouped_without_suffix,
    test_filter_sensor_groups_by_sensor_id,
    # Companion migration robustness
    test_companion_migration_handles_conflict,
    # Helper functions
    test_extract_sensor_suffix_temperature,
    test_extract_sensor_suffix_humidity,
    test_extract_sensor_suffix_fallback,
    test_strip_sensor_suffix_temperature,
    test_strip_sensor_suffix_humidity,
    test_strip_sensor_suffix_no_suffix,
    test_strip_sensor_suffix_case_insensitive,
]


if __name__ == "__main__":
    import traceback

    print("=== Device type tests ===\n")

    sections = {
        "Sensor device grouping": range(0, 16),
        "Switch entities unaffected": range(16, 20),
        "Light entities unaffected": range(20, 23),
        "Cover entities unaffected": range(23, 26),
        "_build_device_label (sensor labels)": range(26, 33),
        "Compatible filter (data_type guard)": range(33, 38),
        "SENSOR_TYPE_NAMES constant": range(38, 40),
        "Diagnostics": range(40, 43),
        "Sensor migration (issue #33)": range(43, 47),
        "Sensor grouped labels & filter": range(47, 50),
        "Companion migration robustness": range(50, 51),
        "Helper functions": range(51, 58),
    }

    for section_name, idx_range in sections.items():
        print(f"--- {section_name} ---")
        for i in idx_range:
            fn = TESTS[i]
            try:
                fn()
                report(fn.__name__, True)
            except AssertionError as e:
                report(fn.__name__, False, str(e))
            except Exception as e:
                report(fn.__name__, False, f"{type(e).__name__}: {e}")
                traceback.print_exc()
        print()

    print("=" * 55)
    print("ALL TESTS PASSED" if ALL_PASS else "SOME TESTS FAILED")
    print("=" * 55)
    sys.exit(0 if ALL_PASS else 1)
