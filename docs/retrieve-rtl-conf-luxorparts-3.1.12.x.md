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

## Pending / future work on this branch

- [ ] Retrieve RTL-433 conf for Luxorparts (original branch purpose — not yet
  started; user to confirm scope)
