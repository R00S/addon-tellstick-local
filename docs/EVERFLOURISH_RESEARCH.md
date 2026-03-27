# Everflourish Protocol — Research & Implementation Notes

> **Issue:** [#85](https://github.com/R00S/addon-tellstick-local/issues/85) —
> GAO (everflourish) protocol works on TellStick Duo but not on TellStick ZNet.

> **⚠️ Status (2026-03):** ZNet testing showed that the raw S-only encoder
> (v1) produces **no blinking**, while the native firmware path produces
> **blinking** (both with and without unit-1 fix).  This means `handleSend()`
> on ZNet v2 **requires the `protocol` key** — S-only dicts are silently
> dropped.  20 encoding variants (EF raw v1–v20) are now available in the
> "by protocol (raw)" menu to empirically test which approach works on
> each hardware version.  Cross-TellStick RX still untested — Duo-generated
> everflourish signals are not picked up by Net/ZNet as a receiver.
>
> **Timing research (from TellStick protocol spec):**
> Each byte value in the S pulse train = `byte_value × 10 µs`.
> Standard: short=60 → 600 µs, long=114 → 1140 µs (same in telldus-core
> AND tellstick-server).  Duo adds R=5 (5 repeats) and `+` end marker;
> ZNet internal path sends once with no repeat and no `+`.
>
> **Test variants (in "by protocol (raw)" menu):**
>
> | # | Name | Dict keys | Hypothesis |
> |---|------|-----------|------------|
> | **Group A — S-only** | | | |
> | v1 | S-only bytes | `{S}` | Current — fails on ZNet v2 |
> | v2 | S + R=4 | `{S, R=4}` | S + repeat prefix |
> | v3 | S + R=10 P=5 | `{S, R=10, P=5}` | S + repeat + pause |
> | v4 | S doubled | `{S+S}` | Double-length signal |
> | **Group B — Native dict** | | | |
> | v5 | native nofix | `{proto, model=sw, …}` | Firmware encodes, no unit fix |
> | v6 | native fix | `{proto, model=sw, unit-1, …}` | Firmware encodes, unit-1 fix |
> | v7 | native model=sl nofix | `{proto, model=sl, …}` | Canonical model name |
> | v8 | native model=sl fix | `{proto, model=sl, unit-1, …}` | Canonical model + fix |
> | **Group C — Hybrid** | | | |
> | v9 | native+S nofix | `{proto, …, S}` | Firmware may use our S bytes |
> | v10 | native+S fix | `{proto, unit-1, …, S}` | Hybrid + fix |
> | v11 | native+S+R+P | `{proto, …, S, R, P}` | Hybrid + repeat/pause |
> | v12 | native unit-2 | `{proto, unit-2, …}` | Double compensation |
> | **Group D — Timing** | | | |
> | v13 | half timing | `{S}` 30/57 | 300/570 µs (2× multiplier?) |
> | v14 | double timing | `{S}` 120/228 | 1200/2280 µs (0.5× divider?) |
> | v15 | inverted bits | `{S}` swap 0↔1 | Bit patterns backwards? |
> | v16 | Duo sync prefix | `{S}` +[60,1,1,60] | Sync burst from Duo format |
> | **Group E — Repeat/terminator** | | | |
> | v17 | S + R=5 | `{S, R=5}` | Match Duo repeat count |
> | v18 | S + '+' term | `{S…+}` | TellStick end-of-TX marker |
> | v19 | S + R=5 P=37 '+' | `{S…+, R=5, P=37}` | Full Duo-style framing |
> | **Group F — Hybrid + repeat** | | | |
> | v20 | native+S+R=5 fix | `{proto, unit-1, S, R=5}` | Native + our S + repeat |

## Problem

Sending on/off commands to Everflourish (GAO) devices works on the TellStick
Duo backend (via telldusd + socat TCP) but silently fails on the TellStick
Net/ZNet backend (via UDP).

## Root Cause

### TellStick Net v1 (C firmware)

The original TellStick Net v1 runs a C firmware
(`tellstick-net/firmware/tellsticknet.c`) with this send logic:

```c
void send() {
    ...
    if (LMFindHashString("protocol")) {
        LMTakeString(&protocol, sizeof(protocol));
        if (LMFindHashString("model")) {
            LMTakeString(&model, sizeof(model));
        }
        // *** ONLY arctech/selflearning is handled natively ***
        if (strcmp(protocol, "arctech") != 0 || strcmp(model, "selflearning") != 0) {
            return;  // SILENTLY DROPS non-arctech commands!
        }
        sendArctechSelflearning();
        return;
    }

    // Fallback: raw pulse-train bytes via the "S" key
    if (!LMFindHashString("S")) {
        return;
    }
    LMTakeString(&sendPacket, sizeof(sendPacket));
    rfStartTransmit();
    for (i = 0; i < repeats; ++i) {
        rfSend(&sendPacket);
        ...
    }
    rfStopTransmit();
}
```

Source: https://github.com/telldus/tellstick-net/blob/master/firmware/tellsticknet.c

On v1: Native dicts are silently dropped for non-arctech protocols.

### TellStick Net v2 / ZNet (Python firmware)

The v2 and ZNet run Linux (OpenWrt) with `tellstick-server`.  Decompiled from
the firmware binary `tellstick-znet-lite-v2-1.3.2.bin` in this repo, the local
UDP send handler (`productiontest/Server.py :: CommandHandler.handleSend`)
routes through the **full Python protocol stack**:

```python
@staticmethod
def handleSend(msg):
    protocol = Protocol.protocolInstance(msg['protocol'])
    protocol.setModel(msg['model'])
    protocol.setParameters({'house': msg['house'], 'unit': msg['unit'] + 1})
    msg = protocol.stringForMethod(msg['method'], None)
    CommandHandler.rf433.dev.queue(RF433Msg('S', msg['S'], {}))
```

On v2/ZNet: ALL protocols are theoretically supported via native dict, BUT
there are bugs:
- **Unit offset**: `msg['unit'] + 1` adds 1 to unit before setParameters,
  causing commands to target the wrong unit
- **Missing parameters**: Only `house` and `unit` are passed — protocols
  needing `code`, `system`, etc. will fail
- **No R/P prefixes**: Repeat/pause values are always `{}`

### Summary

Our code was sending a native dict (`protocol=everflourish, model=selflearning,
house=X, unit=Y, method=Z`) which:
- On v1: Falls through to silent drop (no protocol handler for everflourish)
- On v2/ZNet: Would reach the protocol handler BUT may hit the unit offset bug

**Raw S bytes works on ALL versions** by bypassing all protocol dispatch.

## All Reference Implementations Examined

### 1. telldus-core — ProtocolEverflourish.cpp (TellStick Duo)

**Source:** https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp

The C implementation in telldus-core (used by telldusd on the Duo backend).
Uses the TellStick Duo's "extended" RF format with `R` (repeat), `T` (timing
table) prefix:

