# main — 3.4.2.x timeline

## 3.4.2.2 — PoC service that sends raw OOK through radio_frequency

**Branch:** `main` · **Date:** 2026-11-27 · **Type:** diagnostic

Needed to test split frames against a real Luxorparts socket without
installing a consumer integration, and without putting the protocol into this
project.

### What it does

`tellstick_local.poc_rf_command` takes `timings` (signed µs), `repeat` and
`frequency`, builds an `rf_protocols.commands.ook.OOKCommand` and calls
`homeassistant.components.radio_frequency.async_send_command()` — the exact
call Novy and Honeywell make. The protocol lives in the service call, not in
the code. It returns the frame bytes our provider emitted, so they can be
diffed against a reference capture.

Guarded by `RF_CONSUMER_AVAILABLE` so an older Core only loses this action.

### Version

3.4.2.1 → **3.4.2.2**.

### Hardware result — what the radio_frequency path can and cannot do

Measured on the test instance against three real Luxorparts sockets, using a
throwaway consumer integration (`tools/luxorparts_consumer/`, not shipped) that
sends the 24 verified pairs through `radio_frequency.async_send_command()`:

- **The provider path works.** A consumer integration with no TellStick code
  in it switches real sockets on and off: consumer → `rf_protocols.OOKCommand`
  → `async_send_command()` → our transmitter → telldusd → Duo → air.
- **The Homey cipher never works.** Every generated code was tried over months
  of use and none has ever switched a socket. Only the 24 pairs recorded from
  Telldus Live (`LX_LPD_LIST`) do. The consumer carries that table.
- **Every frame is byte-identical to the proven encoder.** All 24 pairs, ON and
  OFF: `timings_to_raw_frame()` output equals
  `luxorparts_build_raw_command(code, "lx_live")`.
- **Split frames cannot be validated with a Luxorparts receiver.** The protocol
  has no duration above 2550 µs, so the only way to force a split is a longer
  inter-packet gap, and that is exactly what the receiver rejects:

  | gap | frame | wire value | socket reacts |
  |---|---|---|---|
  | 250 µs | 56 B | `…19` (2250 µs with the Duo pause) | yes |
  | 2600 µs | 58 B | `…ff 01 05` (255+5) | no |
  | 3000 µs | 58 B | `…ff 01 2d` (255+45) | no |
  | 6000 µs | 60 B | `…ff 01 ff 01 5a` | no |

  The split logic itself is correct — the bytes are what they should be — but a
  receiver that expects ~2.25 ms of silence before the next packet treats the
  longer pause as the end of the message. The same split gap is worth testing
  with a protocol that has genuinely long durations, not with this one.

### Release documentation (CHORES)

- `README.md` gained an **RF transmitter** section pointing at User Guide §18.
- `docs/USER_GUIDE.md` §18: the splitting bullet now carries the measurement —
  a receiver that expects the natural short silence stops answering at 2600 µs
  and above, so "split" is not a free win on every device.
- `tellsticklive/DOCS.md`: one sentence of the same in the transmitter section.
- `tellsticklive/CHANGELOG.md` 3.4.2.2: notes that this is the first stable
  release since 3.3.3.0, so readers know where the 3.4.0.x/3.4.1.x sections
  come from.
- Version unchanged at **3.4.2.2** — documentation only, no code changed.

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
backend and the entity all work.

Then 3.4.2.1 was installed on the same instance (dev channel, the app updated
and restarted Core itself) with the registry entry deleted first, so the
entity had to be registered from scratch while the entry still carried
`pref_disable_new_entities: true`. Result: the entity came back on its own,
`disabled_by: None`, `hidden_by: None`, `device_class: transmitter`, state
`unknown`. The fix holds for a fresh registration; the re-enable path for
entries already disabled by 3.4.2.0 is unit-tested only.

What is still unproven is a transmission: that needs a consumer integration
(Novy / Honeywell / third-party) and something that listens.

### Consumer side verified live (3.4.2.1)

Home Assistant's own Novy Cooker Hood integration was added through its config
flow, driven over the REST config-flow API:

- The `transmitter` selector was built from `async_get_transmitters(433.92 MHz,
  OOK)` and contained exactly one entry: our
  `radio_frequency.tellstick_duo_<host>_rf_transmitter`. That is the proof the
  provider is selectable, which a disabled entity never is.
- Picking it and submitting ran Novy's own `test_light` step, which sends the
  LIGHT command twice with 1.5 s in between. The flow landed on the
  `test_light` menu (not `test_failed`), so both transmissions returned without
  an error.
- Finishing created the entry: `fan.novy_cooker_hood` and
  `light.novy_cooker_hood_light`.
- `light.turn_on` and `fan.turn_on` were then called: both answered 200 and the
  transmitter's state advanced to each send's timestamp
  (`2026-11-27T01:24:04.584`, `…01:24:10.320`), i.e. every command went through
  `TellStickRadioFrequency.async_send_command` and came back 0 from telldusd.
  No `frame_too_long`, `no_timings` or `transmit_failed` anywhere in
  `system_log`.

So: a protocol that lives entirely outside this project (Novy's, from
`rf_protocols`) can be added, bound to a device, and sent through our hardware.

Still not proven: that the pulses leave the antenna. Nothing in this setup
listens on 433 MHz, so the evidence stops at "telldusd accepted and transmitted
the frame". A real Novy hood — or any receiver — is needed for that last step.

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
