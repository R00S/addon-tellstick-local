# Branch timeline: add-rtl-433-support (3.2.0.x)

## 2026-05-10

- Started investigation of RTL_433 addon slug discovery still failing in Record ON signal flow.
- Confirmed user-visible debug output: `RTL_433 addon not found - check Home Assistant logs`.
- Found root cause for repeated user error: the bundled runtime integration copy
  (`tellsticklive/rootfs/usr/share/tellstick_local/config_flow.py`) still used
  `self.hass.helpers.aiohttp_client.async_get_clientsession()` in two places.
- Implemented fix in bundled runtime copy:
  - imported `async_get_clientsession`
  - replaced both invalid `self.hass.helpers...` calls with
    `async_get_clientsession(self.hass)`
- Bumped integration version from `3.2.0.14` to `3.2.0.15` in both manifest files.
