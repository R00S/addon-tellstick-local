# Luxorparts / Cleverio 25-bit protocol — code structure analysis

**Status:** Analysis of existing RTL-433 captures, no new hardware
**Date:** 2026-11-19
**Data:** `LX_LPD_LIST` (24 Telldus Live device pairs, 48 codes) in
`custom_components/tellstick_local/const.py`, the seven physical-remote pairs in
`docs/LUXORPARTS_PAIRS.md` (LPD 25–31), and the raw analyzer dumps in `sniffed luxorparts`
— 62 captured codes in total.
**Hardware status:** the project owner reports that **all 24 recorded LPD pairs work
on the Duo path** (2026-11-19). That confirms the replay path and the whole LPD list;
it does not test a generated code.
**Supersedes:** the encoding claims in §7.4 and §10 of `docs/LUXORPARTS_RF_PROTOCOL.md`.

The question this answers: *can we generate new codes, instead of only replaying
recorded ones?* **Revised answer (rev 2, after review): not yet established.**

The frame structure is now mapped, and a candidate generation scheme exists, but the
earlier optimistic claim ("nothing to reverse-engineer; any payload will do")
did not survive scrutiny: the Live captures contain an unexplained 1-bit field, the
house/unit labels do not map one-to-one onto devices, and **no generated code has
ever been tested on hardware**. Sections §3.3, §5 and §6 carry the corrections.

The parts that are arithmetic on the captures — timings, bit count, the remote-family
template, the seed round-trip — stand. The conclusions drawn from them have been
narrowed to what the data supports.

---

## 1. Notation

Codes are stored as 28-bit integers because the encoder works on a 25-bit frame
followed by three padding zeros:

```
stored28 = frame25 << 3
payload24 = stored28 >> 3 & 0xFFFFFF      # the 24 bits below the frame's MSB
```

All bit numbers below are positions in `payload24`, bit 0 = least significant.

## 2. Frame shape

| Property | Value | Evidence |
| --- | --- | --- |
| Bits in the air | 25 | rtl_433 `{25}…`, nine full packets plus a 24-bit truncated one per burst |
| Payload bit 0 | **always 1** | 62/62 captured codes |
| Fixed preamble | **none** | old "`0101` preamble" claim holds only for 6 of 62 codes (the first six captures) |
| Frame MSB | varies | `0` for the Live family, `1` for the remote family |
| Checksum / parity | **none found** | only invariant across all 62 codes is payload bit 0 |

The "start bit 0 + 24-bit encrypted payload" layout assumed by
`luxorparts_bits_to_pulse_bytes()` / `_lx_encrypt_payload()` is therefore not
supported: every captured remote code has the 25-bit frame's MSB set.

Physical layer (unchanged, verified): OOK-PWM, 392 µs / 1148 µs pulses, 352 µs /
1108 µs gaps, 1500 µs constant period, 2248 µs inter-packet gap, 10 repeats for
on/off and 48 for learn.

## 3. Two code families in the captures

### 3.1 Remote family — seven physical remote buttons (14 codes)

These are the only codes in the repository captured from real remotes rather than
from Telldus Live, and they are almost entirely constant:

```
template payload = 0x5D55D5 = 0101 1101 0101 0101 1101 0101
```

| Bit class | Positions |
| --- | --- |
| always 1 | 0, 2, 4, 6, 7, 8, 10, 12, 14, 16, 18, 19, 20, 22 |
| always 0 | 3, 5, 15, 21, 23 |
| **data** | **1, 9, 11, 13, 17** |

All 14 captures satisfy `payload & ~0x022A02 == 0x5D55D5` (verified).

What the five data bits do:

| Field | Bit(s) | Evidence |
| --- | --- | --- |
| State | 1 | ON and OFF differ in **exactly this bit**: `R1-A ON 0x5D7DD5` / `OFF 0x5D7DD7`. Bit 1 = 0 means **ON**, bit 1 = 1 means **OFF** (inverted relative to the usual convention). Holds for five of the seven documented pairs; the two exceptions are the misassembled rows described below |
| Button / channel | 9, 11, 13 | only four patterns are used: `0x2800`, `0x2200`, `0x2000`, `0x0A00` |
| Remote / sub-remote | 17 | R1 and R2 codes differ **only** here (`0x5D…` vs `0x5F…`) |

Observed button fields (payload XOR template):

