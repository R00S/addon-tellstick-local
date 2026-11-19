# Luxorparts 50969 — LPD Code List

All known Luxorparts 25-bit OOK-PWM code pairs with both ON and OFF codes.
Each pair is assigned a stable **LPD** (Luxorparts Device) number for testing.

Remote 1 channels B and D are incomplete (B's OFF code and D's ON code were not
captured) — see the warning under the table.

Codes are 28-bit hex values (25-bit code << 3).
Internally, LPD number is the lookup key (house=LPD, unit=1).

---

## All LPD Codes

| LPD | Source | Original ID      | ON          | OFF         |
|-----|--------|------------------|-------------|-------------|
|  1  | Live   | H14466/U1        | 0x5E14538   | 0x5A59738   |
|  2  | Live   | H14468/U2        | 0x559DBA8   | 0x5CCC0A8   |
|  3  | Live   | H14268/U4        | 0x5BD4B88   | 0x51B1088   |
|  4  | Live   | H21900/U1        | 0x340EBF8   | 0x39785F8   |
|  5  | Live   | H166/U3          | 0x6BD1C38   | 0x6DB7638   |
|  6  | Live   | H2190/U2         | 0x32128B8   | 0x3E2CDB8   |
|  7  | Live   | H16634/U3        | 0x2450C38   | 0x2633638   |
|  8  | Live   | H21900/U3        | 0x3757C38   | 0x3B81638   |
|  9  | Live   | H21900/U4        | 0x39785D8   | 0x340EBD8   |
| 10  | Live   | H21900/U5        | 0x3B81618   | 0x3757C18   |
| 11  | Live   | H21901/U1        | 0x35A0BF8   | 0x339A5F8   |
| 12  | Live   | H29102/U1        | 0x3034BF8   | 0x3C4D5F8   |
| 13  | Live   | H12639/U5        | 0x53F5EB8   | 0x5C548B8   |
| 14  | Live   | H12639/U6        | 0x57231E8   | 0x5AC13E8   |
| 15  | Live   | H12639/U7        | 0x5E8E608   | 0x5BBFF08   |
| 16  | Live   | H12639/U8        | 0x51DA248   | 0x5467C48   |
| 17  | Live   | H12639/U9        | 0x5BBFF28   | 0x5E8E628   |
| 18  | Live   | H12639/U10       | 0x5C54898   | 0x53F5E98   |
| 19  | Live   | H12639/U11       | 0x5AC13C8   | 0x57231C8   |
| 20  | Live   | unknown          | 0x23CEC38   | 0x292B638   |
| 21  | Live   | unknown          | 0x21A7C38   | 0x25F1638   |
| 22  | Live   | unknown          | 0x206CC38   | 0x289D638   |
| 23  | Live   | unknown          | 0x2709C38   | 0x224A638   |
| 24  | Live   | maybe H12639/U4  | 0x2A86C38   | 0x2FE8638   |
| 25  | Remote | R1-A             | 0xAEBEEA8   | 0xAEBEEB8   |
| 26  | Remote | R1-B             | 0xAEBAEB8   | 0xAEBBEA8   |
| 27  | Remote | R1-C             | 0xAEAFEB8   | 0xAEBAEA8   |
| 28  | Remote | R2-A             | 0xAFBEEA8   | 0xAFBEEB8   |
| 29  | Remote | R2-B             | 0xAFBBEA8   | 0xAFBBEB8   |
| 30  | Remote | R2-C             | 0xAFBAEA8   | 0xAFBAEB8   |
| 31  | Remote | R2-D             | 0xAFAFEA8   | 0xAFAFEB8   |

> ⚠️ **LPD 26 and 27 are cross-assembled.** Each row carries one ON and one OFF
> code from *different* buttons, so the ON entries are really OFF codes and vice
> versa. The four captures are field `0x2000` ON/OFF
> (`0xAEBAEA8`/`0xAEBAEB8`), field `0x2200` ON (`0xAEBBEA8`) and field `0x0A00`
> OFF (`0xAEAFEB8`); B's OFF and D's ON were never captured. See
> `docs/LUXORPARTS_PROTOCOL_ANALYSIS.md` §3.1. LPD 25–31 are documentation only —
> the picker ships LPD 1–24.

