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

## Fix: redundant "restart required" notifications after HAOS restart (v3.1.12.6)

### Problem

Every time HAOS restarts after an app upgrade, the integration shows a
"Restart Home Assistant" notification. Users find this confusing because they
already restarted HAOS (which includes an HA Core restart).

### Root cause

HAOS starts HA Core **before** it starts add-on containers. So:
1. HA Core boots, loads the OLD integration from disk
2. App container boots, `integration.sh` copies NEW integration files to disk
3. Notification fires: "restart HA to load new code"

The notification is technically correct but feels redundant to users who
just restarted HAOS.

### Fix (`integration.sh`)

When `integration.sh` detects a version update and copies new files, it now
calls `POST http://supervisor/core/restart` to automatically restart HA Core.
HA restarts silently, loads the new integration, `_check_version_mismatch`
sees matching versions → no notification.

Fallback: if the supervisor API call fails (HTTP status ≠ 200), falls back
to the previous behaviour (manual notification + config entry reload).

The Python-side `_check_version_mismatch` in `__init__.py` is unchanged —
it remains the authoritative source for the repair issue and serves as a
safety net if the auto-restart path fails or if files are updated via HACS.

### Version bump
`3.1.12.5` → `3.1.12.6`

---



There is **one Dockerfile** (`tellsticklive/Dockerfile`) used by every
build workflow. The fix (lines 23–26: `apk add --no-cache --upgrade musl
musl-utils musl-dev`) is therefore applied to all of them:

| Workflow | How it builds | Fix applies? |
|---|---|---|
| `create-test-release.yaml` | calls `deploy.yaml` → same Dockerfile | ✅ Yes |
| `create-release.yaml` | calls `deploy.yaml` → same Dockerfile | ✅ Yes |
| `create-stable-release.yaml` | calls `deploy.yaml` with `is_stable: true` → same Dockerfile | ✅ Yes |
| `edge.yaml` (dev branch push) | builds directly from same Dockerfile | ✅ Yes |
| `deploy.yaml` (direct GitHub release event) | builds from same Dockerfile | ✅ Yes |

No per-workflow Dockerfile, no build matrix override, no conditional
execution that could bypass the fix. All five workflows are covered.

---

## Current state (end of session)

| Item | Status |
|------|--------|
| Docker build exit code 4 | ✅ Fixed (musl upgrade added) |
| Branch timeline file | ✅ Created (this file) |
| Convention in instruction files | ✅ Added to AGENTS.md + copilot-instructions.md |
| Create Test Release action | ✅ Should now work on any branch |
| Fix covers all release actions | ✅ Verified — single Dockerfile shared by all 5 workflows |

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

---

## Session — 2026-04-20: Fix persistent restart notification after HAOS restart (v3.1.12.9)

### Problem (user-reported)

After every HAOS restart the "Restart required — TellStick Local v3.1.12.8 installed
(currently loaded: v3.1.12.6)" notification kept appearing, even when nothing had been
updated. The user confirmed both the app and the integration UI showed v3.1.12.8, so
the notification was stale/re-fired unnecessarily.

### Root cause

`INTEGRATION_VERSION` in `const.py` was **never updated** alongside `manifest.json`
for versions 3.1.12.7 and 3.1.12.8. The constant was stuck at `"3.1.12.6"`.

At every HA startup, `_check_version_mismatch()` reads the on-disk `manifest.json`
(= 3.1.12.8) and compares it to the loaded `INTEGRATION_VERSION` (= 3.1.12.6). They
always differ → notification fires afresh every boot, regardless of whether any update
occurred. The user also saw the stale notification persist after restart because the
mismatch meant the `pn_async_dismiss` path was never reached (the re-fire overwrote it).

The comment at the top of `const.py` explicitly says **all four files must always
be identical**, but past commits only touched `manifest.json` and forgot `const.py`.

### Fix

Updated all four version fields to `3.1.12.9`:

| File | Old | New |
|------|-----|-----|
| `custom_components/tellstick_local/manifest.json` | 3.1.12.8 | 3.1.12.9 |
| `custom_components/tellstick_local/const.py` (INTEGRATION_VERSION) | 3.1.12.6 | 3.1.12.9 |
| `tellsticklive/rootfs/usr/share/tellstick_local/manifest.json` | 3.1.12.7 | 3.1.12.9 |
| `tellsticklive/rootfs/usr/share/tellstick_local/const.py` (INTEGRATION_VERSION) | 3.1.12.6 | 3.1.12.9 |

### After-fix behaviour

- **HAOS restart, no update:** integration.sh sees bundled = installed = 3.1.12.9 → skips
  copy → `_check_version_mismatch` sees match → calls `pn_async_dismiss` → stale
  notification cleared. No new notification created. ✓
