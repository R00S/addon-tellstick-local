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

Scheme A is implemented as an opt-in test device: device type
**"Luxorparts — Generated test codes (beta, Duo only)"**, picker 101–105. Each
pair comes from `_lx_template_pair()` in `const.py` — the remote template with an
unobserved button field, so none of the ten codes appears in any capture.

| Pick | Button field | ON (stored28) | OFF (stored28) |
| --- | --- | --- | --- |
| 101 (LX-T1) | `0x0200` (bit 9) | `0xAEABEA8` | `0xAEABEB8` |
| 102 (LX-T2) | `0x0800` (bit 11) | `0xAEAEEA8` | `0xAEAEEB8` |
| 103 (LX-T3) | `0x2A00` (bits 9+11+13) | `0xAEBFEA8` | `0xAEBFEB8` |
| 104 (LX-T4) | `0x0000` (no button bits) | `0xAEAAEA8` | `0xAEAAEB8` |
| 105 (LX-T5) | `0x0200` + bit 17 | `0xAFABEA8` | `0xAFABEB8` |

1. Add one test device on the Duo, pick 101, put a 50969 in learn mode and press
   Learn. Confirm the receiver learns it and then responds to ON and OFF.
2. If 101 fails, try 102–105 — they differ only in the button field, so a partial
   success tells you which bits the receiver checks.
3. If A works, repeat with scheme B (a Live-style pair), which is the real
   target: arbitrary codes on demand.
4. If A works and B fails, the receiver validates part of the remote template and
   generation must stay inside family A.

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

* The opt-in scheme-A test device now exists (`LX_TEST_LIST`, picker 101–105).
  Do not retire the Homey cipher until A and B are hardware-tested — swapping one
  unvalidated mapping for another is not progress.
* If A succeeds, `luxorparts_generate_codes()` can return scheme A or B
  values; the recorded pairs stay authoritative for LPD 1–24.
* **If** A and B pass their hardware tests, the LPD picker could grow past 24 by
  generating additional pairs, so users would no longer be limited to the captured
  list and no two installs would need to share a code. Until then, the picker stays
  at the recorded pairs.
* No timing, repeats or command-format change is involved — the existing
  `P\x02 R10 S50+` path and the verified pulse widths are unaffected.
