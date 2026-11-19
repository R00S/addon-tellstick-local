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

Decrypting the recorded LPD 7 pair with the Homey cipher shows the record layout,
and it is why the current build looks the way it does:

```
ON  0x2450C38 -> plaintext  D5 10 86     (address 0xD510, ctrl 0x86)
OFF 0x2633638 -> plaintext  D5 B1 46     (address 0xD5B1, ctrl 0x46)
```

The two halves carry **different addresses**, and the OFF's control byte is the
ON's with bit 6 set — bit 6 is the state bit (0 = ON, 1 = OFF). The first
generated build replaced the OFF's address with the ON's own and lost every OFF;
the current build keeps both addresses and varies only the unit. Its codes are in
the **v4** section at the end of this file.

A **second** test device (widget 22, "Luxorparts — Test device v1, seeds +1..5",
removed in v3.4.0.12)
restores the first generated build unchanged, so both can be taught to one
receiver in the same session. Its pairs are the old `LPD 7 seeds +1…5` on houses
111–115, plus a control on 116 that replays LPD 7 again:

| Switch | ON | OFF |
|--------|----|-----|
| LX-B1 v1 | 0x2450C48 | 0x2633648 |
| LX-B2 v1 | 0x2450C58 | 0x2633658 |
| LX-B3 v1 | 0x2450C68 | 0x2633668 |
| LX-B4 v1 | 0x2450C78 | 0x2633678 |
| LX-B5 v1 | 0x2450C88 | 0x2633688 |
| CONTROL v1 | 0x2450C38 | 0x2633638 |

They are the build whose decoded state bit explained the whole protocol, and they
stay as the reference — not as a way to create devices.

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
the two halves of a pair decoded to different devices.

The table above is the plaintext-pair build, and it is the third OFF failure:
**all five ONs turned their socket on, no OFF worked, five of five.** The v1 group
beside it (LPD 7 seeds +1…5) split three ways — B3 and B4 worked both ways, B1 and
B5 ran **reversed** (the receiver read our ON as an OFF) and B2 was **refused** and
only works once B1 is taught. Both controls (the recorded LPD 7 pair) work both
ways. So the receiver both decodes and validates the frame, and neither a fresh
address nor an offset of a recorded one produces a usable OFF.

Decrypting the whole recorded list adds three facts that constrain the rule:

* payload bits 0–4 **never** change between the two halves of a recorded pair —
  that is the unit field, and it is shared;
* bits 5–7 and bits 8–23 change in every pair: 19 distinct `ON ^ OFF` masks over
  24 pairs, so there is no single state bit anywhere in the 24-bit payload;
* for the seven pairs that share the unit-6 control bytes (LPD 5, 7, 20–24) the
  OFF control byte is always exactly `ON ^ 0xC0` (`0x86` → `0x46`) and the only
  other difference is the **address**.

### v4 — new units on the recorded address pair (removed in v3.4.0.12)

Device type **"Luxorparts — Test device, 5 switches (beta, Duo only)"** (widget 21,
houses 101–106). The v3 group (recorded ON + OFF rebuilt at that same address) was
tested on 2026-11-19 and is gone: **all five ONs worked, no OFF did** — the fourth
build in a row to fail that way.

v1 is still the only build that ever produced pairs with **both** commands
working, so its five codes are where the answer is. Decrypting them:

| Switch | ON ctrl | OFF ctrl | `ctrl >> 6` ON / OFF | Reported |
| --- | --- | --- | --- | --- |
| LPD 7 (control) | `0x86` | `0x46` | `10` / `01` | correct |
| B1 | `0x6C` | `0xAC` | `01` / `10` | reversed |
| B2 | `0x4A` | `0x8A` | `01` / `10` | reversed, refused |
| B3 | `0x2B` | `0xEB` | `00` / `11` | correct |
| B4 | `0x09` | `0xC9` | `00` / `11` | correct |
| B5 | `0xD8` | `0xA8` | `11` / `10` | reversed |

