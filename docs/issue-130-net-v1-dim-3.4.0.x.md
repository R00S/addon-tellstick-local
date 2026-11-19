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
