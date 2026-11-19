# issue-130-net-v1-dim — 3.4.0.x branch timeline

> Branch: `issue-130-net-v1-dim`. This file continues
> `docs/issue-130-net-v1-dim-3.3.3.x.md` after the branch merged
> `net-v1-protocols` and joined the 3.4.0.x line.

## Session — 2026-11-19: test device reshaped, LX-T1 rejected by hardware

### What the user reported

* The dev-channel test release did not contain the requested device: it was
  five separately added devices, each with its own code picker and pairing
  step. The requirement is **one device with five on/off switches**, with no
  learning step — a Luxorparts receiver learns from the ON code it hears.
* The lowest code (LX-T1, `0xAEABEA8` / `0xAEABEB8`) was offered to a 50969 in
  learn mode and was **not** accepted.

### Changed

* `const.py`: the catalog entry is now **"Luxorparts — Test device, 5 switches
  (beta, Duo only)"**; widget 21 no longer asks for a house code 101–105
  because the dedicated step creates all five itself.
* `config_flow.py`: new `async_step_lx_test()`. `async_step_by_brand()` routes
  widget 21 there instead of the params/confirm steps. It writes the five device
  configs in one pass with `group_uid` = the name given one step earlier, so Home Assistant
  shows **one** device holding LX-T1…LX-T5, and dispatches one synthetic event
  per switch. Nothing is transmitted — there is no learn signal and no confirm
  step.
* Each of the five configs carries `no_learn_button`; `button.py` skips the
  Learn button for those devices, both when pre-creating stored devices and on
  the new-device signal.
* `strings.json` / `translations/en.json`: `lx_test` step text (explains that no
  pairing signal is sent) and the `lx_test_added` abort text.
* Docs: README, `docs/USER_GUIDE.md` §5.2 and §15,
  `docs/LUXORPARTS_PAIRS.md`, `docs/LUXORPARTS_TIMELINE.md` and
  `docs/LUXORPARTS_PROTOCOL_ANALYSIS.md` §7/§9 now describe the single-device
  form, the ON-code pairing and the LX-T1 result.

### Version

3.4.0.3 → **3.4.0.4** in both `manifest.json` files, so the reshaped test
device is distinguishable from the `3.4.0.3.20261119110747` dev build.

### Verification

* `tests/test_ha_integration.py`, `py_compile`, the `const.py` doctests, and a
  script assertion that the five test configs get five distinct UIDs sharing one
  `group_uid`.
* Mirror copies under `tellsticklive/rootfs/` are byte-identical.

### Not verified

* No Luxorparts receiver here. On the user's hardware LX-T1 was rejected;
  LX-T2…LX-T5 differ only in the button-field bits and remain untested, so
  scheme A is still unproven.
* The five-switch grouping has not been looked at in a running Home Assistant —
  only the config data it produces was checked.

## Session — 2026-11-19 (later): scheme A falsified, scheme B + control

### What the user reported

* **All five scheme-A switches were refused** by the 50969 in learn mode, so the
  remote-family clone does not work.
* Request: try scheme B, and put a **CONTROL ON/OFF** in the same test device that
  emits the code the working LPD 7 path emits.

### Changed

* `const.py`: `_lx_template_pair()` and its five codes removed. New
  `_lx_live_pair()` implements scheme B
  (`payload24 = ((seed & 0x7FFFFF) << 1) | 1`, `stored28 = payload24 << 3`).
  `LX_TEST_LIST` now holds five pairs built from the working LPD 7 seeds with
  1…5 added (`0x2450C48`…`0x2450C88` and their OFF partners), so every test code
  is one seed step from a code that works.
* `LX_CONTROL_HOUSE = 106` + `LX_CONTROL_CODES`: the recorded LPD 7 pair
  (`0x2450C38` / `0x2633638`) byte for byte, returned by
  `luxorparts_generate_codes(106, 1)`. House 106 rather than 7 keeps the control
  out of a normal LPD 7 device's UID, so adding the test device never renames or
  regroups an existing switch.
* `config_flow.py`: `async_step_lx_test()` creates six switches in one grouped
  device — LX-B1…LX-B5 and **CONTROL ON/OFF (LPD 7)** — still with no pairing
  signal and no Learn button.
* `strings.json` / `translations/en.json`: `lx_test` description rewritten for the
  six switches, the scheme-B seeds and the control.