| Remote | A | B | C | D |
| --- | --- | --- | --- | --- |
| R1 (bit17 = 0) | `0x2800` | `0x2200`\* | `0x2000` | `0x0A00`† |
| R2 (bit17 = 1) | `0x2800` | `0x2200` | `0x2000` | `0x0A00` |

\* ON captured, OFF missing in `LPD 26`. † OFF captured, ON missing in `LPD 27`.

The three button bits are therefore *not* a binary channel number: only 4 of the 8
possible patterns appear (`101`, `110`, `100`, `011` as bits 13/11/9), and the four
unused patterns have never been observed on hardware.

Within this family's 16-code space this behaves like a fixed-code remote: one state
bit, three button bits, one address bit, no checksum, no rolling counter. That
conclusion is scoped to the 14 captures and says nothing about the Live family.

Two of the seven documented rows are anomalous — `R1-B` differs in bits 1 and 9,
`R1-C` in bits 1, 9, 11 and 13. Those rows are **assembly errors in the table, not
protocol behaviour**: each row holds one ON code and one OFF code from *different*
buttons.

| Row | Code | Actual field | Actual state |
| --- | --- | --- | --- |
| `LPD 26` ON | `0x5D75D7` | `0x2000` | **OFF** |
| `LPD 26` OFF | `0x5D77D5` | `0x2200` | **ON** |
| `LPD 27` ON | `0x5D5FD7` | `0x0A00` | **OFF** |
| `LPD 27` OFF | `0x5D75D5` | `0x2000` | **ON** |

The real pairs are `0x5D75D5`/`0x5D75D7` (field `0x2000`, complete) plus
`0x5D77D5` (field `0x2200`, ON only) and `0x5D5FD7` (field `0x0A00`, OFF only), so
remote 1 has two complete pairs (A and C) and two half-pairs (B, D). The button
letters follow R2's layout — the two remotes differ only in bit 17.

### 3.2 Telldus Live family — 48 codes

In this family **no bit is constant except bit 0**; all 23 other bits vary. ON and
OFF are *independent codes*, not a state-bit pair:

| Device | ON ^ OFF | Differing bits |
| --- | --- | --- |
| 14466/1 | `0x089A40` | 6, 9, 11, 12, 15, 19 |
| 14468/2 | `0x12A360` | 5, 6, 8, 9, 13, 15, 17, 20 |
| 14268/4 | `0x14CB60` | 5, 6, 8, 9, 11, 14, 15, 18, 20 |
| 21900/1 | `0x1AEDC0` | 6, 7, 8, 10, 11, 13, 14, 15, 17, 19, 20 |
| 12639/9 | `0x0A6320` | 5, 8, 9, 13, 14, 17, 19 |
| 12639/10 | `0x1F42C0` | 6, 7, 9, 14, 16, 17, 18, 19, 20 |
| 12639/11 | `0x1BC440` | 6, 10, 14, 15, 16, 17, 19, 20 |

Related codes still share most of their bits — `21900/U1 ON 0x681D7F` vs
`21900/U4 OFF 0x681D7B` differ by `0x04` — so the family is produced by a
generator with a per-device address, but each (device, state) pair is its own
24-bit value.

### 3.3 ⚠️ The Live captures are structured — and the labels overstate the code count

Grouping the 48 Live codes by `ON ^ OFF` exposes a pattern:

* Only **19 distinct ON^OFF values** exist for the 24 pairs, and **five of them are
  each shared by exactly two LPD entries**: `0A6320` (LPD 15, 17), `19AD40`
  (LPD 8, 10), `1AEDC0` (LPD 4, 9), `1BC440` (LPD 14, 19), `1F42C0` (LPD 13, 18).
* Those paired entries are **one bit apart in a criss-cross**: `A ON ~ B OFF`
  and `A OFF ~ B ON`, XOR `0x000004`, for all five pairs.

That is the signature of two codes produced by the same generator at two values of
one small field — a counter, or a state/parity bit that differed between captures —
with the ON/OFF labels crossed, rather than of two unrelated devices. So the 24
pairs are better read as **19 distinct code relationships, five of which were
captured twice at two values of that field**. The house/unit labels do not map
one-to-one onto distinct code identities.

This is a statement about **provenance, not usability**: all 24 recorded pairs work
on hardware (owner report, 2026-11-19), because a receiver learns whatever code it
is taught and does not care where that code came from. Nothing here limits the LPD
picker. It does mean that a generated code must reproduce the generator's field,
not merely the observed payloads.

