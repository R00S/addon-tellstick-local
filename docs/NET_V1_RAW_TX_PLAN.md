# TellStick Net v1 — raw pulse TX (the route to Duo-level protocol support)

> **Status:** plan only. **Nothing here is implemented beyond the #130 dim frame.**
> **Decision gate:** implement only after the issue #130 reporter confirms that a
> dimmer actually changes brightness on a real v1 with 3.3.3.1. If that test
> fails, the whole premise (v1 replays arbitrary `S` pulse bytes) is wrong and
> this document should be reverted rather than extended.

---

## The finding

The original **TellStick Net v1** (C firmware) is not a cut-down ZNet. Its local
`send` handler has **two** paths, and the second one is a generic RF pulse
player:

```c
// firmware/tellsticknet.c :: send()
if (LMFindHashString("protocol")) {
    LMTakeString(&protocol, ...); LMTakeString(&model, ...);
    if (strcmp(protocol, "arctech") != 0 || strcmp(model, "selflearning") != 0) return;
    sendArctechSelflearning();   // on/off only, no dim, no level
    return;                      // never looks at "S"
}
if (!LMFindHashString("S")) return;
LMTakeString(&sendPacket, sizeof(sendPacket));
rfStartTransmit();
for (i = 0; i < repeats; ++i) { setTXPulses(2); rfSend(&sendPacket); pause_ms(pause); }
rfStopTransmit();
```

So a packet with an `S` key and **no** `protocol` key is replayed byte-for-byte
on the RF chip, with no protocol dispatch — the same thing `tdSendRawCommand`
does on a Duo. That is why the v1 can dim (3.3.3.1) while v2/ZNet cannot.

`tellstick-server` (v2/ZNet) has no equivalent: `handleSend()` starts with
`Protocol.protocolInstance(msg['protocol'])`, ignores `S` when `protocol` is
present, and passes `None` as the level. Its own encoder output is the only
thing that ever reaches `rf433`.

### Firmware limits that shape the design

| Property            | Value                                            | Consequence                                        |
| ------------------- | ------------------------------------------------ | -------------------------------------------------- |
| `sendPacket[200]`   | 199 bytes + terminator                           | Guard every encoder: `len(pulses) <= 199`          |
| Pulse resolution    | byte value × 10 µs                               | Same convention as the Duo raw path — ports carry over |
| Repeats / pause     | `DEFAULT_REPEATS 10`, `DEFAULT_PAUSE 11`         | Sensible defaults; override per protocol below     |
| `P` / `R` keys      | **read from the packet dict** on v1              | Per-protocol repeat/pause is possible (v2/ZNet drops them) |
| `protocol` key      | Takes priority and ends the packet               | v1 raw packets must be **S-only**                  |

## What works on v1 today

| Area                       | Status                                                        |
| -------------------------- | ------------------------------------------------------------- |
| arctech on/off             | ✅ Native dict, confirmed on hardware (reporter, 3.3.3.0)      |
| arctech learn              | ⚠️ Native dict sends an OFF frame (pre-existing v1 quirk)      |
| arctech dim                | 🔬 Raw `S` train in 3.3.3.1 — **awaiting hardware confirmation** |
| every other protocol       | ❌ Native dict is dropped by the v1 firmware before RF         |

## What raw-first TX would unlock

If the dim test passes, then on a v1 **any protocol we can encode as pulses
works** — the full Duo TX list — plus correct learn and per-packet repeat/pause.
v2/ZNet stays where it is; nothing here changes their code paths.

| Protocol       | Net/ZNet today | Encoder for v1 raw                                  |
| -------------- | -------------- | --------------------------------------------------- |
| `arctech`      | on/off + DIM(255) | ✅ done — raw on/off proven by probe D, dim in 3.3.3.1 |
| `comen`        | native dict    | 🟢 cheap — arctech selflearning frame with `(house << 2) + 2` |
| `everflourish` | testing        | 🟢 20 raw variants (`ef_r*`) already in `net_client.py`, written for the ZNet `S` path; needs v1 verification |
| `kangtai`      | none           | 🟡 needs port (Clas Ohlson dimmer; no Net encoder exists) |
| `waveman`      | none           | 🟡 needs port — reuse arctech code-switch framing      |
| `yidong`       | none           | 🟡 needs port — reuses sartano framing                 |
| `hasta`        | broken         | 🔴 needs port — UP/DOWN/STOP, needs `R=10 P=25`        |
| `brateck`      | broken         | 🔴 needs port — UP/DOWN/STOP only                      |
| `ikea`         | broken         | 🔴 needs port — system + units + level                 |
| `risingsun`    | broken         | 🔴 needs port                                          |
| `sartano`      | broken         | 🔴 needs port — code + system                          |
| `silvanchip`   | broken         | 🔴 needs port                                          |
| `upm`          | broken         | 🔴 needs port                                          |
| `x10`          | broken         | 🔴 needs port                                          |
| `fuhaote`      | broken         | 🔴 needs port — code switch                            |