---

## Summary

| Source          | LPD range | Count |
|-----------------|-----------|-------|
| Telldus Live    | 1–24      | 24    |
| Physical remote | 25–31     | 7     |
| **Total**       | **1–31**  | **31**|

Plus five **generated** test pairs (houses 101–105 on the test device) that are
not recordings — see the section below.

## Generated test pairs (never captured)

Not recorded codes, with one recorded control. The test device adds one Home
Assistant device with six switches: five **generated** pairs and a
**CONTROL ON/OFF** that replays the recorded LPD 7 pair.

Each generated pair is **one plaintext record, encrypted twice**.  Decrypting the
recorded LPD 7 pair with the Homey cipher shows the record layout:

```
ON  0x2450C38 -> plaintext  D5 10 86     (address 0xD510, ctrl 0x86)
OFF 0x2633638 -> plaintext  D5 B1 46     (address 0xD5B1, ctrl 0x46)
```

The address and unit stay fixed per switch and only the control byte changes, so
ON and OFF describe one device — the shape a receiver needs, because it derives
the OFF from the ON it learned.  Every switch uses the recorded pair's own
control bytes (`0x86` / `0x46`, unit 6) and a fresh address, which is why
`_lx_plain_pair(0xD510)` reproduces the recorded ON code byte for byte.

A **second** test device (widget 22, "Luxorparts — Test device v1, seeds +1..5")
restores the first build unchanged, so both can be taught to one receiver in the
same session. Its pairs are the old `LPD 7 seeds +1…5` on houses 111–115, plus a
control on 116 that replays LPD 7 again:

| Switch | ON | OFF |
|--------|----|-----|
| LX-B1 v1 | 0x2450C48 | 0x2633648 |
| LX-B2 v1 | 0x2450C58 | 0x2633658 |
| LX-B3 v1 | 0x2450C68 | 0x2633668 |
| LX-B4 v1 | 0x2450C78 | 0x2633678 |
| LX-B5 v1 | 0x2450C88 | 0x2633688 |
| CONTROL v1 | 0x2450C38 | 0x2633638 |

They are a diagnostic, not a way to create devices.

| Switch | Address | ON | OFF |
|--------|---------|----|-----|
| LX-B1 | 0xD601 | 0x21C7C38 | 0x203B638 |
| LX-B2 | 0xD602 | 0x26EDC38 | 0x25E1E38 |
| LX-B3 | 0xD603 | 0x2536C38 | 0x228C638 |
| LX-B4 | 0xD604 | 0x27FCC38 | 0x2380E38 |
| LX-B5 | 0xD605 | 0x203B438 | 0x21C7E38 |
| CONTROL | LPD 7 | 0x2450C38 | 0x2633638 |

No pairing signal is sent when the device is added and the switches have no Learn
button; pair a switch by pressing its **on** button with the receiver in learn
mode.

**Hardware results (2026-11-19):** scheme A (five remote-family clones,
LX-T1…LX-T5, `0xAEABEA8`…`0xAFABEB8`) was **refused outright** and is removed
from the code. Scheme B **is accepted**: the control and all five generated pairs
were learned. A first build used seed offsets 1–5 (payload bits 1–3) and several
switches then controlled the same socket with on/off reversed — the receiver
**decodes** the payload, and those low bits are state/unit, not address. A second
build moved the seed in the address bits: all five **ON** commands worked, but **no
OFF** did — an offset added to a stored payload is applied after the cipher, so
the two halves of a pair decoded to different devices. The table above is the
current build: one plaintext record per switch, encrypted twice.

---

## Excluded

- **Remote 1 ch D**: ON code not captured → excluded (no complete pair)
- **H14242/U2**: Removed — single unreliable pair, source uncertain