```cpp
const char ssss = 85;   // 0b01010101 — 4× timing[1]
const char sssl = 84;   // 0b01010100 — 3× timing[1] + 1× timing[0]   → bit "0"
const char slss = 69;   // 0b01000101 — timing[1],timing[0],timing[1],timing[1] → bit "1"

char preamble[] = {'R', 5, 'T', 114, 60, 1, 1, 105, ssss, ssss, 0};
```

This format is specific to the TellStick Duo firmware and NOT usable with the
TellStick Net/ZNet (which uses a simpler one-byte-per-pulse format).

**Encoding:**
- `deviceCode = (house << 2) | (unit - 1)` — 16-bit combined code
- 4-bit checksum via `calculateChecksum(deviceCode)`
- action: turnon=15, turnoff=0, learn=10
- Bit order: MSB first for deviceCode (16 bits), checksum (4 bits), action (4 bits)

### 2. tellstick-server — ProtocolEverflourish.py (TellStick ZNet)

**Source:** https://github.com/telldus/tellstick-server/blob/master/rf433/src/rf433/ProtocolEverflourish.py

The Python implementation used internally by the ZNet firmware. Returns raw
pulse-train bytes via `{'S': strCode}`:

```python
s = chr(60)    # short pulse (≈988 µs on the RF hardware)
l = chr(114)   # long pulse  (≈1878 µs on the RF hardware)

sssl = s+s+s+l  # bit "0"
slss = s+l+s+s  # bit "1"

# Preamble: 8 × short pulse
strCode = s*8

# Data: 16 bits deviceCode + 4 bits checksum + 4 bits action
for i in range(15, -1, -1):
    strCode += bits[(deviceCode >> i) & 0x01]
for i in range(3, -1, -1):
    strCode += bits[(check >> i) & 0x01]
for i in range(3, -1, -1):
    strCode += bits[(action >> i) & 0x01]

strCode += ssss  # terminator (4 × short)
return {'S': strCode}
```