* Docs: README, USER_GUIDE §5.2/§15, `LUXORPARTS_PAIRS.md`,
  `LUXORPARTS_TIMELINE.md`, `LUXORPARTS_PROTOCOL_ANALYSIS.md` §6/§7.

### Version

3.4.0.4 → **3.4.0.5** in both `manifest.json` files.

### Verification

* Scheme-B values computed and asserted; five pairs, ON ≠ OFF, zero overlap with
  the 62 captured codes and with the control.
* The control's codes equal LPD 7's recorded pair exactly.
* `tests/test_ha_integration.py`, `py_compile`, `const.py` doctests, mirror copies
  byte-identical.

### Not verified

* No Luxorparts receiver here: both scheme B and the control are untested on
  hardware. The control is expected to work because it is the recorded LPD 7 pair.

## Session — 2026-11-19 (third): scheme B accepted, seeds moved to address bits

### What the user reported

* **All six switches were accepted** by the 50969 — CONTROL and all five scheme-B
  pairs. Generation works; the receiver learns codes it has never seen.
* However, some switches appeared to carry the **same code** as others, and some
  had **on/off reversed**.

### What that means

The v3.4.0.5 pairs only moved the seed by 1…5, i.e. payload bits 1–3. Codes that
differ in those bits collapsed onto one socket with different states, so the
receiver **decodes** the payload: the low bits are state/unit, the upper bits the
address. "Store the whole code and compare" is therefore ruled out.

### Changed

* `const.py`: `LX_LIVE_SEED_OFFSETS = (0x0400, 0x0800, 0x1000, 0x2000, 0x4000)`;
  `LX_TEST_LIST` is built from the LPD 7 control seeds plus one offset each, so
  every switch differs from the control and from the others in a high payload bit
  (11–15). Codes: `0x2454C38`/`0x2637638` … `0x2490C38`/`0x2673638`, control
  `0x2450C38`/`0x2633638`.
* `strings.json` / `translations/en.json`: `lx_test` text now describes the
  address-bit offsets and no longer claims "one seed step" spacing.
* Docs: README, USER_GUIDE §15, `LUXORPARTS_PAIRS.md`, `LUXORPARTS_TIMELINE.md`,
  `LUXORPARTS_PROTOCOL_ANALYSIS.md` §7 (results + revised procedure).

### Version

3.4.0.5 → **3.4.0.6** in both `manifest.json` files.

### Verification

* New codes computed and asserted: ten distinct generated codes, ON ≠ OFF per
  pair, no overlap with the 62 captured codes, control still byte-identical to
  LPD 7, six distinct UIDs, LPD 7's own UID untouched.
* `tests/test_ha_integration.py`, `py_compile`, `const.py` doctests, mirror copies
  byte-identical.

### Not verified

* No receiver here: whether the address-bit offsets produce sockets the receiver
  treats as separate devices is the next hardware test. The encoder is still
  unknown; a rejection or another collapse means the address field sits elsewhere.

## Session — 2026-11-19 (fourth): pairs built from one plaintext record

### What the user reported

* All five generated switches now work — but **only the CONTROL turns off**.
* The receiver is taught by the ON code alone; once the ON works the OFF is
  expected to work too.

### What that means

A seed offset is added to the stored payload, i.e. after the cipher. Decrypting
the recorded pairs (Homey cipher, inverted) shows the two halves are two separate
encryptions of one record, e.g. LPD 7: ON `0x2450C38` → `D5 10 86`, OFF
`0x2633638` → `D5 B1 46`. Offsetting each ciphertext on its own produced pairs
whose halves decoded to **different devices**, so the receiver — which derives the
OFF from the ON it learned — could only ever answer the ON. The CONTROL worked
because it replays a recorded pair.

Decrypting the recorded list also settles the cipher question: all five criss-cross
groups (LPD 4/9, 8/10, 13/18, 14/19, 15/17) decode to one plaintext address with
two control bytes, and one plaintext address is shared by each remote's codes.

### Changed

* `const.py`: `_lx_live_pair()` / `LX_LIVE_SEED_OFFSETS` removed.
  `_lx_plain_pair(address)` encrypts one record twice: same address, control bytes
  `0x86` ON / `0x46` OFF (unit 6) — the recorded LPD 7 pair's own field values.
  `LX_TEST_ADDRESSES = (0xD601, 0xD602, 0xD603, 0xD604, 0xD605)`. Codes:
  `0x21C7C38`/`0x203B638`, `0x26EDC38`/`0x25E1E38`, `0x2536C38`/`0x228C638`,
  `0x27FCC38`/`0x2380E38`, `0x203B438`/`0x21C7E38`; control unchanged.
