# Branch timeline: add-rtl-433-support (3.2.0.x)

## 2026-05-10

- Started investigation of RTL_433 addon slug discovery still failing in Record ON signal flow.
- Confirmed user-visible debug output: `RTL_433 addon not found - check Home Assistant logs`.
- Next: inspect Supervisor API call path in `custom_components/tellstick_local/config_flow.py` and implement robust fallback discovery.