**This is the format we need for external UDP "send" commands.**

### 3. molobrakos/tellsticknet — everflourish.py (Python library)

**Source:** https://github.com/molobrakos/tellsticknet/blob/master/tellsticknet/protocols/everflourish.py

The Python library for local TellStick Net access. It implements:
- `decode(packet)` — ✅ Works (our `_decode_everflourish` is ported from this)
- `encode(method)` — ❌ `raise NotImplementedError()` — **never implemented!**

This confirms that no external Python library has ever implemented everflourish
TX for the TellStick Net/ZNet.

### 4. Home Assistant core — tellstick integration

The deprecated HA tellstick integration uses `tellcore-py` which talks to
telldusd (same as our Duo backend). It does not implement any direct
TellStick Net/ZNet communication.

### 5. Domoticz

Domoticz has TellStick support but also uses `telldus-core`/`telldusd` for
device communication. No direct everflourish UDP implementation.

## Possible Solutions

### Option A: Generate raw pulse-train bytes locally ✅ RECOMMENDED

Port `ProtocolEverflourish.stringForMethod()` from `tellstick-server` to
generate raw pulse-train bytes in Python. Send with `S=<bytes>` key.

**Pros:**
- Works on ALL hardware (TellStick Net v1, ZNet, future devices)
- Follows the same pattern as our arctech dim implementation
- No dependency on firmware protocol support
- Matches exactly what the ZNet firmware does internally

**Cons:**
- More code to maintain (pulse-train encoding logic)
- Must be exact match to the firmware's encoding

### Option B: Keep sending native dict ❌ UNRELIABLE

Send `{protocol: "everflourish", model: "selflearning", house: X, unit: Y, method: Z}`.

**Why it fails or is unreliable:**
- TellStick Net v1 firmware ignores all non-arctech native dicts (silent drop)
- ZNet v2 firmware routes through the Python protocol stack BUT has bugs:
  - `handleSend()` adds 1 to unit (`msg['unit'] + 1`) causing wrong unit targeting
  - Only `house` and `unit` passed to protocol — missing `code`, `system`, etc.
  - R/P prefixes always empty — protocols needing custom repeat/pause will fail
- molobrakos never implemented this approach either

### Option C: Register a device on the ZNet and send commands through it ❌ COMPLEX

Create a device on the ZNet through TelldusLive API, then send commands
through the device.

**Why it's impractical:**
- Requires TelldusLive cloud connection or complex internal API calls
- The ZNet's internal device management is not accessible via the local UDP API
- Way too complex for a simple on/off command

## Checksum Algorithm

Both `telldus-core` (C++) and `tellstick-server` (Python) implement the same
checksum algorithm (credited to Frank Stevenson):

```python
def calculateChecksum(x):
    bits = [
        0xf, 0xa, 0x7, 0xe,
        0xf, 0xd, 0x9, 0x1,
        0x1, 0x2, 0x4, 0x8,
        0x3, 0x6, 0xc, 0xb
    ]
    bit = 1
    res = 0x5

    if (x & 0x3) == 3:
        lo = x & 0x00ff
        hi = x & 0xff00
        lo += 4
        if lo > 0x100:
            lo = 0x12
        x = lo | hi

    for i in range(16):
        if x & bit:
            res = res ^ bits[i]
        bit = bit << 1
    return res
```

