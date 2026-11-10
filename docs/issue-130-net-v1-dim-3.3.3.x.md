# Branch: issue-130-net-v1-dim — 3.3.3.x

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
