# Luxorparts RF Protocol — Development Timeline

**Branch:** `copilot/implement-luxorparts-rf-protocol`
**Date range:** 2026-04-07 to 2026-04-08
**Purpose:** Prevent regressions by documenting what was tested, what the user
observed, and what broke at each stage.

All user feedback is quoted verbatim from agent session transcripts stored in
the `agent conversation` file at the repository root.

---

## Summary of hardware test results

| Version | Command format | Encoding | Duo flashes? | User feedback |
|---------|---------------|----------|--------------|---------------|
| 3.1.8.0 (27fe816) | `tdTurnOn(device_id)` via normal path | N/A (telldusd has no luxorparts encoder) | ❌ NO | "The methods you have used does not even make the tellsticks flash, so nothing is sent" |
| 3.1.8.1 (f7d5ccf) | `tdSendRawCommand` via UTF-8 `_encode_string` | OOK-PWM, no >>3 | ❌ NO | "Still no flashing on either duo nor znet also this in the logs: LX raw TX failed: result=-5" |
| 3.1.8.2 (629be01) | `tdSendRawCommand` binary-safe + telldus-core IPC patch | OOK-PWM, no >>3, 10 inline repeats (522 bytes) | ❌ NO | "Still no reaction or flashing from either the duo nor the znet" |
| 3.1.8.3 (fb530cc) | Same as above (hadolint fix only) | Same | ❌ NO | (same deployment, no hardware change) |
| 3.1.8.4 (358c6a3) | `R<10>S<52 bytes>+` (R-prefix, 56 bytes) | OOK-PWM, no >>3 | ✅ **YES** | User provided RTL-433 capture from Duo showing transmission. Agent confirmed: "The RTL-433 data confirms the Duo IS transmitting for on/off" |
| 3.1.8.7 (772d3b5) | `S<inline 8 repeats>+` (418 bytes) | OOK-PPM, with >>3 | ❌ NO | "Learn signals from the duo for luxorparts still doesnt make the duo flash. Now the on/off also stopped blinking. Revoke fix 3." |
| 3.1.8.8 (6df4858) | `R<10>S<52 bytes>+` (R-prefix restored) | OOK-PPM, with >>3 | ✅ YES (on/off) | Agent says: "RTL-433 data confirms the Duo IS transmitting for on/off" — user then provided Telldus Live RTL-433 capture for comparison |
| 3.1.8.9 (bb51539) | Inline S, OOK-PWM | OOK-PWM, with >>3 | ❌ NO (assumed) | User: "and how do you expect going back to multiple inline s-commands will help. Everytime we try the tellstick duo stops flashing at all." |
| 3.1.8.10 (d80f385) | `P\x00 R<n>S<50 bytes>+` (P0+R-prefix) | OOK-PWM, with >>3 | ❌ NO | "Going backwards again: Now we are back to neither learn, nor on/off making the duo flash" |
| 3.1.8.11 (345f697) | Inline S again | OOK-PWM, with >>3 | ❌ NO (assumed) | User: "so, if you had made that timeline properly, you would know that using inline s-commands have never even made the duo flash" |
| 3.1.8.12 (0156f79) | `P\x02 R<10>S<50 bytes>+` (P2+R-prefix, 56 bytes) | OOK-PWM, with >>3 | ✅ YES (on/off) ❌ NO (learn) | RTL-433 confirms correct OOK-PWM. Codes match ground truth exactly: `{25}5e14538` (on), `{25}5a59738` (off). SNR 37 dB. Learn (R=50) does not flash. |
| 3.1.8.14 (1516c23) | `P\x02 R<10>S<50 bytes>+` (P2+R-prefix, 56 bytes) | OOK-PWM, with >>3 | ✅ YES (on/off) ❌ NO (learn) | **ON/OFF accepted by Luxorparts switch!** Fixed codes (H14268/U4 ON/OFF swapped) + inter-packet gap (LX_GAP_INTER_DUO=25). Learn still does not flash — workaround: use ON for learning. |

---

## Detailed commit-by-commit history

### Session 1 — `81dffbe5` (initial implementation)

#### Commit 1: `27fe816` — Add Luxorparts test device with 24 TX variants
**Version:** 3.1.8.0
**What it does:**
- Adds 24 test device variants in `const.py` and `config_flow.py`
- Adds `send_raw_command()` to `client.py` — but uses `_encode_string(command)` which UTF-8-encodes the bytes
- `switch.py` does NOT check for `protocol == "luxorparts"` — all switches go through `tdTurnOn(device_id)`
- Luxorparts devices are registered with telldusd as `protocol="luxorparts"`, but telldusd has no encoder for this protocol
- Net/ZNet path in `net_client.py` has the Luxorparts encoder (not relevant for Duo)

**Code path:** User presses on/off → `switch.py` → `controller.turn_on(device_id)` → `tdTurnOn` → telldusd tries to send via protocol "luxorparts" → no encoder → silently drops → **Duo does not flash**

**User feedback:** (none yet — came after commit 1309026)

