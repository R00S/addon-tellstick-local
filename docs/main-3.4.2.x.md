# main — 3.4.2.x timeline

## 3.4.2.1 — the transmitter entity was registered disabled

**Branch:** `main` · **Date:** 2026-11-27 · **Type:** bug fix

Found by testing 3.4.2.0 on a real instance: the platform ran, the config
entry had `backend=duo`, the controller answered `supports_raw_pulses() ==
True`, and still no entity existed — and the log was empty.

### Cause

The entity *was* created, but the registry entry came out with
`disabled_by: integration`. Home Assistant does that when the config entry has
`pref_disable_new_entities` set: `async_get_or_create()` overrides its
`disabled_by=UNDEFINED` with `RegistryEntryDisabler.INTEGRATION`. A disabled
entity is never added to the component, so it is invisible in the UI **and**
invisible to `async_get_transmitters()` — the feature could never have worked
on such an entry.

### Fix

`radio_frequency.async_setup_entry()` now claims the registry entry itself
before adding the entity, with `disabled_by=None`, which bypasses the
preference. An entry already disabled by 3.4.2.0 is switched back on and the
config entry reloads once, which picks the entity up in the same start.

### Verified live

On the instance: enabling the entity by hand and reloading the entry produced
`radio_frequency.tellstick_duo_<host>_rf_transmitter` with
`device_class=transmitter` and state `unknown` — the platform, the `duo`
backend and the entity all work. What is still unproven is a transmission:
that needs a consumer integration and something that listens.

### Version

3.4.2.0 → **3.4.2.1**.

## 3.4.2.0 — TellStick as a `radio_frequency` transmitter

**Branch:** `main` · **Date:** 2026-11-27 · **Type:** new feature

### What was added

Home Assistant 2026.5 introduced the `radio_frequency` building block: an
integration owns RF hardware and exposes it as a transmitter entity, and device
integrations send through it. A TellStick Duo or an original TellStick Net (v1)
now registers such an entity, so any consumer integration (Novy Cooker Hood,
Honeywell String Lights, third-party ones, and anything added later) can send
through our hardware. **No protocol code was added to this project** — the
consumer supplies `get_raw_timings()`, we only translate.

### Files

- `custom_components/tellstick_local/radio_frequency.py` (new) — platform and
  `TellStickRadioFrequency` entity. Skips mirror entries and any backend whose
  `supports_raw_pulses()` is false.
- `const.py` — `PLATFORMS` gains `radio_frequency`; `NET_V1_MAX_PULSES = 199`;
  new `timings_to_raw_frame()` + `_timing_ticks()`.
- `net_client.py` — `supports_raw_pulses()` (true only for product
  `TellStickNet`); `_NET_V1_MAX_PULSES` now aliases the const value.
- `client.py` — `supports_raw_pulses()` returns `True` for a Duo.
- `manifest.json` (both copies) — `3.4.2.0`, `homeassistant: 2026.5.0`,
  `dependencies: ["radio_frequency"]`.
- `strings.json` / `translations/en.json` — `rf_transmitter` entity name plus
  `no_timings`, `frame_too_long`, `transmit_failed` exceptions.
- `tests/test_radio_frequency.py` (new) — conversion, splitting, repeat
  clamping, Net v1 trimming and refusal, empty timings.
- `docs/USER_GUIDE.md` §18, `README.md`, `tellsticklive/CHANGELOG.md`.

### Decisions

- **Min HA raised to 2026.5.0** (user decision), and the platform still guards
  its import: Home Assistant does not enforce the `homeassistant` key for
  custom integrations, so without the guard an older Core would fail to set up
  the *whole* integration. With it, only this optional feature is skipped.
- **Long timings are split, not clamped.** A timing byte saturates at 2550 µs,
  so anything longer becomes chunks separated by a one-tick (10 µs) seam — the
  construct already proven for the ~4.9 ms start mark of a replayed blind
  remote (`2550 + 10 + 2340`).
- **Simplest mirror handling** (user decision): the provider awaits
  `async_mirror_raw_command()` with the existing `_RF_MIRROR_DELAY_S = 0.7`.
  No task, no burst model, no change to `entity.py`.
- **Mirror entries and ZNet never get an entity.** A mirror is infrastructure
  and a ZNet cannot replay raw frames, so neither may appear in a consumer's
  transmitter dropdown.
- **`timings_to_tellstick_bytes()` and `generic_rf_build_raw_command()` are
  untouched**, so Luxorparts, Generic RF replay and the Tuya curtain motor
  transmit byte-for-byte as before.

### Not verified

- No Home Assistant instance or TellStick hardware in the build sandbox, so
  `tests/test_ha_integration.py` could not run here and no RF transmission was
  observed. The splitting seam and the 10 µs quantisation still need hardware
  confirmation with one consumer integration (Novy or Honeywell) and one
  split-heavy protocol before this is called proven.

### Live check on a real instance (read-only)

A live HAOS instance was inspected over the REST API before this version was
installed: Core **2026.11.3**, `radio_frequency` present among loaded
components, `tellstick_local` loaded, 26 TellStick entities including
`selflearning-switch:lx_live` devices and three covers — i.e. raw-pulse capable
hardware (Duo and/or Net v1), the case this feature exists for. As expected,
`radio_frequency` entities were still **0**, because 3.4.1.5 does not contain the
platform. `/api/error_log` answers 404 on 2026.11 for a user token, so logs must
be read in the UI.

### Not covered by tests

The consumer side (Novy / Honeywell / third-party) is not installed on the test
instance, so the entity's presence in a transmitter dropdown is unverified, and
no RF transmission has been observed.

### Version

3.4.1.5 → **3.4.2.0** in both manifests and in `tellsticklive/config.yaml`.
