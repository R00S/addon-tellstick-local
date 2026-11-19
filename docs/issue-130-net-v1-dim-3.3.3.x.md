# Branch: issue-130-net-v1-dim — 3.3.3.x → 3.4.0.x

> This branch started on the 3.3.3.x line. The TellStick Net v1 protocol work was
> re-landed as the 3.4.0.x series on `net-v1-protocols` (up to 3.4.0.2), and this
> branch merged that line in so the Luxorparts work ships as **3.4.0.3**. Sessions
> below keep their original headings; the shared 3.4.0.x history is in
> [`5fe97fc32425f971ae084741-3.4.0.x.md`](5fe97fc32425f971ae084741-3.4.0.x.md).
Continues the 3.3.3.x series started on `main` (see
[`docs/5fe97fc32425f971ae084741-3.3.3.x.md`](5fe97fc32425f971ae084741-3.3.3.x.md))
and the earlier 3.3.1.x/3.3.2.x history in
[`docs/8aa7ad394de32864627ccce6-3.3.1.x.md`](8aa7ad394de32864627ccce6-3.3.1.x.md).

---

## Session — 2026-11-10 — Issue #130 (Net v1 dimming does nothing)

**Trigger:** after the #114 fix shipped in 3.3.3.0, the reporter confirmed on/off
works on an original TellStick Net v1 (firmware 17, arctech
`selflearning-dimmer:nexa`, house 1456353 unit 1) but brightness does not: HA
shows the requested percentage and the receiver does not change. Dimming from
the physical Nexa remote still works.

### Root cause

Two separate firmware quirks, both in the **v1 C firmware** (`tellsticknet.c` /
`transmit_arctech.c`), not in our packet encoding:

1. `send()` reads `protocol` first. If it is present and equals `arctech`, it
   requires `model == "selflearning"` exactly and then calls
   `sendArctechSelflearning()`, returning without ever looking at `S`.
   Our dim packet carries `model="selflearning-dimmer"`, so the `strcmp` fails
   and the firmware returns — **the packet is dropped before RF**, which is why
   nothing at all happens (no blink, no brightness change).
2. Even with the model fixed, the native handler only checks `method == 1`
   (one frame) vs everything else (zero frame). There is no dim method and no
   level field, so a DIM method would be transmitted as an OFF frame.

The `TURNON → DIM(255)` workaround that the ZNet path relies on does not exist
on v1. The only dim path v1 has is raw pulse playback: a packet with an `S`
key and **no** `protocol` key reaches `rfSend()`, which replays the bytes
regardless of protocol. molobrakos confirmed S-byte dim TX on production
original Net hardware, and the reporter's own probe variant D (raw `S`, issue
#114) blinked the LED, so the transport is known-good on his unit.

### Fix applied

- `_encode_arctech_command(..., *, net_v1=False)` — on v1, a non-zero DIM now
  returns an `S`-only dict built by `_arctech_dim_pulse_train()` (147-byte
  arctech selflearning dim train, level quantised to 16 hardware steps).
  Level 0 still maps to TURNOFF (native dict, which v1 does transmit).
  On/off/learn are unchanged on both firmware families, and v2/ZNet keep the
  native `TURNON → DIM(255)` behaviour.
- `TellStickNetController` gained `product` (from UDP discovery:
  `TellStickNet` = v1, `TellstickNetV2`/`TellstickZnet` = Python firmware) and
  `_ensure_product()`, which performs a single 2 s discovery broadcast the
  first time a dim is sent and the product is unknown (entries created before
  the product was stored).
- `config_flow` stores `product` in the Net config entry; `__init__.py` passes it
  to the controller.
- `_arctech_dim_pulse_train()` docstring rewritten: it is now live code for v1,
  not a reference-only dead function.

### Mirrors (runtime copy)

`net_client.py`, `config_flow.py`, `__init__.py` and `manifest.json` copied to
`tellsticklive/rootfs/usr/share/tellstick_local/`; `diff -rq` reports the two
directories identical (ignoring `__pycache__`).

### Version

- Bumped 3.3.3.0 → **3.3.3.1** in both `manifest.json` files.

### Verification (local venv, Home Assistant 2025.1.4)

- `tests/test_net_protocol_encoding.py` — ALL PASS, including new assertions:
  v2/ZNet dim stays a native `TURNON` dict with no `S` key; v1 dim returns an
  `S`-only dict of 147 bytes starting `18ff` and ending `18`; different levels
  produce different frames; v1 level 0 still returns TURNOFF.
- `tests/test_net_udp_hub.py` — ALL PASS
- `tests/test_device_types.py` — ALL PASS
- `tests/test_ha_integration.py` — ALL PASS (integration still loads in HA)
- pyflakes clean on every changed production file (the one warning is a
  pre-existing unused import in the test file, present on `main` too).

### Not verified

- Real hardware. The reporter has the only confirmed Net v1 in this thread; the
  encoding is a faithful port of molobrakos/tellstick-core, but only his unit
  can confirm the receiver dims. Needed from him: LED blink on brightness
  change, physical brightness actually changing, and whether levels map
  sensibly across the whole slider range.
- Behaviour on v1 units whose discovery reply is unavailable (product stays
  unknown): they keep the old native dim path, i.e. no regression, no fix.

### Not done / next steps

- Ask the #130 reporter to test a 3.3.3.1 build on the dev channel. **This is
  the decision gate for the follow-on work below.**