* `config_flow.py`: `async_step_lx_test()` docstring describes the new pairing.
* `strings.json` / `translations/en.json`: `lx_test` text no longer mentions seed
  offsets.
* README, USER_GUIDE §15, `LUXORPARTS_PAIRS.md`, `LUXORPARTS_TIMELINE.md`,
  `LUXORPARTS_PROTOCOL_ANALYSIS.md` §6/§7/§9.

### Version

3.4.0.6 → **3.4.0.7** in both `manifest.json` files.

### Verification

* `_lx_plain_pair(0xD510)` reproduces the recorded LPD 7 ON code byte for byte;
  every pair decrypts back to one address with control bytes `0x86`/`0x46`.
* Ten distinct codes, ON ≠ OFF per pair, no overlap with the recorded codes, every
  payload bit 0 = 1 and frame MSB 0, control byte-identical to LPD 7, six distinct
  UIDs, LPD 7's own UID untouched.
* `const.py` doctests, `py_compile`, `tests/test_ha_integration.py`, mirror copies
  byte-identical.

### Not verified

* No receiver here: whether the 50969 keys a device on the plaintext address and
  reads state from the control byte is the next hardware test.

### Added — the v1 test device, for side-by-side retesting

Asked for by the owner, so the first B build can be retested at the same time as
the current one:

* `const.py`: widget **22** and catalog entry "Luxorparts — Test device v1, seeds
  +1..5 (beta, Duo only)". `_lx_seed_pair()` (the v3.4.0.5 arithmetic) is back,
  `LX_TEST_V1_LIST` / `LX_TEST_V1_CODES` hold houses 111–115
  (`0x2450C48`/`0x2633648` … `0x2450C88`/`0x2633688`) — byte-identical to the
  v3.4.0.5 build — and `LX_CONTROL_V1_CODES` replays LPD 7 on house 116.
  `luxorparts_generate_codes()` returns them for 111–116.
* `config_flow.py`: the switch-config body of `async_step_lx_test()` moved into
  `_add_lx_test_switches()`; new `async_step_lx_test_v1()`, routed from widget 22.
* `strings.json` / `translations/en.json`: `lx_test_v1` step and
  `lx_test_v1_added` abort.
* House ranges do not overlap (101–106 vs 111–116), so both devices can be added
  together and keep separate UIDs.

Version 3.4.0.7 → **3.4.0.8**.

## Session — 2026-11-19 (fifth): both builds retested, no generated OFF

### What the user reported

Both test devices taught to one 50969:

* **v1 (houses 111–116):** B1 reversed and learns with the off press; B2 reversed
  and refuses to learn but works once B1 is taught; B3 and B4 correct; B5 reversed.
* **Plaintext pairs (houses 101–106):** learns and turns on, **no OFF works — on
  all five**.
* **Both controls** work both ways.

### What that means

1. The receiver **decodes and validates** the payload. A rebuilt ON cannot run
   *reversed* unless it is decoded, and B2 cannot be *refused* at learn time
   unless the frame is checked.
2. The plaintext rebuild — the recorded LPD 7 control bytes `0x86`/`0x46` at a
   fresh address — is falsified for OFF: five of five failed. So the OFF is not
   "the same record with the state bits flipped".
3. Decrypting all 24 recorded pairs adds: payload bits 0–4 never change within a
   pair (unit, shared); bits 5–7 and 8–23 change in every pair (19 distinct
   `ON ^ OFF` masks — no single state bit exists); and the seven unit-6 pairs
   always satisfy `OFF ctrl = ON ctrl ^ 0xC0`, with the **address** as the only
   other difference.

The one variable the two builds never isolated is the address: a fresh address
loses the OFF even when its ON is accepted, while the recorded address family
accepts two of five rebuilt pairs. That is what the new group tests.

### Changed

* `const.py`: `_lx_decrypt_payload()` (inverse cipher, round-trip checked),
  `LX_LIVE_STATE_XOR = 0xC0`, `_lx_same_address_off()`, `LX_SAME_OFF_LPDS`
  (LPD 20…24), `LX_SAME_OFF_HOUSES` (121…125), `LX_SAME_OFF_LIST` /
  `LX_SAME_OFF_CODES`, control house 126 (recorded LPD 7 pair), widget **23** and
  its catalog entry, `luxorparts_generate_codes()` lookups.