Consequences:

* "No constant bits" in this family is partly an artefact of mixing field values
  and crossed labels together. It is **not** evidence that the payload is
  unstructured.
* The `0x04` field is unexplained, and an unexplained field is what a cipher or a
  counter looks like — i.e. this data argues **for** an unmodelled encoder, not
  against one.
* Any statement about "the Live family" below inherits this uncertainty.

## 4. The Homey cipher: unresolved, and not the remote encoding

`_lx_encrypt_payload()` in `const.py` implements a nibble-substitution + XOR chain
from the official Kjell & Co Homey app (`se.luxorparts-1`). The captures **do rule
it out for the remote family**, but they do **not** refute it for the Live family:

1. **A chain cipher diffuses single-bit changes.** Any change to one plaintext
   nibble propagates through 4 of the 6 output nibbles. The remote family changes
   exactly one bit of 24 to switch ON → OFF. No diffusion cipher can do that.
2. **Decrypting Live codes with it gives impossible results.** For a fixed device
   the recovered address must be constant, but it is not:

   | Device | State | Decrypted address | Decrypted ctrl |
   | --- | --- | --- | --- |
   | 21900/1 | ON | `0xFAFD` | `0x37` |
   | 21900/1 | OFF | `0xE787` | `0xF7` |
   | 12639/5 | ON | `0x37B1` | `0xD4` |
   | 12639/5 | OFF | `0x223B` | `0x24` |

   The cipher is a bijection on 24 bits, so those *are* its unique plaintexts —
   they simply are not an address/state layout.
3. The `[0][24-bit payload]` framing the cipher assumes is violated by every
   remote code (frame MSB set).

For the Live family the cipher remains a live candidate that simply has not been
translated correctly: the earlier exhaustive sweep (13 verified pairs, count 0–3,
unit offsets −2…+2, address transforms) also found 0 matches, and §3.3 shows the
dataset mixes counter states, so that sweep may have been comparing codes taken at
different counter values.

What can be said safely: the cipher is **not** the remote-family encoding, and it is
**not confirmed** as the Live-family encoding. Previous attempts did not fail because
of a missing insight; they failed because the plaintext field layout (address,
counter, state, unit) is still unknown, and the capture set is too incoherent to
constrain it.

## 5. No checksum found — which does not mean the payload is arbitrary

* Across 62 codes the only invariant in the 24-bit payload is bit 0 = 1.
* Each family also has a fixed frame MSB: 0 for all 48 Live codes, 1 for all 14
  remote codes. The MSB therefore acts as a family marker, not as a checksum.
* In the remote family the five data bits vary freely with no parity relation.
* No counter behaviour is visible across repeated captures of the same remote
  (the same ON code is transmitted on every press).

So no frame-level checksum or parity has been identified. That does **not** justify
"any payload is accepted": §3.3 shows an unexplained 0x04 field in the Live codes,
so a receiver could still decode and validate a field. Replay itself is no longer in
doubt — all 24 recorded pairs have been confirmed working on the Duo path — but every
one of them is a *recorded* pair; no generated code has been tested.

Whether the receiver stores whole codes and compares them — the assumption the whole
generation argument rests on — is **plausible from hardware behaviour but never
directly tested with a new code**. §7 is the test that decides it.

## 6. Generating new codes (hypotheses, not established capability)

Learning worked in v3.1.8.14 with a code our hardware transmitted, which is why
generating our own codes is plausible. But **every code ever accepted in testing was
a recorded one**, and the `0x04` field in §3.3 is unexplained. The two schemes below
are therefore candidates to test, not a solved generator.

### A. Template cloning (remote family) — closest to real hardware

```
payload_ON  = 0x5D55D5 | device_field          # bit 1 = 0
payload_OFF = payload_ON | 0x000002             # bit 1 = 1
stored28    = payload << 3
```

with

```
device_field = one of 0x2800, 0x2200, 0x2000, 0x0A00   (bits 13/11/9)
optional bit 17 selects remote 1 (0) or remote 2 (1)
```

That space is **4 fields × bit 17 × 2 states = 16 codes**, and 14 of them were
captured. Cloning the observed family therefore adds at most two codes — it is a
structure proof, not a generator. The one complete device pair missing from the
captures is `device_field = 0x2200`, bit 17 = 0:

| State | payload24 | frame25 | stored28 |
| --- | --- | --- | --- |
| ON | `0x5D77D5` | `0x15D77D5` | `0xAEBBEA8` |
| OFF | `0x5D77D7` | `0x15D77D7` | `0xAEBBEB8` |

If you want codes that are genuinely outside the captured set, extend to one of the
four **unobserved** button patterns, e.g. `0x0200` (bit 9 only):

| State | payload24 | frame25 | stored28 |
| --- | --- | --- | --- |
| ON | `0x5D57D5` | `0x15D57D5` | `0xAEABEA8` |
| OFF | `0x5D57D7` | `0x15D57D7` | `0xAEABEB8` |

Both variants are byte-for-byte the remote template with a different device field, so
they are the closest thing to a "known-good" code that was never captured. Whether
the receiver accepts them — or whitelists exactly the four observed patterns — is
what the hardware test in §7 settles.

Limitation: no real device space. Use A to prove the mechanism, B to actually scale.

**Tested on hardware 2026-11-19: all five A pairs were refused by a 50969 in
learn mode (see §7). Scheme A is falsified and removed from the code.**

### B. Live-family style — unlimited codes, matches the codes we already ship

```
payload24 = ((seed & 0x7FFFFF) << 1) | 1     # bit 0 forced to 1, frame MSB 0
stored28  = payload24 << 3
```

This reproduces the *shape* of the LPD 1–24 codes. All 24 recorded pairs are now
confirmed working on the Duo path, but every one of them is a recorded pair; no
generated code has been tried. It yields 2^23 distinct codes, enough for per-device uniqueness — if
receivers accept fresh codes at all.

**Reproducing the captures proves the seed algebra, not the protocol.** Every seed
below is just `payload24 >> 1`; that round-trip is true by construction for every
payload with bit 0 = 1, so it validates arithmetic and nothing else.

**Verified against every capture (2026-11-19):** all **48 Live-family codes
regenerate byte-for-byte** from `seed = payload24 >> 1`, and every seed falls inside
the 23-bit range — `0x206CC3` … `0x6DB763`, i.e. no truncation, no collisions, 62
distinct codes total. The 14 remote codes are deliberately *outside* B: their frame
MSB is 1, so they need a 24-bit seed (see below).

Seeds for the captured Live devices — `seed = payload24 >> 1`:

| Device | ON seed | OFF seed |
| --- | --- | --- |
| 14466/1 | `0x5E1453` | `0x5A5973` |
| 14468/2 | `0x559DBA` | `0x5CCC0A` |
| 14268/4 | `0x5BD4B8` | `0x51B108` |
| 21900/1 | `0x340EBF` | `0x39785F` |
| 166/3 | `0x6BD1C3` | `0x6DB763` |
| 2190/2 | `0x32128B` | `0x3E2CDB` |
| 16634/3 | `0x2450C3` | `0x263363` |
| 21900/3 | `0x3757C3` | `0x3B8163` |
| 21900/4 | `0x39785D` | `0x340EBD` |
| 21900/5 | `0x3B8161` | `0x3757C1` |
| 21901/1 | `0x35A0BF` | `0x339A5F` |
| 29102/1 | `0x3034BF` | `0x3C4D5F` |
| 12639/5 | `0x53F5EB` | `0x5C548B` |
| 12639/6 | `0x57231E` | `0x5AC13E` |
| 12639/7 | `0x5E8E60` | `0x5BBFF0` |
| 12639/8 | `0x51DA24` | `0x5467C4` |
| 12639/9 | `0x5BBFF2` | `0x5E8E62` |
| 12639/10 | `0x5C5489` | `0x53F5E9` |
| 12639/11 | `0x5AC13C` | `0x57231C` |
| unlabelled (LPD 20) | `0x23CEC3` | `0x292B63` |
| unlabelled (LPD 21) | `0x21A7C3` | `0x25F163` |
| unlabelled (LPD 22) | `0x206CC3` | `0x289D63` |
| unlabelled (LPD 23) | `0x2709C3` | `0x224A63` |
| unlabelled (LPD 24) | `0x2A86C3` | `0x2FE863` |

**B-wide** — if generation must also express the remote family, use a 24-bit seed
over the 25-bit frame instead:

```
frame25  = ((seed & 0xFFFFFF) << 1) | 1
stored28 = frame25 << 3
```

This reproduces **all 62** captured codes, including the 14 remote ones (their seeds
are `0xAEAFEB` … `0xAFBEEB`, which need the extra bit). B-wide covers both families
on paper. It is not "safer": it only decides which family's constant frame MSB you
emit, and neither variant has been tested with a fresh code.

