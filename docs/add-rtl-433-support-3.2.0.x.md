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
- Investigated follow-up bug reported against `3.2.0.17`: only the first Generic RF
  signal (ON/UP) was captured; later OFF/DOWN/STOP/DIM steps consistently showed
  `No signal captured`.
- Verified current branch already contained:
  - log fallback in OFF/DOWN/STOP/DIM/UP steps
  - missing Generic RF strings fix
  - mirrored runtime copy under `tellsticklive/rootfs/usr/share/tellstick_local/`
- New likely root cause: each later listen step only started a new capture session
  when `_generic_rf_listen_unsub is None`. That made step-to-step capture restart
  depend on prior unsubscribe state instead of always starting clean on entry.
- Implemented a more robust fix:
  - added `_restart_generic_rf_listen()`
  - each listen step now restarts capture on first render (`user_input is None`)
    for ON/OFF/DIM/UP/DOWN/STOP
  - submit/check path still does not clear a just-captured signal
- Mirrored the updated `config_flow.py` to the bundled runtime copy.
- Validation after restart fix:
  - `python3 -m pyflakes custom_components/tellstick_local`
  - `python3 -m py_compile custom_components/tellstick_local/*.py`
  - `python tests/test_ha_integration.py`
  - all passed after removing one unused import and one unnecessary f-string in `config_flow.py`
- Bumped integration version from `3.2.0.17` to `3.2.0.18` in both manifest files.
- Merge-prep decision: RTL-433 / Generic RF development is temporarily halted.
- GUI references to RTL-433 were removed from active config-flow entry points:
  - removed `rtl433_sensors` toggle from Settings options form
  - removed `generic_rf` from Add Device menu options
- README updated to mark RTL-433 / Generic RF as temporarily halted and remove
  GUI-driven setup instructions for those paused features.
