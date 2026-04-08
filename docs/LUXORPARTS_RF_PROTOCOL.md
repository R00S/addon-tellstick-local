# RFC: Luxorparts 50969/50970/50972 RF Protocol (rev 4)

**Status:** Working — ON/OFF verified on hardware (2026-04-08)
**Date:** 2026-04-08
**Author:** R00S
**Source:** RTL-SDR capture via pbkhrv/rtl_433-hass-addons + Telldus Core source (telldus/telldus on GitHub)

---

## 1. Key Findings

- The Luxorparts 50969/50970/50972 does **NOT** use the standard Nexa self-learning
  PPM protocol (`ProtocolNexa::getStringSelflearning`). That produces a 64-bit
  OOK_PPM signal which the 50969 ignores.
- Telldus Live sends a separate **OOK_PWM 25-bit** protocol when the Luxorparts
  device type is selected.
- This protocol is not ProtocolNexa, ProtocolSilvanChip, or any other identified
  Telldus Core open-source protocol.
- ON and OFF commands produce **completely different payloads** — this is not a
  single bit flip.
- The encoding algorithm mapping Telldus house/unit integers to the 25-bit payload
  is **proprietary and not yet reversed**.

## 2. Physical Layer

| Parameter            | Value       |
| -------------------- | ----------- |
| Frequency            | 433.92 MHz  |
| Modulation           | OOK PWM     |
| Short pulse (bit 1)  | 392 µs      |
| Long pulse (bit 0)   | 1148 µs     |
| Short gap            | 352 µs      |
| Long gap             | 1108 µs     |
| Period               | ~1500 µs (constant) |
| Inter-packet gap     | 2252 µs     |

## 3. Symbol Encoding

| Symbol | Pulse    | Gap      |
| ------ | -------- | -------- |
| 1      | 392 µs   | 1108 µs  |
| 0      | 1148 µs  | 352 µs   |

Pulse width varies. Bit value is encoded in pulse width (PWM).
Period is constant at ~1500 µs (pulse + gap always sums to ~1500 µs).

## 4. Packet Structure

Total bits: **25**

- Fixed preamble (bits 0–3): always `0101`
- Variable payload (bits 4–23): 20 bits encoding house + unit + command
- Fixed suffix (bit 24): always `1`

```
[ 0101 ][ 20 variable bits ][ 1 ]
  bits    bits 4–23           bit
  0–3                         24
```

## 5. Burst Structure

| Burst type         | Repetitions  | Duration    |
| ------------------ | ------------ | ----------- |
| Learn / first send | 48 packets   | ~1858 ms    |
| Normal ON/OFF      | 10 packets   | ~386 ms     |
| Post-burst gap     | —            | ~11564 µs   |

The final packet in each burst is consistently truncated to 24 bits. This appears
intentional.

## 6. Observed Codes (Ground Truth)

All codes confirmed via RTL-SDR capture with matching Telldus Live house/unit settings.

| House  | Unit | Command | Hex       | Binary (25 bits)                    |
| ------ | ---- | ------- | --------- | ----------------------------------- |
| 14466  | 1    | ON      | 5e14538   | `0101 1110 0001 0100 0101 0011 1`   |
| 14466  | 1    | OFF     | 5a59738   | `0101 1010 0101 1001 0111 0011 1`   |
| 14468  | 2    | ON      | 559dba8   | `0101 0101 1001 1101 1011 1010 1`   |
| 14468  | 2    | OFF     | 5ccc0a8   | `0101 1100 1100 1100 0000 1010 1`   |
| 14268  | 4    | ON      | 5bd4b88   | `0101 1011 1101 0100 1011 1000 1`   |
| 14268  | 4    | OFF     | 51b1088   | `0101 0001 1011 0001 0000 1000 1`   |

## 7. Bit-level Analysis

### 7.1 Fixed bits

- Bits 0–3: always `0101` — preamble, never changes
- Bit 24: always `1` — suffix, never changes

### 7.2 ON vs OFF XOR per house/unit pair

The XOR between ON and OFF for the same device is spread across all 20 variable
bits — confirming ON/OFF is not a single bit flip:

```
14466/1:  ON  XOR OFF = 0000 0100 0100 1101 0010 0000 0
14468/2:  ON  XOR OFF = 0000 1001 0101 0001 1011 0000 0
14268/4:  ON  XOR OFF = 0000 1010 0110 0101 1011 0000 0
```

### 7.3 Variable payload bits 4–23 (ON codes only)

```
14466/1:  1110 0001 0100 0101 0011
14468/2:  0101 1001 1101 1011 1010
14268/4:  1011 1101 0100 1011 1000
```

### 7.4 Encoding algorithm status

The mapping from Telldus house integer + unit integer to the 20-bit variable payload
is **unknown**. Attempts to match against:

- `ProtocolNexa::getStringSelflearning` — no match
- `ProtocolSilvanChip::getString` (20-bit house) — no match
- Simple bit-split of house integer — no match

## 8. rtl_433 Flex Decoder

For sniffing/verification only:

```
-X 'n=Luxorparts,m=OOK_PWM,s=392,l=1148,r=2260,g=1132,t=302,y=0'
```

## 9. Open Questions

1. What is the encoding algorithm mapping house+unit+command → 20-bit payload?
   Likely in closed-source Telldus Live backend or ZNet firmware.
   **Not blocking:** We generate our own codes since receivers learn any valid signal.
2. Why do ON and OFF produce completely different house codes? Possibly the 50969
   uses separate learned codes for ON and OFF internally.
3. Is the truncated final 24-bit packet intentional or a ZNet firmware quirk?
4. ~~Does the 50969 respond to ON-only, or does it require both ON and OFF to be
   paired?~~ **Answered:** The receiver learns ON and OFF codes independently.
   Teaching is done by sending the ON code while the receiver is in learn mode.
5. ~~Are house integers 14466/14468/14268 semantically related or independently
   assigned by Telldus Live per device?~~ **Not relevant:** We generate our own
   codes — we don't need Telldus Live's encoding scheme.
6. **NEW:** Why does the TellStick Duo refuse to flash when R-prefix repeat count
   is 50 (learn) but works fine with 10 (on/off)? Possible firmware threshold.

## 10. Recommended Implementation Strategy

### Current implementation (working as of v3.1.8.15)

**Hash-based code generation:** The integration generates unique ON/OFF code pairs
from a `(house, unit)` tuple using a deterministic hash. This avoids needing to
reverse Telldus Live's proprietary encoding algorithm.

Each `(house, unit)` pair maps to a unique 25-bit ON code and a unique 25-bit OFF
code. The codes follow the Luxorparts packet structure:
```
[0101][20 variable bits][1]
 ^^^^                    ^
 fixed preamble          fixed suffix
```

The 20 variable bits are derived from a CRC32 hash of `(house, unit, command)`.
Different `(house, unit)` pairs always produce different codes. The receiver
doesn't care about the structure of the variable bits — it memorizes whatever
code it hears during learn mode.

**Ground truth codes** from Telldus Live captures are also stored for reference
and backward compatibility. If a user happens to use the exact Telldus Live
house/unit values, the captured codes are used instead (these were verified to
work on real hardware).

### Learning workflow (user-facing)

1. User adds a Luxorparts device in HA (picks house code + unit, or uses defaults)
2. User puts the Luxorparts receiver in learn mode (hold button until LED flashes)
3. User presses **ON** in HA → Duo transmits the ON code (10 repeats)
4. Receiver learns the code → LED stops flashing
5. ON and OFF now work from HA

**Note:** The dedicated learn command (50 repeats) does not work yet because the
TellStick Duo does not flash when R-prefix repeat count is 50. Using ON (10
repeats) as a workaround is sufficient — the receiver learns from any valid
transmission of the code.

### Transmission format

The integration sends raw pulse data via `tdSendRawCommand` (Duo) or UDP raw
bytes (Net/ZNet). The command format uses R-prefix with P-prefix:
`P\x02 R<n> S<single_packet> +` (56 bytes total). The `P\x02` sets a 2 ms
pause between repeats (close to the natural ~2.25 ms inter-packet gap) and avoids
null bytes which truncate the IPC chain. See `docs/LUXORPARTS_TIMELINE.md` for
the full regression history.