### Recommendation

Do not pick a generator yet. Test **A** first — it is the only scheme in which every
bit pattern is a member of a family actually captured from hardware — then test **B**.
Only if A is accepted does "generation works at all" become established; B then
decides whether arbitrary codes are allowed.

Until those tests run, recorded pairs remain the only supported path, and the Homey
cipher should stay in the code rather than be replaced by an untested generator —
swapping one unvalidated mapping for another is not progress.

## 7. What to test on hardware

Scheme A is falsified: on 2026-11-19 **all five pairs** (LX-T1…LX-T5,
`0xAEABEA8`…`0xAFABEB8`) were refused by a 50969 in learn mode.
`_lx_template_pair()` and those codes are removed from `const.py`.

Scheme B is the test device now: device type **"Luxorparts — Test device, 5
switches (beta, Duo only)"**, which adds **one** Home Assistant device with five
generated switches **LX-B1…LX-B5** (houses 101–105) plus **CONTROL ON/OFF**
(house 106).

```
payload24 = ((seed & 0x7FFFFF) << 1) | 1     # bit 0 always 1, frame MSB 0
stored28  = payload24 << 3
```

The current build (v3.4.0.7) uses the Homey cipher itself: each pair is **one
plaintext record encrypted twice**, so its two halves decode to the same address
and differ only in the control byte. Every switch reuses the recorded pair's own
control bytes (`0x86` ON, `0x46` OFF, unit 6) with a fresh address:

| Switch | Plaintext (ON / OFF) | ON (stored28) | OFF (stored28) |
| --- | --- | --- | --- |
| LX-B1 | `D6 01 86` / `D6 01 46` | `0x21C7C38` | `0x203B638` |
| LX-B2 | `D6 02 86` / `D6 02 46` | `0x26EDC38` | `0x25E1E38` |
| LX-B3 | `D6 03 86` / `D6 03 46` | `0x2536C38` | `0x228C638` |
| LX-B4 | `D6 04 86` / `D6 04 46` | `0x27FCC38` | `0x2380E38` |
| LX-B5 | `D6 05 86` / `D6 05 46` | `0x203B438` | `0x21C7E38` |
| CONTROL (LPD 7) | recorded pair | `0x2450C38` | `0x2633638` |

`_lx_plain_pair(0xD510)` — the recorded ON code's own address — reproduced
`0x2450C38` byte for byte; that helper is gone, replaced by `_lx_unit_pair()`.

The control returns LPD 7's recorded pair from `luxorparts_generate_codes(106, 1)`
— house 106 rather than 7 so the test device never shares the normal LPD 7
device's UID. No pairing signal is sent and the switches have no Learn button:
pair by pressing a switch's **on** button with the receiver in learn mode.

1. Teach **CONTROL** first: receiver in learn mode, press CONTROL's **on**, then
   check that its on and off both work. If CONTROL fails, the test device's own
   wiring is at fault and the B results mean nothing.
2. Teach each of LX-B1…LX-B5 to a **different** socket and check that every switch
   controls only its own socket, with on and off the right way round.
3. If a switch still controls another one, or its on/off are reversed, the address
   field is not where the offsets land — move them further up the payload.

**Results (2026-11-19):** the v3.4.0.5 build, whose seeds differed by only 1…5
(payload bits 1–3), was **accepted in full** — CONTROL and all five generated pairs
were learned. But several of those switches then controlled the **same** socket with
on/off reversed. That settles two questions at once:

* the receiver **learns a code it has never seen**, so generation is possible;
* the receiver **decodes the payload** — bits 1–3 are state/unit, not address.

So "store the whole code and compare" is ruled out, and a generator must produce a
valid address/state encoding, not merely a plausible frame.

**Third build (v3.4.0.6, seed offset in the address bits):** all five **ON**
commands worked on their own sockets, and **no OFF command did** — only the
CONTROL, the single switch that replays a recorded pair. That is the decisive
datum. A receiver derives the OFF from the ON it learned and is never taught an
OFF (v3.1.8.14 taught a 50969 with the ON alone, after which both commands
worked), so the two halves of a pair must decode to *one* device. A seed offset
cannot do that: it is added to the stored payload, i.e. **after** the cipher, so
`0x2450C38` and `0x2633638` offset by the same amount decrypt to unrelated
records.