- If v1 dim is confirmed on hardware: implement **raw-first TX for TellStick Net
  v1** — the v1 firmware replays arbitrary `S` pulse bytes, so every protocol
  the Duo can transmit becomes reachable on v1 (and stays unreachable on
  v2/ZNet). Plan, protocol table and verification steps:
  [`docs/NET_V1_RAW_TX_PLAN.md`](NET_V1_RAW_TX_PLAN.md).
- Raw-first also fixes v1 `learn` (the native dict currently transmits an OFF
  frame — pre-existing, separate issue).
- Recruiting more Net v1 owners as testers is part of that plan: they are the
  only people who can unlock per-protocol TX support, and the #130 report shows
  they are still active.

## Session — 2026-11-10 — ZNet firmware decompile (TX path verified)

**Trigger:** the v2/ZNet raw-send question could not be settled from the old
notes, which contradicted each other.

**Done:** added `tools/decompile_znet_firmware.py` (SquashFS at `0x130ad8` → `.pyc`
→ `uncompyle6`), decompiled the `productiontest`, `rf433` and `telldus` module
roots (35 `.pyc`, 32 decompiled) and replaced the speculative TX section of
`docs/ZNET_FIRMWARE_ANALYSIS.md` with quoted code.

**Findings:** `handleSend()` raises an uncaught `KeyError('protocol')` on S-only
packets, ignores `S` when `protocol` is present, hardcodes `prefixes={}` and
passes `None` as the dim level; `DeviceNode._command()` (vendor-gated API) does
support `P`/`R` and real levels. So v2/ZNet raw TX over UDP is impossible, not
merely unproven — which is why the v1 raw path on this branch is the only
firmware-free route to Duo-level protocol support.

**Not done:** no attempt to decompile the whole rootfs, no vendor source
committed. `morluto/rea` was evaluated and rejected: it targets native, JS,
.NET and Android binaries (via Ghidra/IDA/Hopper), not Python 2.7 bytecode.

## Session — 2026-11-19 — Luxorparts: protocol re-analysis and generated test codes

**Trigger:** the owner reported that all 24 recorded Luxorparts LPD pairs work
through the Duo path. That confirmed the replay path but reopened the real
question — can codes be generated instead of only replayed? An earlier claim
("no cipher; any payload will do") did not survive review of the 62 captures and
was withdrawn.

### Research — `docs/LUXORPARTS_PROTOCOL_ANALYSIS.md`

- The frame is 25 bits. Only payload bit 0 is constant; there is no preamble and
  no checksum. The frame MSB is a family marker (`0` Live, `1` remote).
- Remote family (7 buttons, 14 codes) is a fixed template `0x5D55D5` with five
  data bits: state (bit 1), buttons (9/11/13), remote (17).
- Live family (24 pairs, 48 codes) has no constant bit except bit 0, and ON/OFF
  are independent codes rather than a state-bit pair.
- The 48 Live codes collapse to 19 distinct `ON^OFF` values: five pairs of LPD
  entries are one bit apart in a criss-cross (`0x04`) — LPD 4/9, 8/10, 13/18,
  14/19, 15/17. That is an unexplained field, not 24 independent devices.
- The Homey nibble cipher is ruled out for the remote family (a chain cipher
  cannot flip a single bit); it stays an unconfirmed candidate for Live.
- Seeds: all 48 Live codes regenerate from `payload24 >> 1` in
  `0x206CC3`–`0x6DB763`; B-wide reproduces all 62 including the remote seeds
  `0xAEAFEB`–`0xAFBEEB`.
- Generation remains unproven: every code that has ever worked is a recording.

### Test device

Opt-in device type **"Luxorparts — Generated test codes (beta, Duo only)"**,
picks 101–105 = LX-T1…LX-T5 (`LX_TEST_LIST` / `LX_TEST_CODES`, widget 21). Each
pair clones the remote template with a button field no capture contains (bit 9,
bit 11, bits 9+11+13, none, bit 9 + bit 17), frame MSB set. The recorded LPD
picker stays 1–24 and the codes are deliberately outside it. Timing and the
`P\x02 R10 S50+` path are unchanged.

### Documentation corrections

- §6's `stored28` examples had dropped the frame MSB (`0x2EBBEA8` instead of
  `0xAEBBEA8`); corrected.
- LPD 26/27 are cross-assembled: each row carries one ON and one OFF code from
  different buttons. The field table and the anomalies paragraph were rewritten,
  and `docs/LUXORPARTS_PAIRS.md` now flags the rows and records R1-B/R1-D as
  half-pairs.
- `docs/LUXORPARTS_RF_PROTOCOL.md` §4/§7.1 carry explicit superseded markers.

### Version

3.3.3.1 → **3.3.3.2** for the test device; 3.3.3.2 → 3.3.3.3 with the chores
pass. The branch then merged `net-v1-protocols` (3.4.0.2) to join the 3.4.0.x
line and was bumped to **3.4.0.3** — the test release carries the full Net v1
protocol stack plus the Luxorparts test device.

### Verification

- `tests/test_ha_integration.py` ALL PASS at 3.3.3.2 (HA 2025.1.4); `py_compile`
  and the `const.py` doctests pass.
- Script assertions: five pairs / ten unique codes, MSB set, ON/OFF differ only
  in bit 1, zero overlap with the 48 recorded codes, widget 21 accepts 101–105
  and rejects 106.
- Every table in the analysis was re-derived from the captures.

### Not verified

- No Luxorparts receiver here: whether a 50969 learns a generated pair is the
  whole point of the test device and is still untested.
- No Net v1 hardware: the dim fix still awaits the reporter's confirmation.
