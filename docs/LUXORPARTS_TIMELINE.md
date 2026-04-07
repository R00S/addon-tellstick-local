# Luxorparts RF Protocol — Development Timeline & Lessons Learned

**Branch:** `copilot/implement-luxorparts-rf-protocol`
**Date range:** 2026-04-07
**Purpose:** Prevent regressions by documenting what was tested, what worked,
and what broke at each stage.

---

## Quick Reference — What Works and What Doesn't

| Approach | Duo Flashes? | Receiver Accepts? | Notes |
|---|---|---|---|
| `S<inline_data>+` (PPM, 8 reps, 418 bytes) | ✅ YES | ❌ NO | Wrong modulation — PPM not PWM |
| `R<n>S<data>+` (PPM or PWM) | ❌ NO | ❌ NO | Duo stops flashing entirely |
| `P\x00 R<n>S<data>+` (PWM) | ❌ NO | ❌ NO | Duo stops flashing entirely |
| Multiple sequential `S<inline>+` commands | ❌ NO | ❌ NO | Duo stops flashing on 2nd+ command |
| `S<inline_data>+` (PWM, correct encoding) | ❓ UNTESTED | ❓ UNTESTED | Should be tested next |

### Known Good Signal (Telldus Live, verified by RTL-433)

```
Modulation:  OOK-PWM (Pulse Width Modulation)
Pulse short: 392 µs (bit 1)
Pulse long:  1148 µs (bit 0)
Gap short:   352 µs (paired with long pulse)
Gap long:    1108 µs (paired with short pulse)
Period:      constant ~1500 µs
Inter-packet gap: 2248 µs (replaces last data gap)
Bits per packet: 25 (50 bytes, NO trailing pulse+gap pair)
Packets per burst: 10
Total: 250 pulses, 387 ms
```

### What Our Duo Actually Sent (PPM version, v3.1.8.7)

```
Modulation:  OOK-PPM (Pulse Position Modulation) ← WRONG
Pulse:       396 µs (fixed, all bits same) ← WRONG — should vary
Gap short:   340 µs (bit 1)
Gap long:    1100 µs (bit 0)
Bits per packet: 25 + 1 trailing = 26 pulses (52 bytes)
Packets:     unknown (1 detected by rtl_433 per S command)
Total:       28.82 ms
```

### Key Differences

1. **Modulation:** We sent PPM (fixed pulse, varying gap). Telldus Live
   sends PWM (varying pulse, maintaining constant ~1500 µs period).
2. **Trailing pulse:** Our encoder added a 26th pulse+gap pair (inter-packet).
   Telldus Live replaces the last DATA gap with the inter-packet gap — 25 data
   pairs total, no trailing pair. (50 bytes not 52.)
3. **Repeat mechanism:** Telldus Live sends 10 inline repeats. We tried R-prefix
   (firmware repeat) which breaks the Duo completely.

---

## Commit-by-Commit Timeline

### 1. `27fe816` — v3.1.8.0 — Initial Luxorparts test device

**What:** Added 24 test encoding variants, raw pulse encoder in `net_client.py`,
config flow menu to create test devices, `tdSendRawCommand` stub in `client.py`.

**Encoder:** PPM (fixed pulse), no right-shift of 28-bit codes, 10 inline
repeats (520 bytes), called `_encode_string()` (UTF-8) for raw command.

**Result:** ❌ Never tested on Duo. `send_raw_command` used `_call_int` which
goes through UTF-8 encoding — bytes ≥ 128 (like `LX_GAP_INTER = 225 = 0xE1`)
would be corrupted by UTF-8 multi-byte encoding. Also 520 bytes overflows the
512-byte firmware USART buffer.

**Bugs present:**
- UTF-8 corruption of pulse bytes ≥ 128
- Buffer overflow (520 > 512 bytes)
- No right-shift of 28-bit codes (wrong bits)
- PPM encoding (wrong modulation)

---