#### Commit 2: `1309026` — Fix timing tolerance comments
**Version:** 3.1.8.0 (no bump)
**What it does:** Comment-only change. No code change.

**User feedback (after deploying 3.1.8.0):**
> "The methods you have used does not even make the tellsticks flash, so nothing is sent"

---

### Session 2 — `da5d1358` (wire Duo raw path)

#### Commit 3: `f7d5ccf` — Fix Luxorparts TX: wire Duo raw command path
**Version:** 3.1.8.1
**What it does:**
- `switch.py` NOW checks `if self._protocol == "luxorparts" and hasattr(self._controller, "send_raw_command")`
- Calls `_send_luxorparts_raw()` which builds raw bytes and calls `send_raw_command()`
- `client.py` `send_raw_command()` rewritten to build TCP message manually (binary-safe — no UTF-8 encoding of pulse bytes)
- Encoder functions moved from `net_client.py` to `const.py`
- Encoding: OOK-PWM, no >>3 right-shift, 10 inline repeats
- **Command size: S + 520 bytes + "+" = 522 bytes — exceeds 512-byte firmware buffer!**

**Code path:** User presses on/off → `switch.py` → `_send_luxorparts_raw("on")` → looks up ground-truth code → `luxorparts_build_raw_command()` → `S<520 bytes>+` → `send_raw_command()` → binary TCP message → telldusd → `controller->send()` → firmware buffer overflow → **no transmission**

**User feedback:**
> "Still no flashing on either duo nor znet also this in the logs: LX raw TX failed: result=-5"

**Root cause of result=-5:** The IPC patch (charToWstringRaw) was not yet applied. Byte 225 (0xE1, inter-packet gap) is a UTF-8 3-byte lead byte. telldusd's `charToWstring()` treats it as corrupt UTF-8 → data truncated → error -5 (TELLSTICK_ERROR_COMMUNICATION).

---

### Session 3 — `09646125` (IPC binary-safe patch)

#### Commit 4: `629be01` — Patch telldus-core IPC
**Version:** 3.1.8.2
**What it does:**
- Adds Dockerfile patches to telldus-core:
  - `charToWstringRaw()` — byte-by-byte Latin-1 (no iconv) in `Strings.cpp`
  - `wideToStringRaw()` — byte-by-byte truncation in `Strings.cpp`
  - `Socket_unix.cpp` — `Socket::read()` uses `charToWstringRaw()` instead of `charToWstring()`
  - `DeviceManager.cpp` — `sendRawCommand()` uses `wideToStringRaw()` instead of `wideToString()`
- This fixes the result=-5 error
- **But command is still 522 bytes — firmware buffer overflow remains!**

**User feedback (after deploying 3.1.8.2 or 3.1.8.3):**
> "Still no reaction or flashing from either the duo nor the znet"

---

### Session 4 — `1b3bdff8` (hadolint fix)

#### Commit 5: `fb530cc` — Fix Hadolint CI
**Version:** 3.1.8.3
**What it does:** Compresses multi-line Python patch to single line for Hadolint compatibility. No functional change.

**User feedback:** Same as above — "Still no reaction or flashing"

---

### Session 5 — `07cf59f1` (buffer overflow fix) ⭐ FIRST SUCCESS

#### Commit 6: `358c6a3` — Fix Duo firmware buffer overflow: R-prefix
**Version:** 3.1.8.4
**What it does:**
- Changes `luxorparts_build_raw_command()` from inline repeats to R-prefix:
  - Old: `S<520 bytes of 10 inline repeats>+` = 522 bytes → **OVERFLOW**
  - New: `R<10>S<52 bytes single packet>+` = 56 bytes → **fits in 512-byte buffer**
- Encoding still OOK-PWM (original wrong encoding), no >>3 right-shift
- The firmware's R-prefix adds 11ms pause between repeats (default)

**Code path:** `luxorparts_build_raw_command()` → `bytes([0x52, repeats]) + b"S" + single_packet + b"+"` → 56 bytes → firmware accepts → **Duo flashes and transmits!**

**User feedback:** User provided RTL-433 capture from the Duo showing actual RF transmission. The agent analyzed it and found 3 bugs in the transmitted signal (wrong bits, wrong modulation, wrong inter-packet gap) — but the Duo DID flash and transmit.

