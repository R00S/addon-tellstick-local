# Branch: add-rtl-433-support — 3.1.12.x Timeline

## Objective
Add RTL-433 MQTT sensor auto-discovery and Generic RF record & replay (TX) to the TellStick Local integration. Both features are opt-in and require the rtl_433 add-on + MQTT integration.

## Status: IN PROGRESS

## Implementation Plan

### Feature 1: RTL-433 Sensor Auto-discovery
- [ ] `const.py` — Add `CONF_RTL433_SENSORS`, `RTL433_SENSOR_FIELDS`, `SIGNAL_RTL433_READING`
- [ ] `__init__.py` — Subscribe to `rtl_433/#` via HA MQTT, dispatch signals, lifecycle management
- [ ] `sensor.py` — Add `Rtl433Sensor` class for MQTT-sourced sensor entities
- [ ] `config_flow.py` — Add "Listen for rtl_433 sensors via MQTT" toggle in settings
- [ ] `strings.json` / `translations/en.json` — New UI strings

### Feature 2: Generic RF Record & Replay
- [ ] `const.py` — Add `PROTOCOL_GENERIC_RF`, `generic_rf_build_raw_command()`, `timings_to_tellstick_bytes()`
- [ ] `config_flow.py` — Add `generic_rf` menu option + listen/confirm steps in subentry flow
- [ ] `switch.py` — Handle `protocol == "generic_rf"` with `_send_generic_rf_raw()`
- [ ] `__init__.py` — Skip telldusd registration for generic_rf devices
- [ ] `strings.json` / `translations/en.json` — New UI strings

### Sync & Version
- [ ] Bump `manifest.json` to 3.1.12.16 in both locations
- [ ] Sync all changed files to `tellsticklive/rootfs/usr/share/tellstick_local/`

## Session Log

### 2026-05-06 — Initial implementation
- Created branch timeline file
- Analyzing existing code structure