* `config_flow.py`: `async_step_lx_test_v3()` (widget 23), reusing
  `_add_lx_test_switches()`.
* `strings.json` / `translations/en.json`: `lx_test_v3` + `lx_test_v3_added`; the
  plaintext-pair description no longer claims the receiver derives the OFF.
* README, USER_GUIDE §15, `LUXORPARTS_PAIRS.md`, `LUXORPARTS_TIMELINE.md`.

### Version

3.4.0.8 → **3.4.0.9** in both `manifest.json` files.

### Verification

* `_lx_decrypt_payload()` inverts the cipher (`0x48A187` → `D5 10 86`); the five
  ONs are the recorded LPD 20–24 codes verbatim; the five OFFs are new codes, each
  the ON's address with `ctrl ^ 0xC0`; no clash with the recorded list or widgets
  21/22; every payload keeps bit 0 set and frame MSB clear; six distinct UIDs.
* `const.py` doctests, `py_compile`, `tests/test_ha_integration.py`,
  `strings.json` == `translations/en.json`, mirror copies byte-identical.

### Not verified

* No receiver here — the recorded-ON group is the next hardware test.

## Session — 2026-11-19 (sixth): v3 failed; v1 decoded — bit 6 is state

### What the user reported

v3 (houses 121–126): every switch learns and turns on, **no OFF works** — five of
five. Four builds in a row have now failed on OFF, and the user's note is the key:
*"some perfectly working and some flawed or reversed, but with both on and off
working in v1 — the key has to be in v1."*

### What v1 says

| Switch | ON ctrl | OFF ctrl | `ctrl >> 6` ON/OFF | Reported |
| --- | --- | --- | --- | --- |
| LPD 7 | `0x86` | `0x46` | `10`/`01` | correct |
| B1 | `0x6C` | `0xAC` | `01`/`10` | reversed |
| B2 | `0x4A` | `0x8A` | `01`/`10` | reversed, refused |
| B3 | `0x2B` | `0xEB` | `00`/`11` | correct |
| B4 | `0x09` | `0xC9` | `00`/`11` | correct |
| B5 | `0xD8` | `0xA8` | `11`/`10` | reversed |

**Bit 6 of the control byte is the state bit** (0 = ON, 1 = OFF); bit 7 is a
don't-care. All six outcomes follow, and the three reversals are exactly the three
ON halves with bit 6 set. The recorded pair also keeps **two** addresses (`D510`
on, `D5B1` off); v1 kept both and every failed build replaced the OFF's address,
which is why no OFF ever matched.

### Changed

* `const.py`: `_lx_unit_pair(unit)` builds a device from the recorded pair's two
  addresses and state patterns —
  `encrypt(D5, 0x10, 0x80 | unit)` / `encrypt(D5, 0xB1, 0x40 | unit)` — with
  `LX_LIVE_ADDR_ON/OFF`, `LX_LIVE_CTRL_ON/OFF` and
  `LX_TEST_UNITS = (9, 11, 7, 8, 10)`. `unit 6` reproduces the recorded LPD 7 pair
  byte for byte.
* Removed the falsified v3 group (widget 23, houses 121–126) with its const block,
  config-flow step, strings and catalog entry.
* Widget 22 (v1) untouched: it is the reference the rule came from.
* README, USER_GUIDE §15, `LUXORPARTS_PAIRS.md`, `LUXORPARTS_TIMELINE.md`,
  `LUXORPARTS_PROTOCOL_ANALYSIS.md` §7/§9.

### Version

3.4.0.9 → **3.4.0.10** in both `manifest.json` files.

### Verification

* `_lx_unit_pair(6)` == `(0x2450C38, 0x2633638)`; all five pairs decrypt to
  `D510`/`D5B1` with `ctrl >> 6` = `10`/`01`, the same unit in both halves, and
  payload bit 0 set (the one bit fixed in all 62 captures — 16 of 32 units qualify,
  which is why the list is 9, 11, 7, 8, 10 rather than 1…5).
* Ten distinct codes, no overlap with recorded or v1 codes, control still the
  recorded pair, six distinct UIDs.
* `const.py` doctests, `py_compile`, `tests/test_ha_integration.py`,
  `strings.json` == `translations/en.json`, mirror copies byte-identical.

### Not verified

* No receiver here: whether units other than 6 are separate devices at a 50969 is
  the next hardware test.