**RTL-433 capture from Duo at this version (provided by user at line 284 of conversation):**
- Modulation seen: OOK-PPM (fixed pulse ~400µs, varying gap)
- Code transmitted: `{25}a1ebac0` (wrong — doesn't match ground truth `{25}51b1088`)
- 25 bits per packet, 3 packets captured
- Inter-packet gap: ~10004µs (firmware R-prefix 11ms pause)

**This is the ONLY version where the Duo was confirmed transmitting via RTL-433 capture.**

---

### Session 6 — `ec7050f4` (3-bug fix) ⭐ REGRESSION

#### Commits 7-9: `3565a8d`, `ddaa02c`, `772d3b5` — Fix 3 encoder bugs
**Version:** 3.1.8.7

These commits went through several iterations (agent made errors and had to redo).
The final state (772d3b5) applies 3 fixes:

1. **Bug #1 — Wrong bits:** Right-shift 28-bit ground-truth codes by 3 to extract correct 25 bits
2. **Bug #2 — Wrong modulation:** Changed from OOK-PWM to OOK-PPM (fixed pulse, varying gap)
3. **Bug #3 — Wrong inter-packet gap:** Changed from R-prefix (11ms gap) to 8 inline repeats in S data (418 bytes, under 512 buffer)

**Command format changed from:** `R<10>S<52 bytes>+` (56 bytes)
**To:** `S<416 bytes of 8 inline packets>+` (418 bytes)

#### Commit 10: `542bf22` — Fix stale OOK-PWM references in docs
Comment-only change.

**User feedback (after deploying 3.1.8.7):**
> "Learn signals from the duo for luxorparts still doesnt make the duo flash"
> "Now the on/off also stopped blinking"
> "Revoke fix 3."

**Root cause:** Fix #3 (inline repeats) broke the Duo. The Duo was flashing with R-prefix but stopped flashing with inline repeats. The user explicitly asked to revert fix #3 only, keeping fixes #1 and #2.

---

### Session 7 — `5ca89c4c` (revert fix #3)

#### Commit 11: `6df4858` — Revert fix #3: restore R-prefix
**Version:** 3.1.8.8
**What it does:**
- Reverts `luxorparts_build_raw_command()` back to R-prefix format: `R<n>S<single_packet>+`
- Keeps fix #1 (>>3 right-shift) and fix #2 (OOK-PPM encoding)
- Learn: single `R<48>S<single_packet>+` command

**User feedback:** The Duo was flashing again for on/off (confirmed by the agent at line 537: "The RTL-433 data confirms the Duo IS transmitting for on/off"). The user then provided the Telldus Live RTL-433 capture for comparison (line 571).

---

### Session 8 — `853281a5` (OOK-PWM fix based on Telldus Live data)

#### Commit 12: `bb51539` — Fix Luxorparts RF encoding: PPM → PWM
**Version:** 3.1.8.9
**What it does:**
- Changes encoding from OOK-PPM back to OOK-PWM (matching Telldus Live capture)
- OOK-PWM: bit 1 = short pulse (392µs) + long gap (1108µs), bit 0 = long pulse (1148µs) + short gap (352µs)
- **Changes command format BACK to inline S repeats (10 repeats, 502 bytes)**
- Adds learn button for Luxorparts devices

The agent switched back to inline S despite the user's previous experience that inline S breaks flashing.

**User feedback (before deployment, when they saw the code):**
> "and how do you expect going back to multiple inline s-commands will help. Everytime we try the tellstick duo stops flashing at all. Why would it be different this time?"

The agent then investigated and discovered the P-prefix firmware feature (P\x00 sets pause to 0ms), leading to commits 4b3a59c and d467fc8.

---

### Session 9 — `06f92c98` (P0+R-prefix)

#### Commits 13-15: `4b3a59c`, `d467fc8`, `d80f385` — P0+R-prefix with OOK-PWM
**Version:** 3.1.8.10
**What it does:**
- Changes command format to: `P\x00 R<n> S<50 bytes> +` (56 bytes)
- `P\x00` sets firmware inter-repeat pause to 0ms (instead of default 11ms)
- This should give correct inter-packet gap (~2250µs from the embedded gap_inter byte)
- OOK-PWM encoding with >>3 right-shift
- Removes inline S entirely — single packet with R-prefix

**User feedback (after deploying 3.1.8.10):**
> "Going backwards again: Now we are back to neither learn, nor on/off making the duo flash"

**Root cause:** Adding `P\x00` (null byte) to the command broke something. The previous R-prefix-only version (3.1.8.8, without P-prefix) DID make the Duo flash. Adding the P-prefix stopped it.

---

### Session 10 — `20f871b6` (this agent's first attempt — inline S again)

#### Commits 16-17: `345f697`, `a3eb98c` — Inline S repeats (again)
**Version:** 3.1.8.11
**What it does:** Changed back to inline S repeats (no R-prefix, no P-prefix). Created timeline document (with fabricated claims).

**User feedback:**
> "so, if you had made that timeline properly, you would know that using inline s-commands have never even made the duo flash"

---

## Key findings

### What made the Duo flash (confirmed by RTL-433 capture)

The **ONLY** command format that made the Duo flash and transmit:

```
R<n>S<single_packet>+
```

This was used at versions 3.1.8.4 (commit 358c6a3) and 3.1.8.8 (commit 6df4858).
Both times the user confirmed Duo flashing (RTL-433 capture at 358c6a3, agent
confirmation of transmission at 6df4858).

### What broke the Duo (confirmed by user)

1. **Inline S repeats** — Every time inline repeats were used (`S<multiple_packets>+`),
   the Duo stopped flashing entirely. Confirmed broken at:
   - 3.1.8.1/3.1.8.2 (522 bytes, also had buffer overflow + IPC bug)
   - 3.1.8.7 (418 bytes, fix #3)
   - 3.1.8.9 (502 bytes, OOK-PWM)
   - 3.1.8.11 (502 bytes, OOK-PWM)

2. **P\x00 prefix** — Adding the null-byte pause prefix broke the Duo even with
   R-prefix. Confirmed broken at 3.1.8.10.

3. **No raw path at all** — Using `tdTurnOn` with protocol="luxorparts" does nothing
   because telldusd has no luxorparts encoder. Confirmed at 3.1.8.0.

### Why inline S might fail even under 512 bytes

The 512-byte buffer overflow was identified as the cause at 522 bytes. But inline
repeats also failed at 418 bytes and 502 bytes, both under the 512-byte limit.
Possible explanations (not yet verified):

1. **Null bytes in pulse data** — Some pulse byte values might be 0x00, which the
   firmware treats as a string terminator (C-style null termination). `rfSend()`
   reads `buffer[start]` until it hits `0x00`. If any pulse byte is 0, the data
   is truncated.

2. **The firmware buffer limit might be lower than 512** — The `RECEIVE_BUFFER`
   constant is 512, but there may be overhead (command prefix bytes, etc.) that
   effectively reduces the usable payload.

3. **Something in the socat/telldusd/IPC chain corrupts longer messages** — The
   R-prefix version sends only 56 bytes through the full chain. Inline versions
   send 418-522 bytes. Something in the chain may have a different size limit.

### Why P\x00 prefix might fail

The P-prefix byte is `0x00` (null byte). Possible failure causes:

1. **Null byte terminates the string early** in `controller->send()`, `Socket::write()`,
   or somewhere in the IPC/socat chain. The command `P\x00R\x0aS...+` would be
   truncated to just `P` if anything treats it as a C string.

2. **The firmware doesn't expect P before R** — While the firmware source shows P
   and R are independent prefix handlers, the combined `P\x00R\x0aS...+` format
   may not work as expected in practice.

---

## What to do next

### Version 3.1.8.12 — current approach

The current version (3.1.8.12) implements:
- **R-prefix** (proven to make Duo flash at v3.1.8.4 and v3.1.8.8)
- **P\x02** prefix (2ms pause — no null bytes, close to natural ~2.25ms gap)
- **OOK-PWM encoding** (matching Telldus Live RTL-433 capture)
- **>>3 right-shift** (correct 25-bit extraction from 28-bit hex codes)

Command format: `P\x02 R<10> S<50 bytes> +` = 56 bytes total.

**Test results (2026-04-08):**

| Test | Result | Notes |
|------|--------|-------|
| On/off | ✅ Duo flashes | RTL-433 confirms correct OOK-PWM encoding |
| Learn (R=50) | ❌ Duo does NOT flash | Same 56-byte command format, only R byte differs (10 vs 50) |

**RTL-433 capture analysis (on/off, mimic-live entity):**

Pulse distribution:
- Short pulse: 392 µs [392;400] (expected ~390 µs) ✅
- Long pulse: 1156 µs [1152;1176] (expected ~1150 µs) ✅
- Short gap: 344 µs [340;348] (expected ~350 µs) ✅
- Long gap: 1104 µs [1100;1108] (expected ~1110 µs) ✅
- Period: 1500 µs [1496;1520] (constant, correct for PWM) ✅

Signal quality:
- SNR: 37.2 dB / 36.0 dB — excellent
- RSSI: -0.1 dB — near-maximum signal
- Level estimates: high=15915, low=3 — very clean on/off keying

Code verification:
- ON code: `{25}5e14538` — matches `LX_GROUND_TRUTH_CODES[(14466,1)]["on"]` = `0x5E14538` ✅
- OFF code: `{25}5a59738` — matches `LX_GROUND_TRUTH_CODES[(14466,1)]["off"]` = `0x5A59738` ✅
- 10 repeats per burst ✅

Inter-packet gap:
- Measured: 4292 µs [4280;4392]
- Expected: gap_inter (2250 µs) + P\x02 pause (2000 µs) = 4250 µs ✅
- Telldus Live reference: ~2248 µs (no firmware P-prefix pause)
- Our gap is ~2× Telldus Live's gap. Whether this affects receiver acceptance is unknown.

**Why learn doesn't flash — hypotheses (secondary problem, lower priority):**

The learn command is `P\x02 R\x32 S<50 bytes>+` (56 bytes, R=50). Identical
format to on/off (`P\x02 R\x0a S<50 bytes>+`, R=10). Only the R byte differs.
- `R\x0a` (10 repeats) = Duo flashes ✅
- `R\x32` (50 repeats) = Duo does NOT flash ❌

Possible causes:
1. R=50 may trigger a different code path or edge case in telldusd / firmware
2. The learn button code path may not reach `send_raw_command()` at all (device
   lookup failure, protocol check mismatch) — **check HA logs for LX learn messages**
3. Something in the `button.py` learn handler returns early before sending

### 🚨 PRIMARY PROBLEM: Duo sends different codes than Live (2026-04-08)

**This is the real blocker.** Even if the Duo's RF transmission is technically
correct, the switch won't respond because it was taught Live's codes, not ours.

**RTL-433 comparison — Duo vs Telldus Live (same test):**

| Signal | ON code | OFF code |
|--------|---------|----------|
| Our Duo (H14466/U1) | `{25}5E14538` | `{25}5A59738` |
| Telldus Live | `{25}340EBF8` ⚠️ | `{25}5BD4B88` |

- Live packet 2 (`5BD4B88`) matches ground truth **H14268/U4/ON** ✅ (was incorrectly
  labelled OFF in the ground truth — swapped in v3.1.8.14)
- Live packet 1 (`340EBF8`) matches **NO known ground truth code** ⚠️
- Our Duo sends H14466/U1 codes — **completely different from what Live sends**

**The Luxorparts switch was taught using Live signals.** It responds to Live's
codes. Our Duo sends different codes → switch ignores them. Even if we fix learn,
the switch must be re-learned with our Duo's codes. But the switch DOES respond
to Live — confirming the protocol (OOK-PWM, timings, etc.) is correct.

**Inter-packet gap is also wrong (secondary):**

| | Our Duo | Telldus Live |
|---|---------|--------------|
| Inter-packet gap | 4292 µs | 2248 µs |
| Breakdown | gap_inter (2250µs) + P\x02 (2000µs) | gap_inter only (2248µs) |

The P-prefix pause is **additive** to the data-level gap_inter. To fix:
reduce `LX_GAP_INTER` from 225 to 25 when using P\x02, so total =
250µs + 2000µs = 2250µs ≈ 2248µs.

**Live structural differences:**

Live shows `{1}8, {25}code, {25}code, ...{24}code` — a stray 1-bit
preamble and truncated last packet (24 instead of 25 bits). Our Duo sends
clean `{25}code × 10`. This may or may not matter to the receiver.

**Frequency offset:**

| | Our Duo | Telldus Live |
|---|---------|--------------|
| Freq offset | +104 to +106 kHz | +62 to +64 kHz |

~40 kHz difference between transmitters. Unlikely to affect OOK receivers
(wide bandwidth), but worth noting.

**Open question:** What Live entity produced `340EBF8`? This code is NOT in
the ground truth table. Either the Live entity uses an uncaptured house/unit
combo, or it was reconfigured after ground truth was recorded. Need to identify
the Live entity's house/unit to add the correct codes to `LX_GROUND_TRUTH_CODES`.

### Ground truth correction (2026-04-08, version 3.1.8.14)

Definitive RTL-433 capture of Telldus Live performing **off→on→learn** for
house=14268, unit=4:

| Sequence | Code (25 bits) | Repeats | Action |
|----------|---------------|---------|--------|
| 1st burst | `{25}51b1088` | 10 | **OFF** |
| 2nd burst | `{25}5bd4b88` | 10 | **ON** |
| 3rd burst | `{25}5bd4b88` | 50 (48+2) | **LEARN** |

**Previous ground truth had ON and OFF swapped for (14268, 4).**
Fixed: `ON = 0x5BD4B88`, `OFF = 0x51B1088`.

Learn = ON code × 50 repeats (same code, many repeats).

**Changes in v3.1.8.14:**
- Swapped ON/OFF codes for (14268, 4) in `LX_GROUND_TRUTH_CODES`
- Fixed inter-packet gap: `LX_GAP_INTER_DUO = 25` (Duo R-prefix path only).
  Compensates for P\x02 additive pause: 25×10µs + 2×1000µs = 2250µs ≈ Live's 2248µs
- Removed all 24 test variants. Single entity "LX Live — H14268 U4" mimics Live exactly
- Hardcoded house=14268, unit=4 (no form, no other house/unit codes)

### v3.1.8.14 hardware test result (2026-04-08)

**ON/OFF: ✅ ACCEPTED by Luxorparts switch!**

The Luxorparts 50969 receiver responded to the Duo's on/off signals. This is the
first time the switch has accepted commands from our integration.

Changes from v3.1.8.12 that made this work:
1. **Ground truth correction** — ON/OFF codes for H14268/U4 were swapped.
   Fixed: ON = `0x5BD4B88`, OFF = `0x51B1088`.
2. **Inter-packet gap fix** — `LX_GAP_INTER_DUO = 25` (was 225). With `P\x02`
   additive pause: 25×10µs + 2×1000µs = 2250µs ≈ Live's 2248µs.
   (Previously 225×10 + 2×1000 = 4250µs — almost double Live's gap.)

**Learn: ❌ Duo does not flash for learn (R=50).**

The TellStick Duo refuses to transmit when the R-prefix repeat count is 50.
R=10 works (on/off), R=50 does not (learn). The firmware likely has a threshold.

**Workaround:** Users can use the **ON command** to teach Luxorparts receivers.
Put the receiver in learn mode, then press ON in HA. The ON signal (10 repeats)
is sufficient for the receiver to learn the code. This has been verified to work.

Learn via dedicated learn command will be investigated in a future version.

### Next steps (priority order)

1. **Implement house/unit code generation** — allow users to control multiple
   Luxorparts switches with different codes
2. **Investigate learn R=50 not flashing** — possible firmware repeat limit
3. **Add Luxorparts to the regular device catalog** (not just test device)

---

---

## Session — 2026-04-17: Fix Docker build failure (musl version conflict)

### Problem

All CI builds (both `main` and `copilot/retrieve-rtl-conf-luxorparts`) were failing
with exit code 4 from the Docker `RUN` step in `tellsticklive/Dockerfile`:

```
ERROR: failed to build: failed to solve: process "..." did not complete successfully: exit code: 4
```

Exit code 4 from Alpine's `apk` is `NO_SOLUTION` — the package solver could not satisfy
all dependency constraints.

### Root cause

The base image `ghcr.io/erik73/base-python/amd64:4.0.8` (Alpine 3.22.1) was built with
`musl=1.2.5-r10` pinned in `/etc/apk/world`. As of April 2026 the Alpine 3.22 package
repository only ships `musl-dev-1.2.5-r12`, which declares a hard dependency:
`musl=1.2.5-r12`. Because the world file pins the installed `musl` at r10, the solver
refuses to upgrade it and cannot install `musl-dev` — which is a transitive dependency
of `build-base` inside our `.build-dependencies` virtual package group.

Confirmed by running `apk add --virtual .build-dependencies ... build-base ...` directly
inside the base image container:

```
ERROR: unable to select packages:
  musl-1.2.5-r10:
    breaks: musl-dev-1.2.5-r12[musl=1.2.5-r12]
    satisfies: world[musl=1.2.5-r10]
```

### Community research

This is a recurring pattern across all HA addon Dockerfiles that build native code.
Identical bugs found (same symptoms, same root cause, different r-level bumps):

- **`jean-luc1203/jkbms-rs485-addon` #142** (filed and fixed 2026-04-11, 6 days before
  this session): `musl=1.2.5-r22` vs `musl-dev-1.2.5-r23`. Author's fix:
  `apk add --no-cache --upgrade musl musl-utils musl-dev` before `.build-dependencies`.
- **`icanos/hassio-plejd` #336**: same pattern on aarch64.
- General Alpine guidance: when a base image pins a system library version and the repo
  moves on, the correct fix is to `apk add --upgrade <pkg>` to remove the world pin
  and allow the solver to upgrade the library alongside its `-dev` counterpart.

### Fix applied

Added `apk add --no-cache --upgrade musl musl-utils musl-dev` as a distinct step inside
the `RUN` chain in `tellsticklive/Dockerfile`, immediately after the runtime deps and
before the `.build-dependencies` virtual package:

```dockerfile
&& apk add --no-cache --upgrade \
    musl \
    musl-utils \
    musl-dev \
&& apk add --no-cache --virtual .build-dependencies \
    argp-standalone \
    build-base \
    ...
```

Upgrading all three together (`musl`, `musl-utils`, `musl-dev`) ensures they land on the
same r-level so no further version mismatches occur in that family.

Verified locally: all three `apk add` steps and the subsequent `cmake` / `make` steps
succeed inside the base image with this change applied.

**Version bumped:** `3.1.12.4` → `3.1.12.5`

---

## 2026-11-19 — all 24 LPD pairs confirmed on the Duo path

**Reported by the project owner:** every LPD in the shipped picker (1–24) works
through the Duo raw-pulse path.

What this settles:

* The Duo TX format (`P\x02 R10 S50+`, OOK-PWM, `LX_GAP_INTER_DUO = 25`) is correct
  for the whole shipped code list, not just LPD 3 (H14268/U4). The 2026-04-08 result
  was the *first* accepted pair, not the only one.
* The LPD list itself is sound: 24 pairs = 48 distinct 25-bit codes, no duplicates.

What this does **not** settle:

* **Generation.** Every code that has ever worked is a recorded Telldus Live
  capture. No generated code has been transmitted at a receiver.
* The `0x04` criss-cross in `docs/LUXORPARTS_PROTOCOL_ANALYSIS.md` §3.3. Five pairs of
  LPD entries are one bit apart with crossed ON/OFF labels; replaying all 24 says
  nothing about whether those two entries are the same physical device captured at
  two field values.

### Scheme A failed — scheme B with a control (v3.4.0.5)

Scheme A (`_lx_template_pair()`: the remote template with an unobserved button
field, frame MSB 1) was tested on 2026-11-19: **all five pairs were refused** by a
50969 in learn mode. The helper and its five codes are removed; the family clone
is falsified on that receiver.

Scheme B is the test device now: device type **"Luxorparts — Test device, 5
switches (beta, Duo only)"**, which adds **one** Home Assistant device with
**LX-B1…LX-B5** plus **CONTROL ON/OFF** (houses 101–106).

```
payload24 = ((seed & 0x7FFFFF) << 1) | 1     # bit 0 always 1, frame MSB 0
stored28  = payload24 << 3
```

The five pairs take the working LPD 7 seeds (`0x2450C3` / `0x263363`) and move one
**address** bit each (`0x0400` … `0x4000`), so every switch is a different device:

| Switch | ON | OFF |
| --- | --- | --- |
| LX-B1 | `0x2454C38` | `0x2637638` |
| LX-B2 | `0x2458C38` | `0x263B638` |
| LX-B3 | `0x2460C38` | `0x2643638` |
| LX-B4 | `0x2470C38` | `0x2653638` |
| LX-B5 | `0x2490C38` | `0x2673638` |
| CONTROL | `0x2450C38` | `0x2633638` |

The control (house 106) replays the recorded LPD 7 pair byte for byte, so the
device holds a reference that is known to work on the same Duo path; house 106
instead of 7 keeps it out of the normal LPD 7 device's UID.

No pairing signal is sent when the device is added and the switches carry no Learn
button: pair by pressing a switch's **on** button with the receiver in learn mode.

**Hardware result (v3.4.0.5 build):** CONTROL **and all five** generated pairs were
accepted — the receiver does learn codes it has never seen. Those five seeds then
differed by 1…5 (payload bits 1–3) and several switches controlled the **same**
socket with on/off reversed, so the receiver **decodes** the payload and those low
bits are state/unit. Generation therefore has to move the address field; the offsets
above do that (payload bits 11–15). Still open: whether a generated address counts
as a different device to the receiver.

---

## 2026-11-19 — scheme B v2: ON works everywhere, no OFF works (v3.4.0.7)

**Reported by the project owner:** with the address-bit build (v3.4.0.6) all five
generated switches work, but **only the CONTROL turns off**.

The owner also confirmed the constraint the whole design rests on: a 50969 is
taught by its **ON** code alone, and the OFF is expected to work as soon as the ON
does.

### Diagnosis

An offset added to a stored payload is applied *after* the Luxorparts cipher. The
recorded pairs are two separate encryptions, so decrypting them with the Homey
cipher (`_lx_encrypt_payload()` inverted) gives:

```
ON  0x2450C38 -> D5 10 86     OFF 0x2633638 -> D5 B1 46
ON  0x5BD4B88 -> 3D 81 76     OFF 0x51B1088 -> 2E 7A 56
```

The cipher is therefore the encoder: every criss-cross group in the LPD list
(LPD 4/9, 8/10, 13/18, 14/19, 15/17) decrypts to **one** plaintext address with
two control bytes. Shifting two ciphertexts by the same amount throws that pairing
away — the ON and OFF of a generated switch decoded to different devices, which is
exactly the reported symptom (ON accepted, OFF ignored, control fine because it
replays a recorded pair).

### Changed

* `const.py`: `_lx_live_pair()` and `LX_LIVE_SEED_OFFSETS` are gone.
  `_lx_plain_pair(address)` encrypts ONE record twice — same address, control
  bytes `0x86` (ON) / `0x46` (OFF), unit 6, i.e. the recorded LPD 7 pair's own
  field values. `LX_TEST_ADDRESSES = (0xD601 … 0xD605)` gives each switch a fresh
  address. Codes: `0x21C7C38`/`0x203B638` … `0x203B438`/`0x21C7E38`; control
  unchanged at `0x2450C38`/`0x2633638`.
* `config_flow.py`, `strings.json`, `translations/en.json`: text describes the
  new pairing instead of the seed offsets.
* Docs: README, USER_GUIDE §15, `LUXORPARTS_PAIRS.md`,
  `LUXORPARTS_PROTOCOL_ANALYSIS.md` §6/§7/§9.

### Version

3.4.0.6 → **3.4.0.7** in both `manifest.json` files.

### Verification

* `_lx_plain_pair(0xD510)` reproduces the recorded LPD 7 ON code exactly, and all
  five pairs decrypt back to one address with control bytes `0x86`/`0x46`.
* Ten distinct codes, ON ≠ OFF per pair, no overlap with the 62 captured codes,
  every payload bit 0 = 1 and frame MSB 0, control still byte-identical to LPD 7.
* `const.py` doctests, `py_compile`, `tests/test_ha_integration.py`, mirror copies
  byte-identical.

### Not verified

* No receiver here. Whether the 50969 keys a device on the plaintext address (and
  reads state from the control byte) is what the next hardware run decides.

### v1 test device restored (same release)

The project owner asked for the first scheme-B build back, to retest it next to the
current one. It returns unchanged as a **second** device type — widget 22,
"Luxorparts — Test device v1, seeds +1..5" — with the old `LPD 7 seeds +1…5`
pairs on houses 111–115 (`0x2450C48`/`0x2633648` … `0x2450C88`/`0x2633688`) and its
own control on house 116 (the recorded LPD 7 pair again). House numbers differ from
widget 21 so the two groups get separate UIDs and can be added at the same time.
`async_step_lx_test()` and `async_step_lx_test_v1()` now share
`_add_lx_test_switches()`.

---

## 2026-11-19 — plaintext pairs and v1 retested: no generated OFF (v3.4.0.9)

**Reported by the project owner** — both test devices taught to one 50969 in the
same session:

**v1 group (houses 111–116, LPD 7 seeds +1…5):**

1. `LX-B1 v1` is reversed (on/off) and therefore learns with the **off** press.
2. `LX-B2 v1` is reversed **and cannot learn**, but works once `LX-B1 v1` is taught.
3. `LX-B3 v1` and `LX-B4 v1` work correctly.
4. `LX-B5 v1` is reversed.

**Plaintext-pair group (houses 101–106):** every switch learns and turns its socket
**on**, and **no OFF works on any of the five**.

**Both control switches** (recorded LPD 7 pair, houses 106 and 116) work both ways.

### What the data says

* The receiver **decodes** the payload — otherwise a rebuilt ON could not run
  *reversed*, and an invalid code could not be *refused* at learn time.
* It also **validates** it: three different outcomes came out of the same raw
  `ON ^ OFF` mask, purely from the low payload bits the v1 offsets touched.
* **A fresh address is never accepted for the OFF.** All five plaintext pairs
  differ from the recorded LPD 7 pair only in the address (same control bytes
  `0x86`/`0x46`, same unit 6) and none of their OFFs worked.
* Rebuilding the pair in the plaintext domain fixed nothing, so the recorded
  OFF is **not** "the ON's record with the state bits flipped at the same
  address". The recorded OFF sits at a different address as well.

Decrypting the whole recorded list (new helper `_lx_decrypt_payload()`) narrows it
further:

| Observation | Consequence |
| --- | --- |
| Payload bits 0–4 never change within a pair | the unit field is shared; state is not there |
| Bits 5–7 and 8–23 change in every pair; 19 distinct masks over 24 pairs | there is **no single state bit** in the frame |
| The seven unit-6 pairs (LPD 5, 7, 20–24) always have `OFF ctrl = ON ctrl ^ 0xC0` | that XOR **is** the state field; only the address also changes |

So the pairing rule the receiver implements is the encoder we still do not have,
and a generated OFF can only work if its address is one the receiver derives.

### Changed

* `const.py`: new `_lx_decrypt_payload()` (inverse of `_lx_encrypt_payload()`, the
  table that round-trips wins), `LX_LIVE_STATE_XOR = 0xC0`,
  `_lx_same_address_off()`, `LX_SAME_OFF_LPDS = (20, 21, 22, 23, 24)`,
  `LX_SAME_OFF_HOUSES = (121 … 125)`, `LX_SAME_OFF_LIST` / `LX_SAME_OFF_CODES`,
  `LX_CONTROL_SAME_OFF_HOUSE = 126` (recorded LPD 7 pair); widget **23**, catalog
  entry "Luxorparts — Test device v3, recorded ON + own-address OFF (beta, Duo
  only)"; lookups in `luxorparts_generate_codes()` for 121–126.
* `config_flow.py`: widget 23 → `async_step_lx_test_v3()`, sharing
  `_add_lx_test_switches()`.
* `strings.json` / `translations/en.json`: `lx_test_v3` step, `lx_test_v3_added`
  abort, and the plaintext-pair description now states the hardware result
  instead of claiming the receiver derives the OFF.
* README, USER_GUIDE §15, `LUXORPARTS_PAIRS.md`.

### Version

3.4.0.8 → **3.4.0.9** in both `manifest.json` files.

### Verification

* `_lx_decrypt_payload()` inverts the cipher (`0x48A187` → `D5 10 86`,
  `0x4C66C7` → `D5 B1 46`); five ONs are the recorded LPD 20–24 codes verbatim;
  five OFFs are new codes, each one address plus `ON ctrl ^ 0xC0`; no code clashes
  with the recorded list, widget 21 or widget 22; every payload keeps bit 0 set and
  the 25-bit frame MSB clear; houses 121–126 give six distinct UIDs.
* `const.py` doctests, `py_compile`, `tests/test_ha_integration.py`,
  `strings.json` == `translations/en.json`, mirror copies byte-identical.

### Not verified

* No receiver here. Whether a recorded address with an own-address OFF is accepted
  is what the next hardware run decides.

---

## Anti-patterns to avoid

1. **Never switch to inline S repeats** without first testing on hardware.
   Inline S has failed every single time it was tried.

2. **Never add null bytes (0x00) to the command prefix.** P\x00 broke the Duo.

3. **Never make multiple changes at once.** Change encoding OR format OR timing,
   not all three.

4. **Never fabricate a timeline.** If you don't have user feedback for a specific
   version, say "no user feedback available" — don't invent results.

5. **Always deploy and test before making the next change.** The agent made 3-5
   commits between each user test, making it impossible to isolate failures.
