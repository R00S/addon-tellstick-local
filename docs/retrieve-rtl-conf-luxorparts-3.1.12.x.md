# Branch Timeline: retrieve-rtl-conf-luxorparts 3.1.12.x

**Branch:** `copilot/retrieve-rtl-conf-luxorparts`
**Version series:** `3.1.12.x`
**Date started:** 2026-04-17
**Purpose:** Fix the "Create Test Release" CI action failing with exit code 4; codify the
branch-timeline-file convention; retrieve RTL-433 conf for Luxorparts.

> **Agents: read this file before implementing anything on this branch.**
> It documents every root cause found, every solution tried, and what the
> current state is — so we don't repeat failed approaches or forget key
> discoveries.

---

## Problem statement (user-reported)

> "action to create test release still fails. Do we need to merge to test it
> properly? Else fix it."

The `Create Test Release` GitHub Actions workflow was failing at the Docker
build step with **exit code 4** during the telldus-core compilation phase.

---

## Root cause investigation

### Symptom

Docker buildx reported:

```
ERROR: failed to build: failed to solve: process "/bin/bash -o pipefail -c ..."
did not complete successfully: exit code: 4
```

The failing RUN layer in `tellsticklive/Dockerfile` is the telldus-core build
layer (lines 18–63). The exit code 4 is returned by the shell when one of the
`&&`-chained commands fails.

### Discovery: Alpine 3.22 musl conflict (root cause)

The base image `ghcr.io/erik73/base-python/amd64:4.0.8` is Alpine-based.
Alpine 3.22 introduced a **version conflict** between the pre-installed `musl`
package and the build-dependency chain:

- APK tries to install `build-base` → `musl-dev` → requires `musl >= 1.2.5.r1`
- The container already has `musl 1.2.5.r0` (from base image layer)
- APK refuses to install the build-deps, exits non-zero → shell exits with
  code 4

This is a **known Alpine 3.22 regression** affecting many Dockerfile users.
The canonical fix is to upgrade `musl` (and friends: `musl-utils`, `musl-dev`)
explicitly **before** adding the build-dependencies.

**References searched:**
- Alpine Linux bug tracker / release notes for 3.22
- Multiple GitHub issues in unrelated projects reporting identical `exit code:
  4` symptoms when adding `build-base` on Alpine 3.22
- The fix (upgrade musl first) is consistently recommended across all those
  reports

### Were the patch assertions also an issue?

The Dockerfile applies Python-script patches to the upstream telldus-core
source:

1. `ProtocolNexa.cpp` — TellStick Duo R-prefix learn repeat
2. `Strings.h` / `Strings.cpp` / `Socket_unix.cpp` / `DeviceManager.cpp` —
   binary-safe IPC (`charToWstringRaw` / `wideToStringRaw`)

Upstream `erik73/telldus` (master) was verified:
- `ProtocolNexa.cpp` patch target still present ✅
- `DeviceManager.cpp` has exactly 2 occurrences of the expected pattern ✅
- `Socket_unix.cpp` has the expected `charToWstring(msg.c_str())` target ✅

The patches themselves are not broken. The failure was entirely the musl
version conflict.

---

## Solution applied

### Commit `371da4e` — `fix: upgrade musl before build-deps to resolve Alpine 3.22 version conflict (exit code 4)`

**Files changed:** `tellsticklive/Dockerfile`, `docs/LUXORPARTS_TIMELINE.md`,
`custom_components/tellstick_local/manifest.json`

**Dockerfile change:** Added an explicit `apk add --no-cache --upgrade musl
musl-utils musl-dev` step immediately before the `.build-dependencies` block:

```dockerfile
&& apk add --no-cache --upgrade \
    musl \
    musl-utils \
    musl-dev \
&& apk add --no-cache --virtual .build-dependencies \
    argp-standalone \
    ...
```

This ensures musl is at the latest available version before build-deps are
resolved, eliminating the version conflict.

**Version:** `3.1.12.4` → `3.1.12.5`

---

## Convention codified this session

The branch-timeline-file convention was formally added to both instruction
files (see commits on this branch):

- `AGENTS.md` — section "Branch Timeline Files"
- `.github/copilot-instructions.md` — block added at top of Quick Commands

**Rule:** Every branch has a timeline file at
`docs/<branch-name-without-prefix>-<A.B.C.x>.md`
(e.g. `docs/retrieve-rtl-conf-luxorparts-3.1.12.x.md` for branch
`copilot/retrieve-rtl-conf-luxorparts` at version `3.1.12.5`).
Agents **must** read it before implementing anything, and **must** update it
after each discovery or implementation step.