## Session — 2026-11-19 (seventh): v4 failed; the reversal in v1 explained

### What the user reported

v3.4.0.10 (houses 101–106, new units of the recorded LPD 7 address pair): only **B1
and B3** learned and turned on, with **no OFF**; **B2, B4 and B5 could not learn at
all**; control fine. The owner also restated the hard facts: scheme A never worked,
and v1 is the only build whose OFF ever worked — two correct, two reversed but
working, one reversed and flawed.

### What the data says

* Every generated build has now failed: A, v2, the plaintext pairs, v3 and v4.
  Every one of them invented the encrypted part of the frame.
* v1 differs in exactly one way: it is a **recorded** pair shifted by `+2·offset`,
  and the cipher's nibble chain means that shift rewrites only the control byte —
  both recorded addresses survive.
* The payload's low 5 bits are the **channel field**, shared by both halves of every
  recorded pair. Channel bit 2 (`0x04`) decides which of the two frames is ON: five
  recorded pairs are siblings with that bit flipped and the roles swapped
  (LPD 4/9, 8/10, 13/18, 14/19, 15/17).
* v1's +1, +2 and +5 offsets cleared bit 2 and ran reversed; +3 and +4 kept it and
  worked — exactly the hardware result. +5 also carried into bit 5, which is why it
  was flawed as well.

### Changed

* `const.py`: v5 group `LX_TEST_V5_LIST` / `LX_TEST_V5_CODES` (houses 131–135),
  `LX_CONTROL_V5_HOUSE = 136` / `LX_CONTROL_V5_CODES`, lookups in
  `luxorparts_generate_codes()`; widget **24** plus its catalog entry.
* `config_flow.py`: `async_step_lx_test_v5()`, reusing `_add_lx_test_switches()`.
* `strings.json` / `translations/en.json`: `lx_test_v5`, `lx_test_v5_added`.
* README, USER_GUIDE §15, `LUXORPARTS_PAIRS.md`, `LUXORPARTS_TIMELINE.md`,
  `LUXORPARTS_PROTOCOL_ANALYSIS.md` §7/§9.

### Version

3.4.0.10 → **3.4.0.11**.

### Verification

* All five v5 pairs keep their recording's two addresses, channel bit 2, payload bit
  0 in both halves, and ON ≠ OFF; ten distinct codes; 131/132 are v1's B3/B4 on
  purpose; control 136 is the recorded LPD 7 pair.
* `const.py` doctests, `py_compile`, `tests/test_ha_integration.py`,
  `strings.json` == `translations/en.json`, mirror copies byte-identical.

### Not verified

* No receiver here: whether a shifted recording is accepted as a separate device,
  and whether B3…B5 behave like B1/B2, is the next hardware test.

---

## v3.4.0.12 — generated Luxorparts pool on Duo and Net v1; test devices removed

**v5 passed 5/5 on hardware (2026-11-19),** so the channel-field rule is now a
generator. The four test-device types (widgets 21, 22, 24 + catalog entries + strings
+ their `const.py` groups) are removed, and the pool ships as a normal experimental
device path:

* **Duo:** widget 25 → `luxorparts_codes()` → `luxorparts_build_raw_command()`
  (`P\x02 R10 S50+`, unchanged).
* **Net v1:** `_encode_luxorparts_variant()` now uses the same helper instead of
  `LX_GROUND_TRUTH_CODES`, so generated houses resolve. The v1 firmware caps the `S`
  payload at 199 bytes, so the burst is trimmed from 10 frames (500 B) to **3 frames
  (150 B)**; the encoder would previously have refused the packet outright. This path
  has **not been tested against a receiver**.
* **ZNet / Net v2:** unchanged — raw pulse packets are discarded by that firmware.

### Changed

* `const.py`: pool helpers (`luxorparts_channel_codes()`, `luxorparts_codes()`,
  `LX_GEN_*`), widget 25, generated catalog entry, `lx_gen` timing profile,
  variant-aware `build_device_uid()`; test-device groups deleted.
* `config_flow.py`: test steps and `_add_lx_test_switches()` deleted; the Luxorparts
  confirm branch uses `luxorparts_codes()`.
* `switch.py` / `button.py` / `net_client.py`: dispatch through `luxorparts_codes()`.
* `strings.json` / `translations/en.json`: `lx_test*` keys removed.

### Version

3.4.0.11 → **3.4.0.12**.

### Verification