**Current build (v3.4.0.7):** each pair is one plaintext record — one address, the
recorded pair's own control bytes `0x86`/`0x46` (unit 6) — encrypted twice, so the
ON and OFF of a switch differ only in the state byte. `_lx_plain_pair(0xD510)`
reproduced the recorded LPD 7 ON code byte for byte (the helper was removed in
v3.4.0.10 — see the build note below).

**Result (v3.4.0.8, 2026-11-19):** all five ONs were learned and turned their socket
on, **no OFF worked** — five of five. The v1 group (LPD 7 seeds +1…5) run beside it
split three ways instead: B3 and B4 correct, B1 and B5 reversed (our ON read as an
OFF), B2 refused at learn time. Both controls worked. So the receiver decodes **and**
validates the frame, and the plaintext rebuild is falsified for OFF: the recorded
OFF is not the ON's own record with the state bits flipped.

Decrypting all 24 pairs then shows why. Payload bits 0–4 never change inside a pair
(the unit field); bits 5–7 and 8–23 change in **every** pair, giving 19 distinct
`ON ^ OFF` masks — there is no single state bit anywhere in the frame. For the seven
unit-6 pairs (LPD 5, 7, 20–24) the OFF control byte is always exactly
`ON ^ 0xC0` (`0x86` → `0x46`), and the **address** is the only other difference.

**Fourth build (v3.4.0.9, widget 23):** a recorded Telldus Live ON sent unchanged
with the OFF rebuilt at that same address (`ctrl ^ 0xC0`) — LPD 20…24 on houses
121–125 plus the LPD 7 control on 126. Result: every ON worked, **no OFF did**,
five of five. Removed again in v3.4.0.10.

**The v1 build is the key, and it is fully explained.** Decrypting its five pairs
against their reported behaviour:

| Switch | ON ctrl | OFF ctrl | `ctrl >> 6` ON / OFF | Reported |
| --- | --- | --- | --- | --- |
| LPD 7 (control) | `0x86` | `0x46` | `10` / `01` | correct |
| B1 | `0x6C` | `0xAC` | `01` / `10` | reversed |
| B2 | `0x4A` | `0x8A` | `01` / `10` | reversed, refused |
| B3 | `0x2B` | `0xEB` | `00` / `11` | correct |
| B4 | `0x09` | `0xC9` | `00` / `11` | correct |
| B5 | `0xD8` | `0xA8` | `11` / `10` | reversed |

**Bit 6 of the control byte is the state bit: 0 = ON, 1 = OFF.** All six outcomes
follow, and the three reversals are exactly the three ON halves with bit 6 set —
pressing them sends an OFF frame. Bit 7 is a don't-care. This is the state field
§3.2/§5 could not find in the raw payload: the chain cipher diffuses it, which is
why the raw `ON ^ OFF` masks are multi-bit (§3.3).

It also fixes the address question. A device is **two** plaintext addresses —
`D5 10` for its ON half and `D5 B1` for its OFF half — plus the unit. v1 kept
both addresses because it offsets two recorded ciphertexts, which is why B3/B4
work: they are those two addresses at a different unit. Every build that replaced
the OFF's address (a fresh one, or the ON's own) lost the OFF.

**Current build (v3.4.0.10, widget 21):** new units of the recorded LPD 7 address
pair — `ON = encrypt(D5, 0x10, 0x80 | unit)`, `OFF = encrypt(D5, 0xB1, 0x40 | unit)`
— houses 101–105 for units 9, 11, 7, 8 and 10, plus the recorded pair as control on
house 106. Unit 6 reproduces the recorded pair byte for byte. Units 9 and 11 are
the two v1 already proved; 7, 8 and 10 are new. Half the unit space (0–5, 13,
15–21, 29, 31) is unusable because those frames would not carry payload bit 0,
the one bit fixed in all 62 captured codes.

The open question is now narrow: does a 50969 treat a different unit value as a
different device? If yes, recorded address pair × 16 valid units gives 384
distinct devices without ever knowing the encoder.

## 7b. v4 failed; the channel field carries the state (v3.4.0.11)

**Hardware (2026-11-19, v3.4.0.10):** only B1 and B3 (units 9 and 7) learned and
turned their socket on, with **no OFF** on either; B2, B4 and B5 were refused at
learn time; the control worked. Every build that invents the encrypted part of the
frame has now failed — five of them.