**Bit 6 of the control byte is the state bit: 0 = ON, 1 = OFF.** The three
reversed switches are exactly the three whose ON half has bit 6 = 1, i.e. whose
ON press is an OFF frame. Bit 7 is a don't-care. That is why v1 "worked" for some
switches only: the offset added to the ciphertext walked bits through the state
field.

It also explains why no address build ever worked. The recorded pair keeps **two**
addresses — `0xD510` for ON, `0xD5B1` for OFF — and v1 kept both, because it
offsets two recorded ciphertexts. The plaintext-pair build and v3 replaced the
OFF's address with the ON's, and then no OFF could match what the receiver derives.

So a generated device is grown the way B3/B4 already proved: keep the recorded
pair's two addresses and control patterns, and vary only the 5-bit unit.

```
ON  = encrypt(D5, 0x10, 0x80 | unit)     # bit 7 set, bit 6 clear -> ON half
OFF = encrypt(D5, 0xB1, 0x40 | unit)     # bit 6 set             -> OFF half
```

| Switch | Unit | ON | OFF |
|--------|------|----|-----|
| LX-B1 | 9 | `0x23472F8` | `0x2024EF8` |
| LX-B2 | 11 | `0x2021F68` | `0x2109FE8` |
| LX-B3 | 7 | `0x223BB28` | `0x20E8028` |
| LX-B4 | 8 | `0x25FC788` | `0x27E4708` |
| LX-B5 | 10 | `0x210CE58` | `0x2297C58` |
| CONTROL ON/OFF | 6 | `0x2450C38` | `0x2633638` |

Unit 6 reproduces the recorded LPD 7 pair byte for byte, which is the check that
both halves are one device. Units 9 and 11 are B4's and B3's units from the v1
build — the two switches that worked — so the group carries its own control at the
unit level; 7, 8 and 10 have never been at a receiver.

Sixteen of the 32 unit values are unusable: their frames would not have payload
bit 0 set, and bit 0 = 1 is the one bit fixed in all 62 captured codes
(`LUXORPARTS_PROTOCOL_ANALYSIS.md` §2). The skipped units are 0–5, 13, 15–21, 29
and 31.

### v5 — v1 with the channel bit held (removed in v3.4.0.12)

Device type **"Luxorparts — Test device v5, corrected shifts (beta, Duo only)"**
(widget 24, houses 131–136). v1 is the only build whose OFF ever worked, and the
reason is now pinned down:

* a v1 code is a **recorded pair shifted by `+2·offset`** in the 24-bit payload;
  the cipher's nibble chain runs from the payload's least-significant nibble
  upwards, so only the control byte changes — both recorded addresses stay put;
* the payload's low five bits are the **channel field**, shared by the two halves
  of every recorded pair;
* channel bit 2 (`0x04`) selects which of the two frames is the ON: five recorded
  pairs are siblings that are the same frames with that bit flipped and the roles
  swapped (LPD 4/9, 8/10, 13/18, 14/19, 15/17).

v1's offsets walked that bit. `+3` (`0x0D`) and `+4` (`0x0F`) kept it and worked;
`+1` (`0x09`), `+2` (`0x0B`) and `+5` (`0x11`) cleared it and ran reversed, and
`+5` also carried into bit 5, which is why that one was flawed as well.

| Switch | Pair | Channel | ON | OFF |
|--------|------|---------|----|-----|
| LX-B1 v5 | LPD 7 +3 | `0x0D` | `0x2450C68` | `0x2633668` |
| LX-B2 v5 | LPD 7 +4 | `0x0F` | `0x2450C78` | `0x2633678` |
| LX-B3 v5 | LPD 5 −1 | `0x05` | `0x6BD1C28` | `0x6DB7628` |
| LX-B4 v5 | LPD 13 −1 | `0x15` | `0x53F5EA8` | `0x5C548A8` |
| LX-B5 v5 | LPD 6 +4 | `0x1F` | `0x32128F8` | `0x3E2CDF8` |
| CONTROL v5 | LPD 7 | `0x07` | `0x2450C38` | `0x2633638` |

B1 and B2 are v1's two working pairs, shipped again as the reference; B3…B5 apply
the same rule to other recordings so the five switches cannot be variants of one
pair. Nothing in the encrypted part of the frame is invented — the one thing every
build after v1 got wrong.