Encoder sources are the telldus-core `Protocol*.cpp` `stringForMethod()`
implementations; the porting pattern is already documented in
[`docs/ZNET_PROTOCOL_PORTING_GUIDE.md`](ZNET_PROTOCOL_PORTING_GUIDE.md).

## Design sketch

1. **Product gate (already in place).** `TellStickNetController.product` comes
   from UDP discovery (`TellStickNet` = v1). Only a v1 takes the raw path, so
   v2/ZNet behaviour cannot regress.
2. **Raw-first routing.** When the product is `TellStickNet`, prefer an
   S-only encoder for every send; keep the native arctech dict only as a
   fallback for units where discovery failed (current behaviour).
3. **S-only invariant.** A v1 raw packet must never carry `protocol`/`model`;
   add an assertion in the send path so a future encoder cannot silently build
   a packet the firmware will drop.
4. **Per-protocol parameters.** A small table of `{protocol: (repeats, pause)}`
   so hasta/brateck/luxorparts-style protocols get what they need, defaulting
   to the firmware's 10 / 11 ms.
5. **Size guard.** Refuse (and log) any frame over 199 bytes instead of sending
   a truncated one.
6. **Make `raw` reachable again.** `ENCODING_RAW` (`"raw"`) still exists in the
   data model, but the Net "Add device" menu no longer offers the raw step, so
   `_send_rf()` never sees it for arctech. Raw-first routing by product would
   make the per-device `raw` / `native` / `native_nofix` choice meaningful
   again (and keep a manual override for testing).

## Verification plan (the real bottleneck)

Nothing about this is provable in CI; each protocol needs a receiver.

1. **Unit level** — golden pulse bytes per protocol (ported from telldus-core
   or captured from a Duo), asserted in `tests/test_net_protocol_encoding.py`.
2. **Byte-for-byte against the Duo** — where a Duo is available, capture what
   telldusd sends for the same device/command and diff against our v1 encoder
   output. This catches timing and bit-order mistakes without a v1.
3. **Probe tool** — extend the `tools/probe_net_send.py` pattern (issue #114)
   to send one protocol variant per run and ask the human: LED blink? receiver
   responded? That conversation is what made #114 solvable.
4. **RTL-SDR cross-check** — as used in
   [`docs/DIMMER_INVESTIGATION.md`](DIMMER_INVESTIGATION.md): capture our v1
   transmission and decode the frame to confirm the bytes on air, not just the
   bytes in the packet.
5. **Regression** — `tests/test_net_udp_hub.py`, `tests/test_ha_integration.py`
   and the v2/ZNet encoding assertions must stay green; the product gate means
   v2/ZNet packets are unchanged by construction.

## Rollout

1. Wait for the #130 dim result on a real v1.
2. If positive: merge the dim fix, then add the raw-first skeleton + arctech
   raw on/off behind the v1 gate (no behaviour change for anyone else).
3. Port protocols in demand order, not alphabetically — `hasta`/`brateck`
   covers and `ikea` affect the most users; each port ships with its probe
   variant and a "needs confirmation" note in the user guide.
4. Ask v1 owners to volunteer as testers per protocol. This is the practical
   argument for onboarding more v1 users: on a v1 their hardware can do what a
   ZNet cannot, so they are the only testers who can unlock protocol support
   for the whole project.

## Open questions

- Does the 199-byte cap ever bind in practice? Longest current encoders
  (everflourish, luxorparts) are ~50 bytes; the arctech dim frame is 147.
- Some receivers may need an inter-packet gap longer than `P` provides; if so,
  split into multiple `send` packets (as the Duo path already does).
- v1 `learn` via raw is theoretically a one-bit frame, but unverified on
  hardware; treat as its own port with its own probe.
- The stale "raw S bytes work on real Net/ZNet hardware" paragraph near the end
  of [`docs/ZNET_FIRMWARE_ANALYSIS.md`](ZNET_FIRMWARE_ANALYSIS.md) contradicts
  this document and the decompiled handler; this document is authoritative.