* `const.py` doctests, `py_compile`, `tests/test_ha_integration.py`, JSON/strings
  parity, byte-identical mirror, both manifests 3.4.0.12.
* Pool: 304 distinct pairs from 19 families × 16 channels; the five v5
  hardware-proven codes reproduce exactly; recorded LPD 1–24 lookups unchanged.

### Not verified

* 275 of 304 codes have never been at a receiver.
* Net v1 transmission of a 3-frame burst.

### v3.4.0.13 — the channels are the beta device type, not a second one

The generated pool was re-homed onto the beta path. Its own device type (widget 25,
`selflearning-switch:lx_gen`) lost the typed name and sent the generic cipher on
on/off: `RawDeviceEvent` publishes the RF-normalised model (`selflearning`), so the
entity UID was `luxorparts_selflearning_<lpd>_<channel>` while the stored device was
`luxorparts_lx_gen_<lpd>_<channel>`. The pool was also not unique — 24 LPD × 16
channels is 384 combinations, but only 19 of the 24 recordings are distinct
receivers, so 80 combinations repeated another entry.

Now: beta device type (`selflearning-switch:lx_live`, widget 20), house = LPD (a
`select` of the 19 distinct receivers), unit = channel 1–16 with unit 1 the recorded
pair. `luxorparts_generate_codes()` resolves ground truth → generated channel →
cipher, `luxorparts_codes()`, `LX_GEN_VARIANT`, the `lx_gen` timing profile,
widget 25 and the variant-aware UID are removed, and every offered combination is a
distinct code pair (304).

Version 3.4.0.12 → **3.4.0.13**. Verified by doctests, `py_compile`,
`tests/test_ha_integration.py`, strings/JSON parity, mirror diff and the pool script;
not verified on hardware.

### v3.4.0.14 — separate paths, one slider each

v3.4.0.13 folded the generated channels into the beta device type: an LPD `select`
plus a unit 1–16. That was not the beta path — the beta path was one number — and it
was worse than the type it replaced. Split back into two device types, each ONE list
of on/off pairs behind ONE slider:

* beta — widget 20, `selflearning-switch:lx_live`, slider 1–24: the 19 distinct
  recordings (the five duplicate recordings are not offered) then the five generated
  pairs confirmed on hardware.
* experimental — widget 21, `selflearning-switch:lx_exp`, slider 1–280: the remaining
  generated pairs, none ever at a receiver.

The slider value is resolved to house = LPD, unit = channel, so `switch.py`,
`button.py`, `net_client.py`, `luxorparts_generate_codes()` and the device UID are
unchanged. `LX_GEN_LPD_OPTIONS`, the `select` field type and the `select` branch of
`_build_params_schema()` are removed; a `slider` field type renders an HA
`NumberSelector` in slider mode.

Deleting devices no longer resurrects them: `async_remove_config_entry_device()` now
records every removed UID in `ignored_uids`, so auto-add, the discovery flow and
`_import_app_configured_devices()` all skip it. Previously a deleted device came back
on the next RF event or the next restart.

Version 3.4.0.13 → **3.4.0.14**. Verified: doctests, `py_compile`, pyflakes,
`tests/test_ha_integration.py`, mirror diff, strings/JSON parity, and a script that
checks 24 + 280 pairs (disjoint, 304 distinct code pairs, slider → house/unit → same
code pair, both sliders serialize as `NumberSelector` sliders). Not verified on
hardware.

### v3.4.0.15 — deleting a grouped device removes it for real

The v3.4.0.14 fix only covered cards whose identifier is the stored device UID.
The removed Luxorparts test paths added their switches as ONE grouped card
(identifier `{entry_id}_group_{group_uid}`), so deleting that card matched no
stored device: nothing was removed from `devices`, nothing was ignored, and the
platforms rebuilt the card — with its switches — on the next reload or restart.

`async_remove_config_entry_device()` now resolves a `group_` card to every stored
device carrying that `group_uid`, removes all of them from `devices` and from
telldusd, deletes their entities (learn buttons included), and records each UID in
`ignored_uids`. A card that matches no stored device is ignored as well, so a
leftover registry UID cannot be re-imported by auto-add, the discovery flow or
`_import_app_configured_devices()`.

Version 3.4.0.14 → **3.4.0.15**. Verified: doctests, `py_compile`, pyflakes,
`tests/test_ha_integration.py`, mirror diff, strings/JSON parity. Not verified in
the HA UI or on hardware.