## RF Signal Format

```
┌──────────┬──────────────────┬──────────────┬──────────────┬──────────┐
│ Preamble │    Device Code   │   Checksum   │    Action    │ Terminator│
│  8×short │     16 bits      │   4 bits     │   4 bits     │  4×short │
└──────────┴──────────────────┴──────────────┴──────────────┴──────────┘

  short pulse = 60 (= 60 × 10 µs = 600 µs)
  long  pulse = 114 (= 114 × 10 µs = 1140 µs)

  (TellStick protocol: each byte value × 10 µs.
   Source: telldus/telldus docs/02-tellstick-protocol.dox)

  bit "0" = short, short, short, long   (sssl)
  bit "1" = short, long,  short, short  (slss)

  deviceCode = (house << 2) | (unit - 1)    [16 bits, MSB first]
  checksum   = calculateChecksum(deviceCode) [4 bits, MSB first]
  action     = 15 (on), 0 (off), 10 (learn) [4 bits, MSB first]
```

Total signal length: 8 + (16+4+4)×4 + 4 = **108 pulse bytes**

## Cross-Implementation Timing Research (verified 2026-03)

Seven independent implementations produce different pulse timings for the
same Everflourish protocol. This is why we test 263 variants — the "correct"
timing depends on which receiver hardware the user has.

| # | Source | Repository/File | Short (µs) | Long (µs) | Ratio | TellStick byte (s/l) |
|---|--------|-----------------|-----------|-----------|-------|-----|
| 1 | telldus-core | `telldus/telldus-core/service/ProtocolEverflourish.cpp` | 600 | 1140 | 1.9× | 60/114 |
| 2 | tellstick-server | `telldus/tellstick-server ProtocolEverflourish.py` | 600 | 1140 | 1.9× | 60/114 |
| 3 | castoplug PIC18F2550 | `graememorgan/switches-firmware castoplug.c` | 400+940 | 1005+340 | asymmetric | 40/94 |
| 4 | rfcmd forum patch | `forum.telldus.com/viewtopic.php?t=599` | 230 | 690 | 3.0× | 23/69 |
| 5 | perivar Arduino RX | `perivar/everflourish-rf433 everflourish_receiver.ino` | 550-650 | 1000-1360 | ~1.9× | ~60/114 |
| 6 | alexbirkett GNU Radio | `alexbirkett/ever-flourish-remote-control-plug` (USRP N210) | 344 | 975 | 2.8× | 34/98 |
| 7 | Flipper Zero capture | `Zero-Sploit/FlipperZero-Subghz-DB EverFlourish/3_ON.sub` | 324 | 972 | 3.0× | 32/97 |

Additional sources without dedicated everflourish decoders:

| Source | Notes |
|--------|-------|
| RCSwitch (Arduino) | 12 built-in protocol timings (150-650µs base, 1:2 to 1:6 ratios). Everflourish not listed but P1 (350µs) is close to Flipper/GNURadio. |
| Flipper Zero | Uses **Princeton protocol** decoder. `TE: 324` = base timing element. Key=24 bits. |
| ESPHome community | Reports short=350-400µs, long=1800µs (4.5×) from `remote_receiver` captures. |
| pilight/ESPiLight | Protocol file exists but exact path is non-obvious. Manual mentions 420/1260µs base. |
| OpenMQTTGateway | Uses rtl_433_ESP internally; no dedicated everflourish decoder. |
| Tasmota RF Bridge | Uses RCSwitch internally; no dedicated everflourish decoder. Raw capture/replay works. |
| RFLink | No dedicated Everflourish plugin (Plugin_044 is Auriol V3, NOT Everflourish). |
| rtl_433 | No `src/devices/everflourish.c` found in current master. |

### Key insights from the research