### 2. `f7d5ccf` — v3.1.8.1 — Binary-safe send_raw_command

**What:** Rewrote `send_raw_command` in `client.py` to build TCP message
manually (bypass UTF-8). Moved encoder functions from `net_client.py` to
`const.py`. Added Luxorparts detection in `switch.py` (`_send_luxorparts_raw`).

**Fix:** ✅ Binary-safe TCP transport (no more UTF-8 corruption of bytes ≥ 128).

**Remaining bugs:**
- Buffer overflow (520 bytes with 10 inline repeats)
- No right-shift (wrong bits)
- PPM encoding (wrong modulation)

---

### 3. `629be01` — v3.1.8.2 — Patch telldus-core IPC for binary safety

**What:** Added Dockerfile patches to telldus-core: `charToWstringRaw` and
`wideToStringRaw` cloned functions that use byte-by-byte Latin-1 instead of
iconv UTF-8. `Socket::read()` and `DeviceManager::sendRawCommand()` use the
raw variants.

**Fix:** ✅ telldusd IPC layer now binary-safe for raw commands. Existing
protocols unaffected (still use original UTF-8 functions).

**Remaining bugs:**
- Buffer overflow
- No right-shift
- PPM encoding

---

### 4. `fb530cc` — v3.1.8.3 — Fix Hadolint

**What:** Compressed multi-line Python patch in Dockerfile to single line for
Hadolint compliance.

**Lesson:** 🔧 Hadolint cannot parse multi-line `python3 -c "..."` strings.
Always use single-line format for inline Python patches in Dockerfiles.

---

### 5. `358c6a3` — v3.1.8.4 — Fix buffer overflow with R-prefix

**What:** Changed from inline repeats (520 bytes) to firmware R-prefix:
`R<count>S<52 bytes>+` = 56 bytes.

**Fix:** ✅ No more buffer overflow.

**Result:** ❌ **DUO STOPPED FLASHING.** The R-prefix approach causes the
Duo to not transmit at all. This was the first time we observed this failure
mode.

> **LESSON LEARNED:** The TellStick Duo firmware's `R<n>S<data>+` prefix does
> NOT work reliably with `tdSendRawCommand`. The Duo simply does not transmit.
> The root cause is unclear but consistently reproducible. **Do NOT use R-prefix.**

**Remaining bugs:**
- R-prefix doesn't work (Duo doesn't flash)
- No right-shift
- PPM encoding

---

### 6. `bb51539` — v3.1.8.5 — Added learn button, attempted PWM fix

**What:** Added Luxorparts-specific learn button in `button.py`. Changed
encoder comments from PWM to PPM (but the ACTUAL encoder code is unclear
at this point due to multiple conflicting changes).

**Note:** This commit didn't sync changes to the `tellsticklive/rootfs/`
mirror directory for button.py.

---

### 7. `3565a8d` / `ddaa02c` — v3.1.8.6 — Fix encoder bugs

**What:** Two rapid commits fixing:
- Bug #1: Added right-shift by 3 for 28-bit → 25-bit code extraction
- Bug #2: Clarified PPM encoding (fixed pulse, varying gap)
- Bug #3: Still using inline repeats

**Fix:** ✅ Right-shift now extracts correct 25-bit code from 28-bit hex.

---

### 8. `772d3b5` — v3.1.8.7 — PPM + 8 inline repeats ⭐ FIRST DUO FLASH

**What:** Clean rewrite of encoder:
- PPM encoding (fixed pulse `39`, gap varies: short `35` / long `111`)
- Right-shift by 3 for correct bit extraction
- 8 inline repeats per S command (52 × 8 = 416 + 2 = 418 bytes, under 512)
- Learn: 6 sequential S commands × 8 repeats = 48 total

**Command format:** `S<416 bytes>+` = 418 bytes

**Result: ✅ ON/OFF DID FLASH! ❌ Receiver did not accept the signal.**

User report: *"on/off now flashes, the luxorparts switch does not react
even in learning mode"*

