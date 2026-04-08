# RFC: Luxorparts 50969/50970/50972 RF Protocol (rev 3)

**Status:** Draft
**Date:** 2026-04-07
**Author:** R00S
**Source:** RTL-SDR capture via pbkhrv/rtl_433-hass-addons + Telldus Core source (telldus/telldus on GitHub)

---

## 1. Key Findings

- The Luxorparts 50969/50970/50972 does **NOT** use the standard Nexa self-learning
  PPM protocol (`ProtocolNexa::getStringSelflearning`). That produces a 64-bit
  OOK_PPM signal which the 50969 ignores.
- Telldus Live sends a separate **OOK_PPM 25-bit** protocol when the Luxorparts
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
| 14268  | 4    | ON      | 51b1088   | `0101 0001 1011 0001 0000 1000 1`   |
| 14268  | 4    | OFF     | 5bd4b88   | `0101 1011 1101 0100 1011 1000 1`   |

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
14268/4:  0001 1011 0001 0000 1000
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
2. Why do ON and OFF produce completely different house codes? Possibly the 50969
   uses separate learned codes for ON and OFF internally.
3. Is the truncated final 24-bit packet intentional or a ZNet firmware quirk?
4. Does the 50969 respond to ON-only, or does it require both ON and OFF to be
   paired? Observed: only ON (or Learn) teaches the device, OFF alone does not.
5. Are house integers 14466/14468/14268 semantically related or independently
   assigned by Telldus Live per device?

## 10. Recommended Implementation Strategy

Given the encoding algorithm is unknown, the recommended approach for
`tellstick_local` is:

**Capture-and-store:** During device setup, capture the ON and OFF codes directly
from Telldus Live via RTL-SDR (or Telldus API sniffing) and store the raw 25-bit
hex values in the add-on config. Transmit them verbatim using the known PWM
parameters.

This avoids needing to reverse the encoding and is robust against algorithm
variations across firmware versions.

### Current implementation

The integration stores ground-truth codes in `LX_GROUND_TRUTH_CODES` in `const.py`
and sends them as raw pulse data via `tdSendRawCommand` (Duo) or UDP raw bytes
(Net/ZNet). The command format uses R-prefix with P-prefix:
`P\x02 R<n> S<single_packet> +` (56 bytes total). The `P\x02` sets a 2 ms
pause between repeats (close to the natural ~2.25 ms inter-packet gap) and avoids
null bytes which truncate the IPC chain. See `docs/LUXORPARTS_TIMELINE.md` for
the full regression history.