- **Genuine app update to 3.1.12.x+1:** integration.sh copies new files → `_check_version_mismatch`
  detects mismatch → fires notification once. Auto-restart (or manual restart) loads
  new code where INTEGRATION_VERSION matches → match on next boot → notification cleared. ✓

---

## Session — 2026-04-20: Hide mirror entries from Add 433 MHz device hub picker (v3.1.12.10)

### Problem (user-reported)

When the user had both a primary TellStick and a mirror (range extender) entry
configured, the "Add 433 MHz device" config flow's hub picker showed the mirror
entry as a selectable option. Selecting it caused a confusing / broken flow
because mirror entries have no devices of their own.

### Fix

`config_flow.py`: filtered `async_step_add_rf_device_entry_selector` to exclude
mirror config entries (entries with `CONF_MIRROR_OF` set) from the hub picker.
Only primary entries are shown.

### Files changed

- `config_flow.py` — exclude mirror entries from hub picker
- `manifest.json` — version `3.1.12.9` → `3.1.12.10`
- All changes synced to bundled copy

---

## Session — 2026-04-20: Graceful abort when mirror entry selected in device picker (v3.1.12.11)

### Problem (user-reported)

After the v3.1.12.10 fix hid mirror entries from the picker, there was still a
path where a mirror entry could end up selected (e.g. via direct URL or stale
state). The resulting flow would silently do nothing or show a confusing error.

### Fix

`config_flow.py`: added an explicit `async_abort("mirror_is_secondary")` with a
clear user-facing message when a mirror entry is detected mid-flow.

Added `mirror_is_secondary` abort string to `strings.json` and
`translations/en.json`.

### Files changed

- `config_flow.py` — abort with clear message
- `strings.json` / `translations/en.json` — added `mirror_is_secondary` abort text
- `manifest.json` — version `3.1.12.10` → `3.1.12.11`
- Bundled `config_flow.py` synced (strings/translations not synced — CI copies
  them from source at build time)

---

## Session — 2026-04-20: Fix docker/login-action SHA failure in CI (v3.1.12.12)

### Problem (user-reported)

The "Create Test Release" action was failing. Root cause: `docker/login-action`
was pinned to a specific commit SHA that GitHub's tarball endpoint was failing
to resolve intermittently (transient download failure).

### Fix

Updated `docker/login-action` pin to `v4.1.0` (a current stable tag) in both
`deploy.yaml` and `edge.yaml`.

**Note:** This commit did NOT update `INTEGRATION_VERSION` in `const.py` —
it was left at `3.1.12.10` while `manifest.json` went to `3.1.12.12`.
This caused the same const.py drift bug documented in the v3.1.12.9 session
to recur immediately (repair issue fired on every boot again).

### Files changed

- `.github/workflows/deploy.yaml` — updated docker/login-action pin
- `.github/workflows/edge.yaml` — updated docker/login-action pin
- `manifest.json` — version `3.1.12.11` → `3.1.12.12`

---

## Session — 2026-04-20: Permanent fix for version drift + graceful restart repair (v3.1.12.13)

### Problems (user-reported)

1. "Restart required" repair issue still appearing after every restart — the
   const.py / manifest.json drift bug has now recurred **twice** (3.1.12.6 and
   3.1.12.10 both forgotten during version bumps).
2. The repair dialog only had "Ignore" — no way to take action from the dialog
   ("not very graceful abort").
3. Three sessions (v3.1.12.10, .11, .12) were missing from the timeline.

### Root cause of recurring drift

`INTEGRATION_VERSION` was a hardcoded string in `const.py`. Every version bump
required updating **four files** (two `manifest.json` + two `const.py`). The
const.py files were routinely forgotten.

### Fix 1 — Dynamic version read (permanent)

`INTEGRATION_VERSION` in `const.py` (both copies) now reads directly from
`manifest.json` at module import time:

```python
INTEGRATION_VERSION: str = _json.loads(
    (_pathlib.Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
)["version"]
```

- At import time, Python reads manifest.json from the same directory → frozen
  to the version that was on disk when HA started.
- If the app later overwrites manifest.json with a newer version,
  `INTEGRATION_VERSION` still holds the old value → mismatch detected ✓
- On HA restart, module re-imports → new version read → versions match → issue
  cleared ✓
- **Version bumps now only require updating the two `manifest.json` files.**
  `const.py` never needs to be touched for version bumps.

`ISSUE_RESTART` and `ISSUE_DEV_CHANNEL` moved from local `_ISSUE_*` constants
in `__init__.py` to exported constants in `const.py`, so `repairs.py` can
import them without a circular dependency.

### Fix 2 — Fixable repair with "Restart" button

- `repairs.py` (new): implements `async_create_fix_flow` + `RestartRepairFlow`
  that calls `homeassistant.restart` when the user clicks "Fix → Submit".