**Hardware result (2026-11-19, v3.4.0.10):** only v4's B1 and B3 learned and turned
on (no OFF on either); B2, B4 and B5 could not learn at all; the control worked.

### v3.4.0.12 — the generated pool replaces the test devices

The four test-device types (widgets 21, 22 and 24, and their catalog entries) are
**removed**. Their job is done: v5 was built with the rule in
`LUXORPARTS_PROTOCOL_ANALYSIS.md` §7b and worked **5 of 5** on a 50969, so the rule
now ships as a generator instead of as five switches.

Device type **"Luxorparts — Generated channel, 304 codes (experimental)"**
(widget 25) takes **house = LPD number 1–24** and **unit = channel 1–16**:

```
channel field values: 0x01, 0x03, 0x05 … 0x1F  (unit 1 … 16)
on  = (recorded_on  & ~0xF8) | (channel << 3)
off = (recorded_off & ~0xF8) | (channel << 3)
if (channel ^ recorded_channel) & 0x04:          # bit 2 picks the ON frame
    on, off = off, on
```

The 24 recordings are **19 families** — five are the same receiver twice (LPD 4/9,
8/10, 13/18, 14/19, 15/17) and are canonicalised to the first entry — so the pool is
**19 × 16 = 304 device codes**: 24 are the recordings themselves and 280
were never recorded.

| Base LPD | Sibling | Recorded channel | bit 2 | ON at channel 4 | OFF at channel 4 |
| --- | --- | --- | --- | --- | --- |
| 1 | — | `0x07` | 1 | `0x5E14538` | `0x5A59738` |
| 2 | — | `0x15` | 1 | `0x559DB38` | `0x5CCC038` |
| 3 | — | `0x11` | 0 | `0x51B1038` | `0x5BD4B38` |
| 4 | 9 | `0x1F` | 1 | `0x340EB38` | `0x3978538` |
| 5 | — | `0x07` | 1 | `0x6BD1C38` | `0x6DB7638` |
| 6 | — | `0x17` | 1 | `0x3212838` | `0x3E2CD38` |
| 7 | — | `0x07` | 1 | `0x2450C38` | `0x2633638` |
| 8 | 10 | `0x07` | 1 | `0x3757C38` | `0x3B81638` |
| 11 | — | `0x1F` | 1 | `0x35A0B38` | `0x339A538` |
| 12 | — | `0x1F` | 1 | `0x3034B38` | `0x3C4D538` |
| 13 | 18 | `0x17` | 1 | `0x53F5E38` | `0x5C54838` |
| 14 | 19 | `0x1D` | 1 | `0x5723138` | `0x5AC1338` |
| 15 | 17 | `0x01` | 0 | `0x5BBFF38` | `0x5E8E638` |
| 16 | — | `0x09` | 0 | `0x5467C38` | `0x51DA238` |
| 20 | — | `0x07` | 1 | `0x23CEC38` | `0x292B638` |
| 21 | — | `0x07` | 1 | `0x21A7C38` | `0x25F1638` |
| 22 | — | `0x07` | 1 | `0x206CC38` | `0x289D638` |
| 23 | — | `0x07` | 1 | `0x2709C38` | `0x224A638` |
| 24 | — | `0x07` | 1 | `0x2A86C38` | `0x2FE8638` |

Channel 4 was used as the sample column because it is the field value
(`0x07`) that most recordings use, so those rows reproduce recorded codes
where the recording itself sits on channel 4.

Why this is believed to work, and what has actually been to a receiver: the 24
recordings, plus the five v5 channels (LPD 7 channel 7 = `0x2450C68`/`0x2633668`,
channel 8 = `0x2450C78`/`0x2633678`, LPD 5 channel 3, LPD 13 channel 11, LPD 6
channel 16). Those five **learned and switched both ways**. Channel 4 of a family is
its own recording, so it returns the recorded pair unchanged.

The learn button and "no pairing signal on add" behaviour are unchanged: a receiver
learns the code it hears, so pair a generated channel by pressing its **on** button.