RTL-433 showed our signal was **PPM** (fixed pulse 396µs, varying gap) while
Telldus Live uses **PWM** (varying pulse 392µs/1148µs, constant period).

**Learn did NOT flash** — the 6 sequential S commands approach failed.
Likely the Duo can't handle rapid sequential `tdSendRawCommand` calls.

> **KEY FINDING:** Inline S commands DO work on the Duo (single command).
> R-prefix does NOT work. Sequential S commands also problematic for learn.

**Remaining bugs:**
- PPM encoding (should be PWM)
- Trailing pulse+gap pair (52 bytes, should be 50)
- Learn doesn't flash (sequential S commands fail)

---

### 9. `542bf22` — v3.1.8.7 (cont) — Doc cleanup

**What:** Fixed stale OOK-PWM references in comments to say OOK-PPM.

---

### 10. `6df4858` — v3.1.8.8 — Revert to R-prefix ❌ REGRESSION

**What:** Reverted from 8 inline repeats back to R-prefix:
`R<count>S<52 bytes>+`

**Result:** ❌ **DUO STOPPED FLASHING AGAIN.** Same failure as commit #5.

> **LESSON RE-LEARNED:** R-prefix does NOT work on the Duo for raw commands.
> This was already discovered in commit #5 but the lesson wasn't retained.

---

### 11. `4b3a59c` / `d467fc8` — v3.1.8.9/v3.1.9.0 — PWM + P0 R-prefix ❌❌

**What:** Two commits changing:
- Encoder from PPM to PWM (varying pulse width, constant period)
- Added `P\x00` prefix (zero inter-repeat pause)
- Still using R-prefix: `P\x00 R<n> S<50 bytes> +`
- Removed trailing pulse+gap (50 bytes per packet, not 52)

**Command format:** `P\x00 R\x0a S<50 bytes>+` = 56 bytes

**Result:** ❌ **DUO DOES NOT FLASH.** R-prefix still broken regardless of
P-prefix or PWM/PPM encoding.

---

### 12. `d80f385` — v3.1.8.10 — Version fix only

**What:** Fixed version back to 3.1.8.10 (was incorrectly bumped to 3.1.9.0),
fixed minor doc references.

**Result:** Same as #11 — nothing functional changed.

---

## Root Cause Analysis

### Why R-prefix doesn't work

The firmware's `handleMessage()` processes `R<n>` by setting `repeats = buffer[p+1]`.
Then when `S` is encountered, `send(start, pause, repeats)` calls `rfSend()`
in a loop. **In theory** this should work. Possible causes:

1. **Null terminator missing:** `rfSend()` reads pulse bytes until it hits `0x00`.
   Our pulse data contains no `0x00` (min value = 35). Without a null terminator
   after the pulse data, `rfSend()` reads past the data into the `+` byte (0x2B)
   and whatever follows in the buffer. This could cause very long or garbage
   transmissions that the Duo LED can't show normally.

2. **The `0x00` in P\x00:** The null byte at position 1 in the command could
   cause issues in C string handling somewhere in the telldusd → firmware path,
   truncating the command.

3. **Firmware bug with R-prefix for raw S commands:** The R-prefix may only work
   reliably when the pulse data is generated by telldus-core's protocol engine,
   which includes a proper null terminator. Raw S commands from `tdSendRawCommand`
   may not include this terminator.

### Why inline S DOES work

The inline approach (`S<repeated_data>+`) puts all pulse bytes in a single
contiguous block. Even without a null terminator, `rfSend()` reads through all
the data, hits `+` (0x2B = 43), interprets it as one extra short pulse, then
hits `0x00` (buffer zero-initialized on boot) and stops. The spurious extra
pulse doesn't prevent transmission — the Duo LED flashes.

### Why the wrong modulation

The encoder used PPM (Pulse Position Modulation — fixed pulse, varying gap)
instead of PWM (Pulse Width Modulation — varying pulse, constant period).
The correct encoding based on RTL-433 comparison with Telldus Live is:

```
bit 1: SHORT pulse (39 = 390µs) + LONG gap (111 = 1110µs)  → period 1500µs
bit 0: LONG pulse (115 = 1150µs) + SHORT gap (35 = 350µs)  → period 1500µs
```

### Why 50 bytes not 52

Telldus Live sends 25 data bits as 25 pulse-gap pairs (50 bytes). The
inter-packet gap REPLACES the last data gap — there is no extra 26th
pulse+gap pair. Our early encoder added a trailing `[pulse, gap_inter]`
pair making it 52 bytes.

---

## Anti-Patterns — Never Do These Again

### ❌ 1. Do NOT use firmware R-prefix for Luxorparts raw commands

**Failure count:** 3 times (commits #5, #10, #11)

The `R<n>S<data>+` approach causes the TellStick Duo to not transmit at all.
Always use inline repeats: `S<data × N>+`.

### ❌ 2. Do NOT send P\x00 (null byte in command payload)

The null byte can be truncated by C string functions anywhere in the
telldusd → USB path. Avoid null bytes in the command payload entirely.

### ❌ 3. Do NOT send multiple sequential tdSendRawCommand calls rapidly

Learn at v3.1.8.7 used 6 sequential S commands. On/off worked (single command)
but learn did NOT flash. The Duo may not handle rapid sequential raw commands.
For learn, embed all 48 repeats inline if possible.

### ❌ 4. Do NOT exceed 512 bytes in a single S command

The firmware USART buffer is 512 bytes. Commands exceeding this overflow
silently. At 50 bytes per packet (PWM), 10 inline repeats = 502 bytes
(`S` + 500 + `+`), which is SAFE.

### ❌ 5. Do NOT use PPM encoding for Luxorparts

RTL-433 comparison confirmed Telldus Live uses PWM (varying pulse width,
constant period). PPM (fixed pulse, varying gap) is the wrong modulation.

### ❌ 6. Do NOT forget the right-shift for 28-bit hex codes

Ground-truth codes are stored as 28-bit hex integers with 3 bits of zero
padding at the LSB. The encoder MUST right-shift by 3 to extract the
correct 25-bit code.

### ❌ 7. Do NOT add a trailing pulse+gap pair

Telldus Live sends exactly 25 data pairs (50 bytes). The inter-packet gap
replaces the last data gap. Do NOT add a 26th pair.

### ❌ 8. Do NOT forget to sync changes to `tellsticklive/rootfs/usr/share/tellstick_local/`

The integration is deployed from this mirror directory, NOT from
`custom_components/`. If only `custom_components/` is updated, the deployed
code on the user's HA instance won't change.

---

## What To Try Next

Based on the timeline, the next approach should combine:

1. ✅ **Inline S repeats** (the only approach that makes the Duo flash)
2. ✅ **PWM encoding** (correct modulation matching Telldus Live)
3. ✅ **50 bytes per packet** (no trailing pulse+gap pair)
4. ✅ **Right-shift by 3** (correct 25-bit code extraction)
5. ✅ **10 inline repeats** = 500 bytes → `S<500>+` = 502 bytes (under 512)
6. ❓ **Learn** — 10 repeats per command, send 5 sequential commands with
   delays between them (total 50 repeats). OR try a single command with
   10 repeats and see if the receiver learns.

### Buffer math for 10 inline PWM repeats

```
50 bytes/packet × 10 repeats = 500 bytes
S + 500 + = 502 bytes total
512 - 502 = 10 bytes margin ✅
```

### Expected RTL-433 output if correct

```
Total count: 250 pulses (10 packets × 25 bits)
Pulse widths: 390µs and 1150µs (two widths — PWM)
Gap widths: 350µs, 1110µs, 2250µs (inter-packet)
Period: constant ~1500µs
codes: {25}51b1088 × 10
Guessing modulation: Pulse Width Modulation
```

This should match Telldus Live's output exactly (within timing tolerances).