1. **Real remotes transmit at ~324-344µs short / ~972-975µs long (ratio 3×)**,
   as confirmed by both Flipper Zero capture and GNU Radio USRP analysis.

2. **telldus-core uses 600/1140µs (ratio 1.9×)** — significantly slower than
   what real remotes produce. This works because everflourish receivers have
   wide timing acceptance windows, but it's not the "correct" timing.

3. **castoplug uses asymmetric OOK** — bit 0 = HIGH 400µs + LOW 940µs,
   bit 1 = HIGH 1005µs + LOW 340µs. This is different from the pulse-quartet
   encoding used by telldus-core. It works because the receiver only checks
   the total bit period (~1340µs per bit).

4. **rfcmd uses 230/690µs (ratio 3×)** — matches the real remote ratio but
   at lower absolute timing. Forum thread t=599 on forum.telldus.com.

5. **Flipper Zero identifies the protocol as Princeton** — a generic OOK
   encoding scheme used by many 433MHz devices (PT2262/EV1527 chipsets).

### Variant organization

Total: **140 RAW + 123 NATIVE = 263 variants**

RAW (S-only pulse bytes — bypass firmware):
- ef_r01-r12: Standard timing (60/114), repeat sweep 1-20×
- ef_r13-r18: Timing sweep (30-90µs short)
- ef_r19-r25: Preamble length sweep (0-16)
- ef_r26-r31: Double/triple signal copies
- ef_r32-r40: Frame/terminator combos
- ef_r41-r43: Inverted bits
- ef_r44-r46: Bit order variations
- ef_r47-r52: Cross timing combos
- ef_r53-r64: **RCSwitch P1-P12 emulation** (verified from RCSwitch.cpp)
- ef_r65-r68: **Castoplug PIC timing** (verified from castoplug.c)
- ef_r69-r72: **rfcmd forum timing** (verified from forum.telldus.com t=599)
- ef_r73-r76: rtl_433 receiver window timing
- ef_r77-r82: Duo T-table format
- ef_r83-r90: Ratio sweep (1.5×-3.0× normal/inverted)
- ef_r91-r98: Absolute level sweep (200-1500µs)
- ef_r99-r103: Sync pulse prefix
- ef_r104-r110: Pause (inter-repeat gap) sweep
- ef_r111-r116: **Flipper Zero Princeton TE=324µs** (verified from capture)
- ef_r117-r120: **GNU Radio 344/975µs** (verified from USRP capture)
- ef_r121-r124: **ESPHome community 350/1800µs** (community reports)
- ef_r125-r127: **Castoplug asymmetric OOK** (verified from castoplug.c)
- ef_r128-r133: Princeton TE sweep (250-500µs)
- ef_r134-r140: Cross-source combos

NATIVE (firmware protocol dicts):
- ef_n01-n07: Model name variations
- ef_n08-n14: Unit offsets (selflearning-switch)
- ef_n15-n21: Unit offsets (selflearning)
- ef_n22-n26: House offsets
- ef_n27-n34: Native+S hybrids
- ef_n35-n42: Native+R/P repeats
- ef_n43-n48: Combo (native+S+R)
- ef_n49-n53: Edge cases (method as string, etc.)
- ef_n54-n65: Native+RCSwitch/alt timing S bytes
- ef_n66-n71: Protocol name/case variations
- ef_n72-n79: Extended unit offsets
- ef_n80-n85: Extended house offsets
- ef_n86-n93: Native+S+varying R/P
- ef_n94-n97: Native+Duo format S
- ef_n98-n103: Method+model combos
- ef_n104-n108: Dict ordering/type variations
- ef_n109-n112: **Native+Flipper Zero S bytes** (verified from capture)
- ef_n113-n115: **Native+GNU Radio S bytes** (verified from USRP capture)
- ef_n116-n117: **Native+ESPHome S bytes** (community reports)
- ef_n118-n119: **Native+Castoplug S bytes** (verified from castoplug.c)
- ef_n120-n123: **Native+Princeton TE sweep S bytes**
