# Luxorparts 50969 — Consolidated OFF/ON Pair List

All known Luxorparts 25-bit OOK-PWM code pairs, sorted by source.
Each pair consists of an OFF code and an ON code (28-bit hex, i.e. 25-bit value << 3).

**Pairing verified by:** suffix pattern analysis — the last byte of the 28-bit hex
is identical for OFF and ON of the same (house, unit) in all Telldus Live captures.

---

## Telldus Live — Labeled Pairs

Captured from Telldus Live via RTL-433. House/unit labels confirmed.

| #  | House | Unit | OFF         | ON          | Source                  |
|----|-------|------|-------------|-------------|-------------------------|
| 1  | 14466 |  1   | 0x5A59738   | 0x5E14538   | ZNet MQTT plugin        |
| 2  | 14468 |  2   | 0x5CCC0A8   | 0x559DBA8   | ZNet MQTT plugin        |
| 3  | 14268 |  4   | 0x51B1088   | 0x5BD4B88   | ZNet MQTT plugin        |
| 4  | 21900 |  1   | 0x39785F8   | 0x340EBF8   | ZNet MQTT plugin        |
| 5  |   166 |  3   | 0x6DB7638   | 0x6BD1C38   | RTL-433 Homey app       |
| 6  |  2190 |  2   | 0x3E2CDB8   | 0x32128B8   | RTL-433 Homey/Live      |
| 7  | 16634 |  3   | 0x2633638   | 0x2450C38   | RTL-433 Homey app       |
| 8  | 21900 |  3   | 0x3B81638   | 0x3757C38   | RTL-433 Live            |
| 9  | 21900 |  4   | 0x340EBD8   | 0x39785D8   | RTL-433 Live            |
| 10 | 21900 |  5   | 0x3757C18   | 0x3B81618   | RTL-433 Live            |
| 11 | 21901 |  1   | 0x339A5F8   | 0x35A0BF8   | RTL-433 Live            |
| 12 | 29102 |  1   | 0x3C4D5F8   | 0x3034BF8   | RTL-433 Live            |
| 13 | 12639 |  5   | 0x5C548B8   | 0x53F5EB8   | RTL-433 Live            |
| 14 | 12639 |  6   | 0x5AC13E8   | 0x57231E8   | RTL-433 Live            |
| 15 | 12639 |  7   | 0x5BBFF08   | 0x5E8E608   | RTL-433 Live            |
| 16 | 12639 |  8   | 0x5467C48   | 0x51DA248   | RTL-433 Live            |
| 17 | 12639 |  9   | 0x5E8E628   | 0x5BBFF28   | RTL-433 Live            |
| 18 | 12639 | 10   | 0x53F5E98   | 0x5C54898   | RTL-433 Live            |
| 19 | 12639 | 11   | 0x57231C8   | 0x5AC13C8   | RTL-433 Live            |

## Telldus Live — Unlabeled Pairs

Captured from Telldus Live via RTL-433. House/unit not yet identified.
Suffix pattern confirms correct OFF/ON pairing.

| #  | House | Unit | OFF         | ON          | Notes                   |
|----|-------|------|-------------|-------------|-------------------------|
| 20 |   ?   |  ?   | 0x292B638   | 0x23CEC38   | unknown-1               |
| 21 |   ?   |  ?   | 0x25F1638   | 0x21A7C38   | unknown-2               |
| 22 |   ?   |  ?   | 0x289D638   | 0x206CC38   | unknown-3               |
| 23 |   ?   |  ?   | 0x224A638   | 0x2709C38   | unknown-4               |
| 24 | 12639?|  4?  | 0x2FE8638   | 0x2A86C38   | maybe H12639/U4         |

## Physical Remotes — Luxorparts 50969

Captured from two physical Luxorparts 50969 remotes via RTL-433.
Each remote has 4 channels (A-D), each with dedicated OFF and ON buttons.
The remote also transmits Homey proprietary junk codes alongside the
Luxorparts {25}-bit codes — only the {25}-bit codes are listed here.

Remote codes use a different suffix pattern than Live codes (OFF suffix ≠ ON suffix).

### Remote 1 (0xAE... prefix)

| #  | Ch | OFF         | ON          | Notes                   |
|----|----|-------------|-------------|-------------------------|
| 25 | A  | 0xAEBEEB8   | 0xAEBEEA8   |                         |
| 26 | B  | 0xAEBBEA8   | 0xAEBAEB8   |                         |
| 27 | C  | 0xAEBAEA8   | 0xAEAFEB8   |                         |
| 28 | D  | 0xAEAFEA8   | ???         | ON not captured         |

### Remote 2 (0xAF... prefix)

| #  | Ch | OFF         | ON          | Notes                   |
|----|----|-------------|-------------|-------------------------|
| 29 | A  | 0xAFBEEB8   | 0xAFBEEA8   |                         |
| 30 | B  | 0xAFBBEB8   | 0xAFBBEA8   |                         |
| 31 | C  | 0xAFBAEB8   | 0xAFBAEA8   |                         |
| 32 | D  | 0xAFAFEB8   | 0xAFAFEA8   |                         |

---

## Summary

| Source          | Labeled pairs | Unlabeled pairs | Total |
|-----------------|---------------|-----------------|-------|
| Telldus Live    | 19            | 5               | 24    |
| Physical remote | 0             | 8 (1 partial)   | 8     |
| **Total**       | **19**        | **13**          | **32**|

## Removed Pairs

- **(14242, 2)**: Removed — single unreliable pair, source uncertain.
