# ZNet Protocol Porting Guide

> **Purpose:** Step-by-step guide for porting 433 MHz protocols to work on the
> TellStick Net/ZNet backend.  The same pattern that fixed everflourish (issue #85)
> applies to **every non-arctech protocol**.

## Background: Why Protocols Need Raw Pulse Bytes

### Hardware versions and their firmware

There are three TellStick Net hardware products.  They all speak the **same
local UDP protocol** (port 30303 discovery, port 42314 commands/events), but
their send-command handling differs:

| Product           | Discovery name    | Firmware        | Send handling                         |
| ----------------- | ----------------- | --------------- | ------------------------------------- |
| TellStick Net     | `TellStickNet`    | C (`tellsticknet.c`) | Only arctech natively + raw `S` bytes |
| TellStick Net v2  | `TellstickNetV2`  | Python (`tellstick-server`) | Full protocol stack + raw `S` bytes |
| TellStick ZNet    | `TellstickZnet`   | Python (`tellstick-server`) | Full protocol stack + raw `S` bytes |

Source: firmware binary `tellstick-znet-lite-v2-1.3.2.bin` in this repo,
extracted and decompiled from SquashFS rootfs.

### TellStick Net v1 (C firmware)

The original TellStick Net v1 runs a C firmware on a PIC microcontroller.
Source: `telldus/tellstick-net/firmware/tellsticknet.c`.

Its `send()` function has **exactly two code paths**:

```
Path 1:  protocol dict with protocol=arctech AND model=selflearning
         → native sendArctechSelflearning() handler ✅

Path 2:  raw pulse-train bytes via the "S" key
         → direct rfSend() playback ✅

Path 3:  anything else → SILENTLY DROPPED ❌
```

This means **only arctech selflearning on/off/learn** works via native dict.
All other protocols and arctech dim MUST use raw pulse-train bytes.

### TellStick Net v2 / ZNet (Python firmware)

The v2 and ZNet run Linux (OpenWrt) with the `tellstick-server` Python daemon.
The RF chip (connected via USB serial) is driven by the Python `Adapter` class.

The local UDP "send" handler (`productiontest/Server.py :: CommandHandler.handleSend`)
routes through the **full Python protocol stack**:

```python
# From decompiled ZNet v2 firmware (productiontest/Server.py):
@staticmethod
def handleSend(msg):
    protocol = Protocol.protocolInstance(msg['protocol'])
    protocol.setModel(msg['model'])
    protocol.setParameters({'house': msg['house'], 'unit': msg['unit'] + 1})
    msg = protocol.stringForMethod(msg['method'], None)
    CommandHandler.rf433.dev.queue(RF433Msg('S', msg['S'], {}))
```

This means **ALL protocols are theoretically supported** via native dict on
v2/ZNet — `Protocol.protocolInstance()` includes arctech, everflourish, brateck,
comen, fuhaote, hasta, ikea, risingsun, sartano, silvanchip, upm, waveman,
x10, yidong, and kangtai.

**However, the handleSend() has bugs that make native dicts unreliable:**

1. **Unit offset bug**: `msg['unit'] + 1` — the handler adds 1 to unit before
   calling `setParameters()`, but the protocol encoders already handle
   1-indexed unit values internally via `intParameter('unit', 1, N) - 1`.
   This double-offset causes commands to target the wrong unit.

2. **Limited parameter passthrough**: Only `house` and `unit` are passed to
   `setParameters()`.  Protocols that need `code`, `system`, `units`, `fade`,
   or other parameters (sartano, fuhaote, ikea, etc.) will fail silently.

3. **No R/P prefix passthrough**: `handleSend()` always passes `{}` as
   prefixes to `RF433Msg`, ignoring `R` (repeat) and `P` (pause) values
   that some protocols require (e.g. hasta needs R=10, P=25).

### Why raw S bytes is the correct approach for ALL versions

Raw pulse-train bytes (`S` key) work on **every** TellStick Net hardware
version because they bypass all protocol dispatch:

- On **v1**: The C firmware's `rfSend()` plays back the bytes directly
- On **v2/ZNet**: The Python `Adapter.__send()` writes bytes directly to
  the RF chip via serial

This avoids:
- The v1 firmware's arctech-only limitation
- The v2 `handleSend()` unit offset bug
- The v2 `handleSend()` missing parameter passthrough
- Any firmware-specific protocol encoding differences

**IMPORTANT: Raw S bytes via the UDP "send" command have NO proven success on
ZNet.**  When a packet with only an `S` key is received, `handleSend()` crashes
immediately at `Protocol.protocolInstance(msg['protocol'])` because `msg['protocol']`
raises `KeyError`.  When `protocol` and `model` keys are included alongside `S`,
`handleSend()` ignores `S` entirely and re-encodes using the firmware's own protocol
stack (crashing later at `msg['house']` if house/unit are absent, or at
`None / 16` if a DIM level is missing).

The only reliable approach for each version is:
- **v1 (C firmware)**: Native arctech selflearning dict only
- **v2/ZNet (Python firmware)**: Native dict through `handleSend()` (with unit-1
  compensation for the `unit + 1` bug)

## Current Status of Each TX Protocol

| Protocol       | Net/ZNet TX Status | Method Used                                    | Source                                         |
| -------------- | ----------------- | ---------------------------------------------- | ---------------------------------------------- |
| `arctech`      | ✅ Working        | Native dict (on/off/learn); DIM→full brightness via TURNON+selflearning-dimmer model | `tellstick-server/ProtocolArctech.py` |
| `everflourish` | 🔬 Testing²       | Native dict variants (ef_n*); raw S-only variants have no proven success | `tellstick-server/ProtocolEverflourish.py` |
| `brateck`      | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolBrateck.py`          |
| `comen`        | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolComen.py`¹           |
| `fuhaote`      | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolFuhaote.py`          |
| `hasta`        | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolHasta.py`            |
| `ikea`         | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolIkea.py`             |
| `risingsun`    | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolRisingSun.py`        |
| `sartano`      | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolSartano.py`          |
| `silvanchip`   | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolSilvanChip.py`       |
| `upm`          | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolUpm.py`              |
| `waveman`      | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolWaveman.py`¹         |
| `x10`          | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolX10.py`              |
| `yidong`       | ❌ **Needs port** | Falls through to generic dict (BROKEN) | `tellstick-server/ProtocolYidong.py`¹          |

¹ `comen` and `waveman` extend `ProtocolArctech` — they reuse arctech's
  `stringSelflearningForCode()` or `stringForCodeSwitch()`.
  `yidong` extends `ProtocolSartano` — it reuses sartano's `stringForCode()`.

² Everflourish native dict variants (ef_n*) go through the firmware's protocol
  stack and are under active testing.  Raw S-only variants (ef_r*, ef_v1–v4,
  ef_v13–v20) have **no proven success**: `handleSend()` drops packets without
  a `protocol` key.  Hybrid variants (ef_v9–v11, ef_v20) include both a native
  dict and `S` bytes, but `handleSend()` ignores the `S` key and re-encodes
  from the protocol stack regardless.
  See `docs/EVERFLOURISH_RESEARCH.md`.

> **Note:** The Duo backend (telldusd + socat TCP) handles all protocols
> natively — the issue is ONLY with the Net/ZNet UDP backend.

### Arctech dim limitation on ZNet

Variable-level dimming is **not supported** via the ZNet UDP interface.
`handleSend()` always passes `None` as the level to `stringForMethod()`:

```python
msg = protocol.stringForMethod(msg['method'], None)  # level always None
```

For `selflearning-dimmer` + method `TURNON`, the firmware's built-in workaround
applies:
```python
if method == Device.TURNON and self.model == 'selflearning-dimmer':
    return self.stringForSelflearning(Device.DIM, 255)  # full brightness
```

So our integration maps any dim-to-level request to TURNON with
`model="selflearning-dimmer"`, which makes the receiver go to **full brightness**.
The brightness slider in HA moves, but the physical device always goes to 100%
(level 255) for any non-zero brightness value.  TURNOFF (level 0) works correctly.

## How to Port a Protocol — Step by Step

### Step 1: Find the Net/ZNet Firmware Source

Every protocol has a `stringForMethod()` in the `tellstick-server` repo:

```
https://github.com/telldus/tellstick-server/blob/master/rf433/src/rf433/Protocol<Name>.py
```

This function returns `{'S': raw_bytes}` — exactly what we need.

### Step 2: Create the Encoder Function

In `custom_components/tellstick_local/net_client.py`, add a new encoder
function following the everflourish pattern:

```python
# ---------------------------------------------------------------------------
# <Protocol> TX encoding
#
# Ported from tellstick-server Protocol<Name>.stringForMethod():
#   https://github.com/telldus/tellstick-server/blob/master/rf433/src/rf433/Protocol<Name>.py
#
# See docs/ZNET_PROTOCOL_PORTING_GUIDE.md for the porting pattern.
# ---------------------------------------------------------------------------

def _encode_<protocol>_command(
    house: Any, unit: Any, method_name: str
) -> bytes | None:
    """Return raw pulse-train bytes for a <protocol> UDP 'send' command."""
    # ... port stringForMethod() here ...
    # MUST return bytes (the raw S value), NOT a dict
```

### Step 3: Add the Protocol Branch in `_send_rf`

In the `_send_rf` method of `TellStickNetController`, add an `elif` branch:

```python
elif protocol == "<protocol>":
    rf_packet = _encode_<protocol>_command(house, unit, method_name)
    if rf_packet is None:
        _LOGGER.warning("Net <protocol>: unsupported method=%s", method_name)
        return -1
    send_kwargs = dict(S=rf_packet)  # raw pulse-train bytes
```

### Step 4: Mirror to Bundled Copy

**CRITICAL:** The integration exists in TWO copies that must be kept in sync:
- `custom_components/tellstick_local/net_client.py`
- `tellsticklive/rootfs/usr/share/tellstick_local/net_client.py`

### Step 5: Verify with User Testing

The pulse-train encoding is deterministic — if the bytes match the
`tellstick-server` source exactly, it will work.  But RF hardware is
unpredictable, so always confirm with a user who has the actual device.

## Protocol Complexity Tiers

### Tier 1 — Simple (< 50 lines to port)

These have straightforward `stringForMethod()` with no subclasses:

| Protocol     | Lines in source | Parameters    | Notes                              |
| ------------ | --------------- | ------------- | ---------------------------------- |
| `sartano`    | ~15             | code (string) | Static code string → pulse train   |
| `yidong`     | ~10             | unit (1-4)    | Extends sartano's stringForCode()  |
| `fuhaote`    | ~25             | code (string) | 5-bit house + 5-bit unit + on/off  |
| `upm`        | ~35             | house, unit   | 12-bit house + unit + checksum     |
| `brateck`    | ~25             | house (string)| DIP-switch string → pulse train    |

### Tier 2 — Medium (50-100 lines)

| Protocol     | Lines in source | Parameters        | Notes                                  |
| ------------ | --------------- | ----------------- | -------------------------------------- |
| `waveman`    | ~10 (+ arctech) | house, unit       | Reuses arctech codeswitch              |
| `comen`      | ~15 (+ arctech) | house, unit       | Extends arctech selflearning (house shift) |
| `risingsun`  | ~60             | house, unit       | Two models: selflearning + codeswitch  |
| `x10`        | ~60             | house (A-P), unit | Complex bit interleaving + complement  |

### Tier 3 — Complex (100+ lines)

| Protocol     | Lines in source | Parameters           | Notes                                    |
| ------------ | --------------- | -------------------- | ---------------------------------------- |
| `hasta`      | ~80             | house, unit          | Two versions: v1 + v2, each different    |
| `silvanchip` | ~80             | house, unit          | Three models: default, ecosavers, kp100  |
| `ikea`       | ~80             | system, units, level | Koppla dimming with level mapping        |

## Key Differences Between Protocols

### Pulse timing values

Each protocol uses different timing values for its pulses:

| Protocol       | Short | Long  | Encoding style          |
| -------------- | ----- | ----- | ----------------------- |
| `arctech`      | 24    | 127   | 4-pulse per bit         |
| `everflourish` | 60    | 114   | 4-pulse per bit         |
| `sartano`      | `$`/`k` chars¹ | — | Character-based²       |
| `fuhaote`      | 19    | 58    | 4-pulse per bit         |
| `risingsun`    | 51    | 120   | 2-pulse per bit (selflearning) |
| `x10`          | 59    | 169   | 2-pulse per bit + complement |
| `upm`          | `;`   | `~`   | 2-pulse per bit         |
| `hasta` v1     | 17    | 32    | 2-pulse per bit (LSB first) |
| `hasta` v2     | 35    | 66    | 2-pulse per bit (LSB first) |
| `brateck`      | `!`   | `V`   | 4-pulse per bit (DIP switch) |
| `ikea`         | `T`   | chr(170) | 2-pulse per bit + checksum |
| `silvanchip`   | varies | varies | Depends on model        |

¹ Sartano and its derivatives (yidong) use `$` and `k` as pulse-width
  characters, where `$` ≈ chr(36) and `k` ≈ chr(107).

² The Net/ZNet firmware's `rfSend()` treats each byte as a timing value.
  Character-based protocols like sartano use printable ASCII as timing values —
  `$` = 36 (≈594 µs), `k` = 107 (≈1764 µs).

### Repeat and pause parameters

Some protocols require extra `R` (repeat) and `P` (pause) parameters:

```python
# Protocols with custom R/P values:
hasta:       {'S': ..., 'R': 10, 'P': 25}  # v1
hasta_v2:    {'S': ..., 'R': 10, 'P': 0}   # v2
risingsun:   {'S': ..., 'P': 5}             # selflearning
risingsun:   {'S': ..., 'P': 5, 'R': 50}   # learn command

# All others use firmware defaults (R=3 in molobrakos defaults)
```

When encoding, include R and P in the send dict alongside S:

```python
send_kwargs = dict(S=pulse_bytes, R=10, P=25)
```

## Testing a Ported Protocol

1. **Byte-for-byte comparison:** Write a standalone test that replicates the
   `tellstick-server` `stringForMethod()` and compares output byte-by-byte
   (see `docs/EVERFLOURISH_RESEARCH.md` for an example).

2. **Round-trip test:** For protocols with both encode and decode, verify that
   encoding parameters → decoding the expected raw data → same parameters.

3. **User testing:** Ask a user with the actual hardware to test.  The test
   release workflow (`.github/workflows/create-test-release.yaml`) makes this
   easy — create a pre-release, user installs via HACS, tries the device.

## Reference: Net/ZNet Firmware Source Locations

All protocol implementations are in the `telldus/tellstick-server` repo under
`rf433/src/rf433/`:

```
Protocol.py          — Base class with intParameter(), stringParameter()
ProtocolArctech.py   — arctech (parent of comen, waveman)
ProtocolBrateck.py   — brateck
ProtocolComen.py     — comen (extends ProtocolArctech)
ProtocolEverflourish.py — everflourish
ProtocolFuhaote.py   — fuhaote
ProtocolHasta.py     — hasta (v1 + v2)
ProtocolIkea.py      — ikea (Koppla)
ProtocolRisingSun.py — risingsun (selflearning + codeswitch)
ProtocolSartano.py   — sartano (parent of yidong)
ProtocolSilvanChip.py — silvanchip (3 models)
ProtocolUpm.py       — upm
ProtocolWaveman.py   — waveman (extends ProtocolArctech)
ProtocolX10.py       — x10
ProtocolYidong.py    — yidong (extends ProtocolSartano)
```

The critical method in each is `stringForMethod(self, method, data=None)`
which returns `{'S': raw_pulse_bytes}` (sometimes with `R` and `P` keys).
