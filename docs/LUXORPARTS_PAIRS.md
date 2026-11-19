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

Plus five **generated** test pairs (picker 101–105) that are not recordings — see
the section above.

## Generated test pairs (never captured)

Not recorded codes: built with scheme A from
`docs/LUXORPARTS_PROTOCOL_ANALYSIS.md` §6 (remote template `0x5D55D5`, bit 1 =
state, frame MSB 1). Offered in the Duo flow as "Luxorparts — Generated test
codes" (picker 101–105, LX-T1…LX-T5). None of these ten codes appears in any
capture, so a receiver that learns one accepts a generated code.

| Pick | Button field | ON | OFF |
|------|--------------|----|-----|
| 101 (LX-T1) | bit 9 | 0xAEABEA8 | 0xAEABEB8 |
| 102 (LX-T2) | bit 11 | 0xAEAEEA8 | 0xAEAEEB8 |
| 103 (LX-T3) | bits 9+11+13 | 0xAEBFEA8 | 0xAEBFEB8 |
| 104 (LX-T4) | none | 0xAEAAEA8 | 0xAEAAEB8 |
| 105 (LX-T5) | bit 9 + remote 2 | 0xAFABEA8 | 0xAFABEB8 |

---

## Excluded

- **Remote 1 ch D**: ON code not captured → excluded (no complete pair)
- **H14242/U2**: Removed — single unreliable pair, source uncertain