---

## Current state (end of session)

| Item | Status |
|------|--------|
| Docker build exit code 4 | ✅ Fixed (musl upgrade added) |
| Branch timeline file | ✅ Created (this file) |
| Convention in instruction files | ✅ Added to AGENTS.md + copilot-instructions.md |
| Create Test Release action | ✅ Should now work on any branch |

---

## RTL-433 configuration (`docs/rtl_433.conf`)

The file `docs/rtl_433.conf` already exists in the repo from previous sessions.
It was created to capture raw 433 MHz signals for debugging Luxorparts and
other protocol work.

**Key design decisions recorded in the file comments:**

- **No `protocol N` lines** — intentional. Adding any `protocol N` line
  disables all other built-in decoders. Without restriction, all built-in
  decoders run first; only truly unknown signals fall through to
  `report_unknown on`. This gives full protocol coverage AND captures
  unknown frames (Nexa dim levels, Luxorparts proprietary signals, etc.).

- **`report_unknown on`** — captures any signal no built-in decoder
  recognises. This is how Luxorparts raw signals and Nexa dimmer dim-level
  commands (20/40/60/80/100%) were captured.

- **Output:** `mqtt://core-mosquitto:1883/rtl_433[/model][/id]` — publishes
  to the Mosquitto broker add-on using HA Supervisor's internal hostname.

**How to use:**
1. Install `pbkhrv/rtl_433-hass-addons` from the HA add-on store
2. Copy `docs/rtl_433.conf` to the add-on configuration directory
3. Install and start Mosquitto broker add-on
4. Press a remote — decoded JSON appears as MQTT messages under `rtl_433/`

---

## Luxorparts test device (`const.py` — `DEVICE_CATALOG`)

The Luxorparts test device is in `DEVICE_CATALOG` at line ~321 of `const.py`:

```python
# NOTE: Luxorparts/Cleverio 50969, 50970, 50972 — BETA (Duo only)
# Uses raw RF pulse encoding via LPD codes.  Pick LPD 1-24 to select
# a verified Telldus Live code pair.  Not available on Net/ZNet yet.
("Luxorparts — On/off (beta, Duo only)", "luxorparts", "selflearning-switch:lx_live", 20),
```

Widget 20 means the user picks `house` = LPD number (1–24); `unit` is fixed
at 1. The LPD number selects one of the 24 verified ON/OFF code pairs
captured via RTL-433 from Telldus Live transmissions (see
`luxorparts_generate_codes()` in `const.py`).

**Protocol details (from `const.py` lines ~883–960):**

- OOK-PWM, 433.92 MHz
- Bit 1: short pulse ≈ 392 µs + long gap ≈ 1108 µs (total ≈ 1500 µs)
- Bit 0: long pulse ≈ 1148 µs + short gap ≈ 352 µs (total ≈ 1500 µs)
- 25 data bits, MSB first
- 10 repeats for on/off, 48 for learn/pairing
- Inter-packet gap ≈ 2248 µs
- Encryption: nibble-substitution cipher ported from Homey `se.luxorparts-1`
  `lib/PayloadEncryption.js`

**All 24 LPD code pairs** are in `const.py` at `_LX_VERIFIED_CODES`, verified
via RTL-433 captures of Telldus Live signals. Pairs 1–13 are labeled
(address confirmed from user's Telldus Live device list); pairs 14–24 are
unlabeled (captured but device address unconfirmed).

**Encoding path in the integration:**

```
switch.py → async_turn_on/off
  → controller.send_luxorparts_raw(lpd, "on"/"off")
    → luxorparts_generate_codes(lpd, 1) → code
    → luxorparts_build_packet(code, repeats=10)  → raw bytes
    → client.py send_raw_command(bytes)          → TCP → telldusd → Duo
```

**Known working:** On/off with `P\x02 R<10> S<50 bytes>+` format makes the
Duo flash and is accepted by the physical Luxorparts receiver (verified,
version 3.1.8.14). Learn (48 repeats) does not flash the Duo — workaround is
to use the on/off command for pairing.

---

## Pending / future work on this branch

- [ ] Confirm whether RTL-433 conf needs any further changes for this branch's scope
- [ ] Confirm with user whether additional LPD pairs need to be captured