The v1 group is still the only source of working OFFs, and it is enough. A v1 code
is the recorded LPD 7 pair shifted by `+2·offset` in the 24-bit payload. Because the
cipher is a nibble chain running from the payload's least-significant nibble
upwards, that shift rewrites only the control byte: both recorded addresses
(`0xD510` on, `0xD5B1` off) survive untouched. "v1 kept two addresses" is therefore
not a property of the code but of the arithmetic — v1 is the only build that never
touched the encrypted part.

The payload's low five bits — the **channel field** — are shared by the two halves
of every recorded pair (bits 1–4 never differ within a pair; bit 0 is always 1 over
all 62 captured codes). And the channel field is what decides the ON/OFF side: five
recorded pairs are siblings that are the same two frames with channel bit 2 (`0x04`)
flipped and the roles swapped.

| Pair | channel | sibling | channel |
| --- | --- | --- | --- |
| LPD 4 | `0x1F` | LPD 9 | `0x1B` |
| LPD 8 | `0x07` | LPD 10 | `0x03` |
| LPD 13 | `0x17` | LPD 18 | `0x13` |
| LPD 14 | `0x1D` | LPD 19 | `0x19` |
| LPD 15 | `0x01` | LPD 17 | `0x05` |

v1 sits on channel `0x07` and its offsets walked that bit:

| offset | channel | bit 2 | result |
| --- | --- | --- | --- |
| +1 | `0x09` | 0 | reversed |
| +2 | `0x0B` | 0 | reversed |
| +3 | `0x0D` | 1 | correct |
| +4 | `0x0F` | 1 | correct |
| +5 | `0x11` | 0 | reversed; the shift also carried into bit 5 (encrypted field) |

That is the answer to "why were the reversed ones reversed": their ON frame decoded
as an OFF frame because the shifted channel cleared bit 2. The earlier bit-6 reading
of the control byte agreed with all five v1 outcomes but is a property of the v1
family only — it does not survive the shift into other recordings, so the channel
field is the better model.

**v5 (`v3.4.0.11`)** therefore keeps the recorded frames and moves only inside the
channel field with bit 2 held: LPD 7 +3 and +4 (v1's two working pairs), LPD 5 −1,
LPD 13 −1 and LPD 6 +4 on houses 131–135, plus the recorded LPD 7 control on 136.

## 8. Still unknown

* What the `0x04` field in §3.3 is (counter, state or parity), and whether the
  receiver requires it to be consistent for acceptance.
* Whether the Live-family address space is meaningful to the receiver or purely
  arbitrary — decided by B's hardware test, not by analysis.
* Whether 50970 (indoor) and 50972 (dimmer) use the same frame — only 50969
  captures exist.
* Whether any receiver revision enforces the remote template. Scheme A is immune
  to this; scheme B is not.

## 9. What this changes in the code

* The test device now builds its pairs **with the Homey cipher itself**
  (`LX_TEST_LIST`, houses 101–105, `_lx_unit_pair()`) plus the LPD 7 control
  (house 106, `LX_CONTROL_CODES`). Scheme A is falsified, and so is offsetting a
  stored payload: a pair has to be two encryptions of one record. The cipher is no
  longer an unvalidated candidate for the Live family — decrypting the recorded
  pairs yields one plaintext address per remote (all five criss-cross groups) and
  the recorded LPD 7 ON re-encrypts byte for byte.
* **v3.4.0.10** turns the test device into `_lx_unit_pair(unit)` — the recorded
  LPD 7 pair's two addresses and state patterns with only the unit changed
  (`LX_TEST_UNITS = (9, 11, 7, 8, 10)`), so every switch is a distinct device.
  `_lx_decrypt_payload()` stays (it is how the state bit and the unit space were
  established). The v3 group and `LX_LIVE_STATE_XOR` are removed.
* **v3.4.0.11** adds v5 (widget 24): recorded pairs shifted only inside the channel
  field with channel bit 2 held — houses 131–135, control 136.
* If B succeeds, `luxorparts_generate_codes()` can return scheme-B values for
  unknown houses; the recorded pairs stay authoritative for LPD 1–24.
* **If** B passes its hardware test, the LPD picker could grow past 24 by
  generating additional pairs, so users would no longer be limited to the captured
  list and no two installs would need to share a code. Until then, the picker stays
  at the recorded pairs.
* No timing, repeats or command-format change is involved — the existing
  `P\x02 R10 S50+` path and the verified pulse widths are unaffected.
