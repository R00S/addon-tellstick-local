# Everflourish Protocol — Research & Implementation Notes

> **Issue:** [#85](https://github.com/R00S/addon-tellstick-local/issues/85) —
> GAO (everflourish) protocol works on TellStick Duo but not on TellStick ZNet.

> **⚠️ Status (2026-03):** ZNet testing showed that the raw S-only encoder
> (v1) produces **no blinking**, while the native firmware path produces
> **blinking** (both with and without unit-1 fix).  This means `handleSend()`
> on ZNet v2 **requires the `protocol` key** — S-only dicts are silently
> dropped.  12 encoding variants (EF raw v1–v12) are now available in the
> "by protocol (raw)" menu to empirically test which approach works on
> each hardware version.  Cross-TellStick RX still untested — Duo-generated
> everflourish signals are not picked up by Net/ZNet as a receiver.
>
> **Test variants (in "by protocol (raw)" menu):**
>
> | Variant | Dict keys sent | Hypothesis |
> |---------|---------------|------------|
> | v1 | `{S}` | Current S-only — fails on ZNet v2 |
> | v2 | `{S, R=4}` | S + repeat prefix |
> | v3 | `{S, R=10, P=5}` | S + repeat + pause (like internal path) |
> | v4 | `{S+S}` | Doubled signal |
> | v5 | `{protocol, model=sw, house, unit, method}` | Native, no unit fix |
> | v6 | `{protocol, model=sw, house, unit-1, method}` | Native, unit-1 fix |
> | v7 | `{protocol, model=sl, house, unit, method}` | Native, model="selflearning" |
> | v8 | `{protocol, model=sl, house, unit-1, method}` | Native, model="selflearning" + fix |
> | v9 | `{protocol, model=sw, …, S}` | Hybrid, no fix |
> | v10 | `{protocol, model=sw, …, S}` unit-1 | Hybrid, fix |
> | v11 | `{protocol, model=sw, …, S, R, P}` | Hybrid + R+P |
> | v12 | `{protocol, model=sl, house, unit-2, method}` | Native, unit-2 fix |

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

  short pulse = 60 (≈988 µs timing value)
  long  pulse = 114 (≈1878 µs timing value)

  bit "0" = short, short, short, long   (sssl)
  bit "1" = short, long,  short, short  (slss)

  deviceCode = (house << 2) | (unit - 1)    [16 bits, MSB first]
  checksum   = calculateChecksum(deviceCode) [4 bits, MSB first]
  action     = 15 (on), 0 (off), 10 (learn) [4 bits, MSB first]
```

Total signal length: 8 + (16+4+4)×4 + 4 = **108 pulse bytes**