- `__init__.py`: `is_fixable=False` → `is_fixable=True`.
- `strings.json` / `translations/en.json`: added `fix_flow.step.init` strings
  for the restart confirmation form.

### Fix 3 — CI enforcement

New CI job `lint-integration-versions` in `ci.yaml` compares the `version`
field in both `manifest.json` files on every push/PR. If they differ, CI fails
with a clear error message pointing to both files.

### Files changed

| File | Change |
|------|--------|
| `custom_components/tellstick_local/const.py` | Dynamic version read; add `ISSUE_RESTART`, `ISSUE_DEV_CHANNEL` |
| `custom_components/tellstick_local/manifest.json` | `3.1.12.12` → `3.1.12.13` |
| `custom_components/tellstick_local/__init__.py` | Import `ISSUE_*` from const; `is_fixable=True`; remove local `_ISSUE_*` |
| `custom_components/tellstick_local/repairs.py` | New — fix flow for restart repair |
| `custom_components/tellstick_local/strings.json` | Add `fix_flow` step under `restart_required` |
| `custom_components/tellstick_local/translations/en.json` | Same |
| `tellsticklive/rootfs/usr/share/tellstick_local/const.py` | Same dynamic version read + issue constants |
| `tellsticklive/rootfs/usr/share/tellstick_local/manifest.json` | `3.1.12.10` → `3.1.12.13` |
| `tellsticklive/rootfs/usr/share/tellstick_local/__init__.py` | Synced from source |
| `tellsticklive/rootfs/usr/share/tellstick_local/repairs.py` | Synced from source |
| `tellsticklive/rootfs/usr/share/tellstick_local/strings.json` | Synced from source |
| `tellsticklive/rootfs/usr/share/tellstick_local/translations/` | Synced from source |
| `.github/workflows/ci.yaml` | New `lint-integration-versions` job |
| `docs/retrieve-rtl-conf-luxorparts-3.1.12.x.md` | Backfill v3.1.12.10–.13 sessions |

### What was documented

User confirmed: variable-brightness dimming does not work on ZNet/Net for arctech
`selflearning-dimmer` — only on Duo. The code already had the correct workaround
(sends TURNON+selflearning-dimmer model → firmware converts to DIM(255)), but the
user-facing docs did not mention this limitation.

### Files changed

- `README.md`:
  - Hardware status block: added note that arctech dimmers are on/off only on Net/ZNet
  - Added "Mixing Duo and Net/ZNet" bullet: use Duo as primary device
  - Supported devices: added "Arctech dimmer note" after Nexa note
  - Known limitations: added new section "Arctech dimmers on TellStick Net / ZNet — on/off only"
- `tellsticklive/DOCS.md`:
  - Added "⚠️ Arctech dimmers on TellStick Net / ZNet — on/off only" section after Luxorparts
- Version bumped: `3.1.12.7` → `3.1.12.8`

---

## Session — 2026-04-17: Remove arc_raw_test Proove dimmer test device (v3.1.12.7)

### What was removed

The `arc_raw_test` test device was added to empirically verify whether raw
S-byte payloads (with no `protocol` key) could make the ZNet LED blink.

**Confirmed finding:** Raw S-only packets generate **nothing** on ZNet/Net —
`handleSend()` raises `KeyError('protocol')` before the RF chip is reached.
Only the native dict path (with `protocol/model/house/unit/method` keys) works.

This was the last open question for arctech on ZNet. The test has served its
purpose, the result is documented in `docs/ZNET_PROTOCOL_PORTING_GUIDE.md`,
and the test device has been removed.

### Files changed

- `const.py`: removed `ARC_RAW_TEST_GROUP_UID/HOUSE/UNIT/VARIANTS` block
- `config_flow.py`: removed `ARC_RAW_TEST_*` imports, `"arc_raw_test"` menu option, `async_step_arc_raw_test()` method
- `button.py`: removed `ARC_RAW_TEST_VARIANTS` import, `"arc_raw_test_sequence"` entry from `_SEQ_MODELS`
- `net_client.py`: removed `_arctech_selflearning_on_off_pulse_train()` (test-only function) and the `:arc_raw` model suffix branch in the arctech encoder
- `strings.json` / `translations/en.json`: removed `arc_raw_test_sequence` button string, menu label, step definition
- All changes synced to bundled copy in `tellsticklive/rootfs/usr/share/tellstick_local/`
- `docs/ZNET_PROTOCOL_PORTING_GUIDE.md`: updated arctech row with confirmed finding
- Version bumped: `3.1.12.6` → `3.1.12.7`

### Note: Luxorparts untouched

The Luxorparts implementation (widget 20, catalog entry, LX raw encoder, all
switch/button/config_flow code) is **unchanged** — identical to the state in
`main`. Luxorparts currently only works on the Duo (native arctech selflearning
via the raw OOK-PWM encoder). Net/ZNet support is unverified.
