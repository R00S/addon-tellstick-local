# TellStick Local – Copilot Instructions

```
████████████████████████████████████████████████████████████████████████████████
█                                                                              █
█   🛑🛑🛑 READ THIS FIRST — VERSION BUMPING RULES 🛑🛑🛑                    █
█                                                                              █
█   manifest.json version = X.Y.Z.W                                           █
█                                                                              █
█   W = bump after each user input/response on the current branch             █
█   Z = bump only when the git branch name changes                            █
█   Y = minor feature release                                                 █
█   X = major release                                                          █
█                                                                              █
█   ⚠️  DO NOT hardcode a version here — it will always be stale.             █
█   ALWAYS read manifest.json to get the current version, then bump W.        █
█   Run `git branch --show-current` — same branch name → bump W only.        █
█   Z only changes when the branch name itself is different.                  █
█                                                                              █
█   config.yaml version MUST ALWAYS be 'dev' on branches (linter-enforced)    █
█                                                                              █
████████████████████████████████████████████████████████████████████████████████
```

```
████████████████████████████████████████████████████████████████████████████████
█                                                                              █
█   🛑 CRITICAL: SOURCE OF TRUTH FOR DIFFERENT DATA 🛑                        █
█                                                                              █
█   ADD-ON CONFIG (devices, protocols):                                        █
█     → Edit: tellsticklive/config.yaml                                        █
█     → Reflected in: tellsticklive/rootfs/etc/cont-init.d/telldusd.sh         █
█                                                                              █
█   INTEGRATION CONFIG (HA platforms, entities):                               █
█     → Edit: custom_components/tellstick_local/<platform>.py                  █
█     → Constants: custom_components/tellstick_local/const.py                  █
█                                                                              █
█   PROTOCOL: TEXT-BASED (telldusd socket encoding):                        █
█     → Edit: custom_components/tellstick_local/client.py                      █
█     → NEVER use binary framing — protocol is text-based                      █
█                                                                              █
████████████████████████████████████████████████████████████████████████████████
```

## Quick Commands

```bash
# Lint YAML files
yamllint tellsticklive/config.yaml

# Lint shell scripts (-s bash because of bashio shebang)
shellcheck -s bash tellsticklive/rootfs/etc/services.d/telldusd/run
shellcheck -s bash tellsticklive/rootfs/etc/cont-init.d/telldusd.sh

# Check Python syntax and unused imports
python -m py_compile custom_components/tellstick_local/*.py
python -m pyflakes custom_components/tellstick_local/

# Check integration version
grep '"version"' custom_components/tellstick_local/manifest.json
# Add-on config.yaml always reads 'dev' on branches — that is correct, see below
grep '^version:' tellsticklive/config.yaml

# Test integration loads and config flows work in a real HA instance
# (see "Integration testing against Home Assistant" below)
pip install homeassistant pyflakes
python tests/test_ha_integration.py
```

## Version Numbering — Two Files, Different Rules

There are **two version fields** and they are intentionally **different** on non-release branches:

| File                                              | Value on branch        | Value on release        |
| ------------------------------------------------- | ---------------------- | ----------------------- |
| `custom_components/tellstick_local/manifest.json` | real version `2.0.1.0` | same real version       |
| `tellsticklive/config.yaml`                       | **always `dev`**       | set by release workflow |

### Why `config.yaml` must be `dev` on branches

The CI runs `frenck/action-addon-linter` (the "Lint App" check). This linter enforces
that the app `version` field in `config.yaml` is the literal string `dev` on every
non-release branch. Putting a real version number there causes the linter to fail with:

```
Add-on version identifier must be 'dev'
```

The release workflow (`deploy.yaml`) replaces `dev` with the real version at release
time. **Do not change `config.yaml` version away from `dev`** — it will break CI.

### 🛑 You MUST bump `manifest.json` on every change

**Always increment `manifest.json` → `"version"` when making any code change.**

HACS and Home Assistant use the integration version to detect updates. If the version
does not change, users will silently receive the old cached integration — Home
Assistant will not reload it, HACS will not prompt for an update, and browsers will
not re-fetch any frontend assets. This has caused multiple silent broken releases in
similar projects.

```
□ EVERY commit with code changes → bump manifest.json "version": "X.Y.Z.W"
```

`tellsticklive/config.yaml` stays `version: dev` forever on branches.

### Version ticking scheme (`X.Y.Z.W`)

The version in `manifest.json` follows `X.Y.Z.W`:

| Digit | When to bump                                                             |
| ----- | ------------------------------------------------------------------------ |
| **W** | After each user input/response — always, on every change                 |
| **Z** | Only when the **git branch name changes** (different branch from before) |
| **Y** | Minor feature release                                                    |
| **X** | Major release                                                            |

**How to determine the current version:** always `grep '"version"' custom_components/tellstick_local/manifest.json` — never rely on a version written in these instructions (it will be stale). Then bump **W** for this prompt.

Example: branch `fix/my-feature` starts at `3.1.5.0`. Each user prompt bumps W → `3.1.5.1`, `3.1.5.2`, etc. A new branch `fix/other-thing` starts at `3.1.6.0` (Z bumped). The branch name is the only trigger for Z.

## What File to Edit for Each Change

| I want to change...                      | File to edit                                             |
| ---------------------------------------- | -------------------------------------------------------- |
| Device/protocol list in add-on           | `tellsticklive/config.yaml`                              |
| tellstick.conf generation logic          | `tellsticklive/rootfs/etc/cont-init.d/telldusd.sh`       |
| Integration install/update logic         | `tellsticklive/rootfs/etc/cont-init.d/integration.sh`    |
| telldusd startup / socat bridge          | `tellsticklive/rootfs/etc/services.d/telldusd/run`       |
| stdin service call handling              | `tellsticklive/rootfs/etc/services.d/stdin/run`          |
| TCP socket binary protocol (framing)     | `custom_components/tellstick_local/client.py`            |
| HA config flow (host/port entry)         | `custom_components/tellstick_local/config_flow.py`       |
| Hub setup / event dispatch               | `custom_components/tellstick_local/__init__.py`          |
| Base entity / device registry            | `custom_components/tellstick_local/entity.py`            |
| Switch entities                          | `custom_components/tellstick_local/switch.py`            |
| Light/dimmer entities                    | `custom_components/tellstick_local/light.py`             |
| Wireless sensor entities (temp/humidity) | `custom_components/tellstick_local/sensor.py`            |
| Device automation triggers               | `custom_components/tellstick_local/device_trigger.py`    |
| All domain constants                     | `custom_components/tellstick_local/const.py`             |
| UI strings (config flow labels, errors)  | `custom_components/tellstick_local/strings.json`         |
| English translations                     | `custom_components/tellstick_local/translations/en.json` |

---

## Project Overview

This repository provides local 433 MHz TellStick / TellStick Duo support for
Home Assistant — **no cloud, no Telldus Live account required**.

It has **two independent components** that work together:

### Component 1 — HAOS App (`tellsticklive/`)

> **Terminology note:** HAOS 2026.2 renamed "Add-ons" to "Apps" in the UI.
> The underlying Supervisor system, `config.yaml` format, and Docker container
> model are unchanged. "Add-on" and "App" refer to the same thing.

A Docker container managed by the HAOS Supervisor that:

- Builds `telldusd` from source and runs it inside the container
- Exposes `telldusd` over TCP via socat bridges:
  - **Port 50800** → `TelldusClient` UNIX socket (commands: turn on/off, dim)
  - **Port 50801** → `TelldusEvents` UNIX socket (events: RF button presses, sensor readings)
- Passes through the TellStick USB hardware via the `usb: true` config

**How to install:** HAOS Settings → Apps → three-dot menu → Add custom repository
→ `https://github.com/R00S/addon-tellstick-local` → category **App**.
**Not installed via HACS.**

The app also **automatically installs the companion integration** by copying it to
`/config/custom_components/tellstick_local/` at startup — no HACS step needed.

### Component 2 — HA Custom Integration (`custom_components/tellstick_local/`)

A Home Assistant integration that runs inside the HA Core Python process:

- Connects to the app's TCP sockets (host + ports 50800/50801)
- Subscribes to 433 MHz RF events from the TelldusEvents socket
- Builds a stable device identifier from RF parameters (`protocol_model_house_unit`)
- Auto-adds switch / light / sensor entities when a 433 MHz signal is received
  (controlled by the `automatic_add` option)
- Fires HA bus events and dispatcher signals for automations / device triggers

**How to install:** Automatically — the app copies it to `/config/custom_components/`
at startup. The Supervisor then fires a discovery notification: "New device found:
TellStick Local — Set up?" and the user clicks through the one-screen confirm flow.
**HACS is not required.** (HACS can still be used optionally for update management.)
**Not installed via the Supervisor Apps store.**

### Why you need both — and why they can't be merged

**This is the same architecture as Z-Wave JS, deCONZ, and Zigbee Home Automation.**
Both components run on the **same HAOS machine** — but HAOS enforces a hard separation
between two execution environments:

| Execution environment  | Who lives here                         | USB access? | HA API access? |
| ---------------------- | -------------------------------------- | ----------- | -------------- |
| Docker container (app) | `telldusd` C daemon, socat TCP bridges | ✅ Yes      | ❌ No          |
| HA Core Python process | Our integration, all HA entities       | ❌ No       | ✅ Yes         |

**Z-Wave JS does the exact same thing:**

- Z-Wave JS Server **app** → Docker container, USB passthrough, runs `zwave-js-server` (Node.js)
- Z-Wave JS **integration** → Python in HA Core, creates entities, connects to server via WebSocket

We do the exact same thing for TellStick:

- TellStick Local **app** → Docker container, USB passthrough, runs `telldusd` (C), exposes TCP
- TellStick Local **integration** → Python in HA Core, creates entities, connects via TCP

**Why the separation is unavoidable:**

| Constraint                                  | App                            | Integration                      |
| ------------------------------------------- | ------------------------------ | -------------------------------- |
| USB hardware passthrough (`usb: true`)      | ✅ Supervisor provides this    | ❌ Not available to integrations |
| Runs compiled C daemon (`telldusd`)         | ✅ Built from source in Docker | ❌ Can't run native daemons      |
| HA entities / config flow / device registry | ❌ Apps have no HA API access  | ✅ Integration's job             |
| Automations / device triggers               | ❌                             | ✅                               |

`telldusd` is a **compiled C daemon** that needs `cmake`, `gcc`, and `libftdi` to build —
it cannot run inside HA Core's Python process. And the TellStick USB device is only
accessible through the Supervisor's USB passthrough, which is only available to apps.

The integration uses a **pure asyncio TCP client** (no native libraries) to talk to the
TCP sockets the app exposes. It has zero Python dependencies outside stdlib + HA.

---

## Key Files

### HAOS App (`tellsticklive/`)

| File                                    | Purpose                                                                                       |
| --------------------------------------- | --------------------------------------------------------------------------------------------- |
| `config.yaml`                           | App metadata, version (`dev` on branches), device schema                                      |
| `Dockerfile`                            | Container build: compiles telldus-core from source, installs socat; bundles integration files |
| `rootfs/etc/cont-init.d/integration.sh` | Copies bundled integration to `/config/custom_components/` at startup                         |
| `rootfs/etc/cont-init.d/telldusd.sh`    | Generates `/etc/tellstick.conf` from add-on config at startup                                 |
| `rootfs/etc/services.d/telldusd/run`    | Starts `telldusd`, waits for UNIX sockets, launches socat bridges                             |
| `rootfs/etc/services.d/telldusd/finish` | Halts add-on if telldusd crashes unexpectedly                                                 |
| `rootfs/etc/services.d/stdin/run`       | Processes `hassio.addon_stdin` service calls (on/off/dim/list)                                |

### Custom Integration (`custom_components/tellstick_local/`)

| File                   | Purpose                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------- |
| `manifest.json`        | Domain, version, no external requirements (pure asyncio TCP client)                                     |
| `const.py`             | **SOURCE OF TRUTH** – domain constants, method bitmasks, device catalog, signal templates               |
| `client.py`            | **SOURCE OF TRUTH** – asyncio TCP client; telldusd text protocol (one-shot commands, persistent events) |
| `config_flow.py`       | Config flow: host/port entry, live connection validation, options flow                                  |
| `__init__.py`          | Hub setup, event subscription, dispatcher + HA bus event dispatch                                       |
| `entity.py`            | Base entity: device registry, state restore                                                             |
| `switch.py`            | Switch platform (on/off for codeswitch / selflearning-switch models)                                    |
| `light.py`             | Light platform (dim / on / off for selflearning-dimmer models)                                          |
| `sensor.py`            | Sensor platform (temperature, humidity from wireless sensors)                                           |
| `device_trigger.py`    | Device automation triggers: `turned_on` / `turned_off`                                                  |
| `strings.json`         | UI strings (config flow labels, error messages)                                                         |
| `translations/en.json` | English translations (mirrors strings.json)                                                             |

---

## Architecture: Communication Flow

```
433 MHz remote/sensor
        │ RF signal
        ▼
  TellStick USB hardware
        │ USB
        ▼
   telldusd daemon
        │ UNIX sockets
        ├─ /tmp/TelldusClient   (commands)
        └─ /tmp/TelldusEvents   (events)
        │
   socat bridges
        │ TCP
        ├─ port 50800  (commands)
        └─ port 50801  (events)
        │
HA custom integration (client.py)
        │ asyncio TCP
        ├─ command_port → turn_on / turn_off / dim
        └─ event_port  → raw RF events → dispatcher → entities
```

---

---

## telldusd Socket Protocol

The `client.py` file implements the telldusd socket protocol. Key facts:

- **Text-based, NOT binary.** Source: `telldus-core/common/Message.cpp`.
- Strings are encoded as: `<byte_length>:<utf8_text>` (e.g. `7:arctech`)
- Integers are encoded as: `i<decimal_value>s` (e.g. `i42s`)
- **Command socket** (port 50800): each command requires a **new TCP connection**
  because telldusd creates a one-shot handler per UNIX-socket connection (reads
  one message, responds with `\n`-terminated reply, closes).
- **Event socket** (port 50801): persistent connection. telldusd pushes events
  to all connected clients using the same text encoding (no `\n` terminator;
  messages are self-delimiting).
- Event types are identified by **string names** (not integer IDs):
  - `TDRawDeviceEvent` – raw RF event string (key:value pairs separated by `;`)
  - `TDDeviceEvent` – named device state change
  - `TDSensorEvent` – sensor reading
  - `TDDeviceChangeEvent` – device config change (consumed but not dispatched)

**NEVER duplicate this protocol logic outside `client.py`.**
**NEVER use binary framing (struct.pack / big-endian) — the protocol is text.**

### Raw RF event format

Raw events arrive as a semicolon-separated `key:value` string, for example:

```
class:command;protocol:arctech;model:selflearning;house:A;unit:1;method:turnon;
```

The stable device UID is built from: `protocol_model_house_unit`.

---

## Supported 433 MHz Protocols

The protocols below are compiled into `telldusd` (telldus-core). The list is
**fixed in software** — unlike RFXtrx (which has updateable firmware and supports
many more protocols), TellStick Duo's protocol coverage depends entirely on what
is implemented in telldus-core.

The **RX** column indicates whether the TellStick Duo can **receive** signals from
that device (i.e. the protocol has a `decodeData()` implementation in telldus-core).
Without RX support, the device can only be controlled (TX), not auto-discovered.

| Protocol       | RX  | TX  | Typical brands / device types                                                                                                                                                                                                                   |
| -------------- | --- | --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `arctech`      | ✅  | ✅  | Nexa (switches, dimmers, remotes, buttons), KlikAanKlikUit (KAKU), Intertechno, Proove, HomeEasy, CoCo Technologies, Chacon, Byebye Standby, Rusta, Kappa — models: `codeswitch`, `selflearning-switch`, `selflearning-dimmer`, `bell`, `kp100` |
| `everflourish` | ✅  | ✅  | Everflourish / Rusta selflearning switches                                                                                                                                                                                                      |
| `fineoffset`   | ✅  | —   | **Nexa thermometers/weather sensors** (e.g. LMST-606, WDS-100), Fine Offset WH1080/WH3080 — temperature & humidity auto-discovered when received                                                                                                |
| `hasta`        | ✅  | ✅  | Hasta motorised blinds/screens                                                                                                                                                                                                                  |
| `mandolyn`     | ✅  | ✅  | Mandolyn/Summerbird switches                                                                                                                                                                                                                    |
| `oregon`       | ✅  | —   | Oregon Scientific weather sensors — temperature, humidity, rain, wind, UV, pressure                                                                                                                                                             |
| `sartano`      | ✅  | ✅  | Sartano / Kjell & Company switches (identical to x10)                                                                                                                                                                                           |
| `waveman`      | ✅  | ✅  | Waveman switches (old arctech codeswitch family)                                                                                                                                                                                                |
| `x10`          | ✅  | ✅  | X10 protocol switches                                                                                                                                                                                                                           |
| `brateck`      | —   | ✅  | Brateck motorised blinds (TX only — cannot auto-discover)                                                                                                                                                                                       |
| `comen`        | —   | ✅  | Comen devices (TX only — cannot auto-discover)                                                                                                                                                                                                  |
| `fuhaote`      | —   | ✅  | Fuhaote remote switches (TX only — cannot auto-discover)                                                                                                                                                                                        |
| `ikea`         | —   | ✅  | IKEA Koppla 433 MHz remotes (TX only — cannot auto-discover)                                                                                                                                                                                    |
| `risingsun`    | —   | ✅  | Rising Sun remote switches (TX only — cannot auto-discover)                                                                                                                                                                                     |
| `silvanchip`   | —   | ✅  | Silvanchip devices (TX only — cannot auto-discover)                                                                                                                                                                                             |
| `upm`          | —   | ✅  | UPM/Esic sensors (TX only in telldus-core — not auto-discoverable)                                                                                                                                                                              |
| `yidong`       | —   | ✅  | Yidong remotes (TX only — cannot auto-discover)                                                                                                                                                                                                 |

**TX only means:** the device can be controlled from HA, but it cannot be
auto-discovered by pressing a button. To add a TX-only device, the user must
manually configure it (protocol, house, unit code) in the app's `options.devices`
or the future options-flow teach step.

### TellStick Duo vs RFXtrx

| Aspect                   | TellStick Duo                                            | RFXtrx433E                           |
| ------------------------ | -------------------------------------------------------- | ------------------------------------ |
| Protocol coverage        | ~17 protocols (fixed in telldus-core)                    | 100+ protocols (firmware-updateable) |
| Receive (RX) capability  | 9 protocols                                              | Most supported protocols             |
| Protocol list updatable? | No (requires telldus-core fork)                          | Yes (firmware update from RFXCOM)    |
| Smart home focus         | Nordic/European brands (Nexa, KAKU, Proove)              | Very broad, incl. US/AU brands       |
| Weather sensors          | Oregon Scientific, Fine Offset (incl. Nexa thermometers) | Oregon Scientific + many more        |
| Blind control            | Hasta, Brateck                                           | Somfy RTS + many more                |

**Conclusion:** TellStick Duo is a solid choice for the popular Nordic/European
arctech ecosystem (Nexa, KAKU, Intertechno, Proove) and Oregon Scientific sensors.
For environments needing many different brands or future firmware-added protocols,
RFXtrx is the better choice. This project makes TellStick Duo work as well as it
possibly can within telldus-core's constraints.

Common model strings: `codeswitch`, `selflearning-switch`, `selflearning-dimmer`,
`bell`, `kp100`, `ecosavers`, `temperature`, `temperaturehumidity`

### ⚠️ Multi-protocol detection (one button = multiple events)

`telldusd` runs **all** protocol decoders on every RF signal. A single button press
from one remote can produce **multiple** raw device events with different protocol
interpretations. This is normal behaviour, not a bug.

**Verified example — Luxorparts 50969 remote (A-on button):**

| #   | device_uid                         | protocol     | model        | house   | unit |
| --- | ---------------------------------- | ------------ | ------------ | ------- | ---- |
| 1   | `arctech_selflearning_2673666_1`   | arctech      | selflearning | 2673666 | 1    |
| 2   | `everflourish_selflearning_3264_1` | everflourish | selflearning | 3264    | 1    |
| 3   | `waveman_codeswitch_a_10`          | waveman      | codeswitch   | A       | 10   |

The **correct** interpretation for this remote is **arctech / selflearning-switch**.
The everflourish and waveman detections are false positives caused by similar bit
patterns. The discovery flow will show all three as separate "Discovered" devices —
the user should only add the arctech one.

**Luxorparts receivers accept arctech/selflearning** — confirmed by user testing with
TellStick ZNet (which also uses telldus-core). The Homey app (se.luxorparts-1) uses
its own proprietary encrypted protocol stack, but that is Homey-specific — the actual
RF signal is standard arctech selflearning.

### Luxorparts protocol deep-dive (verified from source code)

The Homey `se.luxorparts-1` app defines a **separate proprietary protocol**:

- **Signal**: SOF=[375µs, 2250µs], bit 0=[375µs, 1125µs], bit 1=[1125µs, 375µs]
- **Payload**: 24 bits (3 bytes) — 16-bit address + 2-bit count + 1-bit state + 5-bit unit
- **Encryption**: Nibble substitution cipher (two 16-element lookup tables) + XOR chain
  (see `lib/PayloadEncryption.js`)

**This is NOT arctech selflearning.** Arctech selflearning is:

- 26-bit house + 1-bit group + 1-bit on/off + 4-bit unit = 32+ data bits
- T-packet timing: T0=127(~1270µs), T1=255(~2550µs), T2=24(~240µs), T3=1(~10µs)
- Manchester-like encoding with ~240µs/~1270µs pulse durations

**BUT Luxorparts receivers are dual-protocol**: they accept BOTH the proprietary
Luxorparts signal AND standard arctech/selflearning. Self-learning 433 MHz receivers
memorize whatever bit pattern they hear during learn mode. TellStick ZNet uses
telldus-core's arctech selflearning to control them — confirmed by user.

### Critical bug found: vendor suffix in model name

Device catalog entries include a vendor suffix (e.g. `selflearning-switch:luxorparts`).
This suffix is for display/matching in the integration only. When registering devices
with telldusd, the suffix MUST be stripped because telldusd's `ProtocolNexa::methods()`
only recognizes `selflearning-switch` (without suffix). If the full
`selflearning-switch:luxorparts` is passed as the model:

1. `methods()` returns 0 (no recognized model)
2. `isMethodSupported(TELLSTICK_LEARN)` returns METHOD_NOT_SUPPORTED
3. Learn signal silently fails → receiver never learns the code
4. On/off commands also fail → device appears dead

**Fix**: `client.py::add_device()` strips vendor suffix via `model.split(":")[0]`
before calling `tdSetModel`.

### Critical bug found: UID mismatch in synthetic events

When the "Add device" flow dispatches a synthetic `RawDeviceEvent` to create the
entity, the model in the raw string MUST be the RF-normalized name (e.g.
`selflearning`), NOT the catalog name (e.g. `selflearning-switch:luxorparts`).

`build_device_uid()` normalizes: `selflearning-switch:luxorparts` → `selflearning`
`RawDeviceEvent.device_id` does NOT normalize — it uses whatever model is in the raw string.

If the synthetic event uses the catalog model, the entity gets a different UID than
what's stored in `device_id_map`. Result: `device_id_map.get(uid)` returns `None`,
and `async_turn_on()` silently skips the command (Duo doesn't blink).

**Fix**: `config_flow.py::async_step_confirm()` uses `normalize_rf_model()` to
convert the catalog model to the RF-compatible name before building the synthetic event.

**Symptom**: Learn/teach works (Duo blinks) but on/off does nothing (Duo silent).
This is because `learn()` uses `telldusd_id` directly, but `turn_on()`/`turn_off()`
look up the device via the mismatched UID.

If learning still fails on TellStick Duo, the most likely cause is insufficient signal
repetitions. The R-prefix Dockerfile patch (adding firmware-level repeats for
pid 0x0c31) addresses this.

**Impact on integration code:**

- Discovery must deduplicate per `device_uid` (each UID is unique per protocol
  interpretation, so three distinct discoveries fire — this is correct).
- The `_discovered_uids` set in `__init__.py` prevents the same UID from
  triggering duplicate discovery flows within a single session.

### TellStick ZNet MQTT plugin confirms arctech/selflearning

The ZNet MQTT plugin (`quazzie/tellstick-plugin-mqtt-hass`) uses telldus-core's
Python SDK internally: `device.command(Device.TURNON)` → `tdTurnOn()`. The ZNet
configures Luxorparts as arctech/selflearning-switch and it works. This confirms:

- The protocol IS arctech/selflearning (not proprietary Luxorparts encryption)
- The same `tdTurnOn`/`tdTurnOff` commands we send work on ZNet
- The Duo should work identically once the UID mismatch is fixed

### Future feature: Raw Record & Replay (bypasses protocol decoding)

**The user explicitly requested this feature for future implementation.**

`telldusd` always decodes received signals into protocol parameters (arctech,
everflourish, waveman, etc.) before exposing them. One button press can trigger
**multiple** protocol decoders simultaneously, creating multiple "phantom" devices.
Example: Luxorparts 50969 A-on → 3 devices (arctech, everflourish, waveman).

A **raw record/replay** approach would bypass protocol decoding entirely:

**How it works (verified from telldus-core source):**

1. **Receive raw:** TellStick Duo firmware sends raw pulse data via `+R` prefix.
   `processData()` in `TellStick_libftdi.cpp:129` calls `publishData()` which
   emits the raw pulse string **before** any protocol decoding.
   (Compare: `+W` prefix → `decodePublishData()` → `Protocol::decodeData()` →
   protocol-decoded events. This is the decoded path we currently use.)

2. **Send raw:** `tdSendRawCommand(const char *command, int reserved)` sends a
   raw firmware command string directly to the TellStick hardware via
   `controller->send()`. The string format is TellStick firmware pulse encoding,
   e.g. `S$k$k$k$k$k$k$k$k$k$k$k$k$k$k$k$k$k$k$kk$$kk$$kk$$}+`
   (from `tdtool --raw` documentation).

3. **No protocol encoding/decoding** — the exact received waveform is replayed.

**Why this matters:**

- Works for **any** 433 MHz device, even unrecognized protocols
- No multi-protocol phantom devices (one button = one recorded signal)
- Could solve Luxorparts if the arctech/selflearning approach fails

**Implementation requirements:**

- Expose `+R` raw data through the event socket (or a new raw socket)
- Add `tdSendRawCommand` to `client.py`
- New UI flow: "Record" → press remote button → capture `+R` data → "Replay"
- Store raw ON/OFF pulse strings per device

**NOT YET IMPLEMENTED — queued for future development.**

---

## Testing

### Integration testing against Home Assistant

The integration can be tested against a real Home Assistant instance **without**
TellStick hardware. Install HA Core as a Python package and run the test script:

```bash
pip install homeassistant pyflakes
python tests/test_ha_integration.py
```

The test script (`tests/test_ha_integration.py`) boots a minimal HA instance,
copies `custom_components/tellstick_local/` into a temp config directory, and
verifies:

1. **Integration loads** — `loader.async_get_integration()` finds it in custom_components
2. **Config flow imports** — no broken imports prevent the module from loading
3. **User config flow** — `async_step_user` shows the host/port form
4. **Hassio discovery flow** — `async_step_hassio` → `hassio_confirm` form
5. **OptionsFlow** — instantiates without the deprecated `config_entry` parameter
6. **All platform modules** — client, const, entity, switch, light, sensor, device_trigger

This catches the most common integration-breaking issues:

- **Removed HA imports** — e.g. `HassioServiceInfo` moved from
  `homeassistant.components.hassio` to `homeassistant.helpers.service_info.hassio`
- **Deprecated API patterns** — e.g. OptionsFlow `self.config_entry = config_entry`
  explicit assignment removed in HA 2025.12
- **Syntax errors or typos** in any module

> **Note:** The test uses whatever HA version `pip install homeassistant` provides.
> If the user reports issues on a newer HA version, check the
> [HA developer blog](https://developers.home-assistant.io/blog/) for breaking
> changes and update imports accordingly.

### Hardware testing on real HAOS

Testing is manual on real HAOS with TellStick hardware:

1. Create a GitHub release from the branch using the **Create Test Release** workflow
   (`.github/workflows/create-test-release.yaml`)
2. Install the **HAOS app** from this repository:
   HAOS Settings → Apps → Add custom repository → category **App**
3. Install the **integration** via HACS:
   HACS → Add custom repository → category **Integration** → install the test version
4. Restart Home Assistant
5. Add the **TellStick Local** integration via Settings → Devices & Services
6. Enable **Automatically add new devices** in the integration options
7. Press a 433 MHz remote — the device should appear in HA automatically

---

## Common Mistakes to Avoid

1. ❌ Editing the integration without checking the actual `client.py` framing first
2. ❌ Changing `const.py` event type IDs without verifying against telldusd source
3. ❌ Forgetting to bump `manifest.json` version — HACS/HA won't detect the update and will silently keep the old cached version. AND ❌ Bumping `config.yaml` version away from `dev` — it must stay `dev` on branches (linter enforced)
4. ❌ Using deprecated HA APIs — check HA 2024.1+ compatibility
5. ❌ Adding Telldus Live / cloud dependencies — this is intentionally local-only
6. ❌ **FABRICATING method/property names instead of reading the source code** (see below)

---

## 🛑 Known HA Breaking Changes (verified the hard way)

These are **real breaking changes that broke this integration in production**.
Always check the [HA developer blog](https://developers.home-assistant.io/blog/)
for new ones when a user reports failures on a newer HA version.

### `HassioServiceInfo` import moved (HA 2025.11)

The old import was **removed** (not just deprecated) in HA Core 2025.11:

```python
# ❌ OLD — removed in HA 2025.11, causes ImportError:
from homeassistant.components.hassio import HassioServiceInfo

# ✅ NEW — required since HA 2025.2, sole path since 2025.11:
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
```

Same pattern applies to all ServiceInfo classes: `DhcpServiceInfo`,
`SsdpServiceInfo`, `UsbServiceInfo`, `ZeroconfServiceInfo` — all moved from
`homeassistant.components.<type>` to `homeassistant.helpers.service_info.<type>`.

### OptionsFlow `config_entry` explicit assignment (HA 2025.12)

Passing `config_entry` to `OptionsFlow.__init__` and setting
`self.config_entry = config_entry` was **removed** in HA 2025.12:

```python
# ❌ OLD — raises error in HA 2025.12+:
class MyOptionsFlow(OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry  # ← BREAKS

# ✅ NEW — framework auto-provides self.config_entry after init:
class MyOptionsFlow(OptionsFlow):
    def __init__(self):
        self._my_state = some_default
    # Access self.config_entry in step methods (NOT in __init__)
```

Also update `async_get_options_flow` to not pass the entry:

```python
return MyOptionsFlow()  # ✅ no argument
```

### How to detect these early

**Always run the integration test** after any change to integration Python code:

```bash
pip install homeassistant pyflakes
python tests/test_ha_integration.py
```

If a new HA version breaks an import, the test will fail immediately with the
exact `ImportError` or `TypeError`.

---

## 🛑 Shell Script Pitfalls (Alpine / BusyBox)

The add-on container runs **Alpine Linux with BusyBox**. Many GNU tools behave
differently or are missing entirely.

### `grep -P` does not exist

BusyBox `grep` does **not** support `-P` (Perl regex). This includes `\K`,
lookahead, lookbehind, and other PCRE features. Commands using `grep -oP` will
**silently fail** with exit code 2.

```bash
# ❌ BROKEN in Alpine — grep -P not supported:
VERSION=$(grep -oP '"version":\s*"\K[^"]+' manifest.json)

# ✅ CORRECT — use jq (always available via bashio):
VERSION=$(jq -r '.version' manifest.json)
```

**Rule:** For JSON parsing in shell scripts, **always use `jq`**, never `grep`.
`jq` is guaranteed available in all bashio-based add-on containers.

### Other BusyBox gotchas

- `sed -i` works but some GNU extensions don't (e.g. `\x00` hex escapes)
- `find` lacks `-printf` — use `-exec` instead
- `date` lacks `--date` — use busybox-compatible format strings
- No `realpath` — use `readlink -f` instead

---

## 🛑 NEVER Fabricate Code — Always Read the Source First

**This is the #1 cause of failed releases.** AI agents tend to generate
plausible-sounding method names from patterns instead of reading the actual
source code.

### The Rule

When writing ANY new code that calls existing methods or references existing properties:

1. **OPEN and READ the actual source file** where the method/property is defined
2. **FIND the real method name** by reading the code, not by guessing from patterns
3. **COPY the exact name** from the source into your new code

### What NOT to Do

- ❌ Guess method names from naming patterns
- ❌ Assume a method exists because "it should" or "it makes sense"
- ❌ Write code that references methods you haven't verified exist in the codebase

### Success Rate Impact

| Approach                                           | Success Rate |
| -------------------------------------------------- | ------------ |
| Code where source was READ first                   | 80–95%       |
| Code with FABRICATED names (guessed from patterns) | **0%**       |

---

## Terms of Reference (ToR)

### Objective

Make the **TellStick Duo USB stick** work in Home Assistant OS exactly like other
433 MHz receivers do (e.g. RFXtrx) — entirely through the **HA GUI and HA companion
app** (Android/iOS), locally, with no cloud, no YAML editing, and no separate web
server.

The TellStick Duo is a USB 433 MHz transceiver (receive _and_ transmit).
`telldusd` is the C daemon that drives it. This project exposes `telldusd` to HA
via TCP and wraps it in a native HA integration.

---

### User Experience Goals

Everything happens inside HA's own UI: **Settings → Devices & Services →
TellStick Local → Configure**. The HA companion app (Android/iOS) uses the same UI
— no browser required, no separate web server, no ingress panel.

| Capability                   | How it looks in HA UI                                                                                                                                                       |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Automatic install prompt** | Install the app → HA automatically pops up "New device found: TellStick Local — Set up?"                                                                                    |
| **Press-to-discover**        | Enable "Automatically add new devices" in integration options → press any 433 MHz remote/sensor → device appears in HA with the correct entity type (switch, light, sensor) |
| **Self-learning teach**      | Options → "Add device" → pick protocol + generate house/unit code → put receiver in learn mode → click Send → receiver learns the code → device appears in HA (no YAML)     |
| **GUI-only management**      | All add / rename / remove through HA UI — no YAML, no config file, no restart                                                                                               |
| **Local push**               | RF events arrive in real time via TCP event stream; no polling, no cloud                                                                                                    |
| **Automation triggers**      | Any 433 MHz button press fires a device trigger usable directly in HA automations                                                                                           |
| **Companion app**            | Identical UX in the HA Android/iOS app — same config flows, same device cards                                                                                               |
| **No Telldus Live**          | Zero cloud, zero account, zero internet dependency                                                                                                                          |

---

### Supported Devices

`telldusd` (telldus-core) implements 17 protocols. **RX** = TellStick Duo can
receive signals from the device (can auto-discover by pressing a button). **TX** =
can only send commands — device must be manually added.

#### Auto-discoverable (RX capable) — press button → appears in HA

| Protocol                          | Entity type(s)                               | Example brands / devices                                                             |
| --------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------ |
| `arctech` — `codeswitch`          | Switch                                       | Old Nexa, KAKU dial-based remotes and wall switches                                  |
| `arctech` — `selflearning-switch` | Switch                                       | Nexa, KAKU, Intertechno, Proove, HomeEasy, Chacon, CoCo                              |
| `arctech` — `selflearning-dimmer` | Light (dimmer)                               | Nexa, Proove, KAKU dimmers                                                           |
| `arctech` — `bell`                | Event                                        | Nexa doorbell                                                                        |
| `everflourish`                    | Switch                                       | Everflourish, Rusta selflearning                                                     |
| `hasta`                           | Switch/Cover                                 | Hasta motorised blinds                                                               |
| `mandolyn`                        | Switch                                       | Mandolyn / Summerbird                                                                |
| `sartano`                         | Switch                                       | Sartano, Kjell & Company                                                             |
| `waveman`                         | Switch                                       | Waveman (old arctech family)                                                         |
| `x10`                             | Switch                                       | X10 wall switches                                                                    |
| `fineoffset`                      | Sensor (temp/humidity)                       | **Nexa** LMST-606 / WDS-100 thermometers, Fine Offset WH1080/WH3080 weather stations |
| `oregon`                          | Sensor (temp/humidity/rain/wind/UV/pressure) | Oregon Scientific weather sensors                                                    |

> **Nexa spans two protocols:** Nexa _switches, dimmers, remotes and buttons_ use
> `arctech` (RX+TX). Nexa _thermometers and weather sensors_ (LMST-606, WDS-100 etc.)
> use `fineoffset` (RX only — sensor data arrives, no commands can be sent).

#### TX only — can be controlled but NOT auto-discovered

These devices can be turned on/off from HA, but they cannot be discovered by
pressing a button — they must be manually added (protocol + house + unit code).

| Protocol     | Entity type(s) | Example brands / devices                            |
| ------------ | -------------- | --------------------------------------------------- |
| `brateck`    | Cover          | Brateck motorised blinds                            |
| `comen`      | Switch         | Comen devices                                       |
| `fuhaote`    | Switch         | Fuhaote remotes                                     |
| `ikea`       | Switch         | IKEA Koppla 433 MHz                                 |
| `risingsun`  | Switch         | Rising Sun remotes                                  |
| `silvanchip` | Switch/Cover   | Silvanchip devices                                  |
| `upm`        | —              | UPM/Esic (TX only in telldus-core — not receivable) |
| `yidong`     | Switch         | Yidong remotes                                      |

#### Hardware limitation vs RFXtrx

TellStick Duo supports **fewer protocols** than RFXtrx and the list is **fixed**
(no firmware updates). RFXtrx433E has 100+ protocols and regular firmware updates.
TellStick Duo is strong for Nordic/European brands (Nexa, KAKU, Proove, Intertechno)
and Oregon Scientific sensors. For broader protocol coverage, RFXtrx is the better
choice.

---

### How the Two Components Fit Together

```
TellStick Duo USB
      │  USB passthrough (Supervisor only — no integration can get this)
      ▼
┌─────────────────────────────────────────────────┐
│  HAOS App  (tellsticklive/)                     │  ← Install via Supervisor
│  Docker container, Supervisor-managed           │     Settings → Apps →
│  • Builds + runs telldusd (compiled C daemon)   │     Add custom repository
│  • socat bridges: TCP 50800 (cmds), 50801 (evt) │
│  • discovery: tellstick_local → triggers setup  │
└────────────────────┬────────────────────────────┘
                     │ TCP  (host: app slug, ports 50800/50801)
                     ▼
┌─────────────────────────────────────────────────┐
│  HA Integration  (custom_components/            │  ← Install via HACS
│                   tellstick_local/)             │     custom repository
│  Pure asyncio, zero native dependencies         │
│  • Config flow (Supervisor auto-offer on start) │
│  • Receives raw RF events → auto-adds entities  │
│  • Sends on/off/dim commands via TCP            │
│  • Options flow: teach self-learning devices    │
│  • Device triggers for automations             │
└─────────────────────────────────────────────────┘
```

**Why both are required — they cannot be merged:**

> **This is the same architecture as Z-Wave JS (and deCONZ, Zigbee2MQTT broker + integration).**
> Both components run on the **same HAOS machine**. The split is not about "network distance" —
> it is about two different execution environments that HAOS enforces:
>
> - The **app** lives in a Docker container → the only place USB passthrough works.
> - The **integration** lives in HA Core's Python process → the only place HA entities can be created.
>
> There is no way to put USB passthrough code into a Python integration, and no way to put
> HA entity-creation into a Docker container. The TCP link (even over localhost) is the
> only bridge between them.

| Constraint                         | App (Docker)           | Integration (Python)           |
| ---------------------------------- | ---------------------- | ------------------------------ |
| USB hardware passthrough           | ✅ Supervisor provides | ❌ Unavailable to integrations |
| Run compiled C daemon (`telldusd`) | ✅ Built in Docker     | ❌ Cannot run native binaries  |
| HA entities / device registry      | ❌ No HA API access    | ✅ Integration's job           |
| Config flow / options flow         | ❌                     | ✅                             |
| HA companion app / automations     | ❌                     | ✅                             |

---

### Out of Scope (Non-Goals)

- ❌ **Telldus Live / any cloud** — will never return
- ❌ **External telldusd** — TellStick USB must be in the HAOS machine; no remote setup
- ❌ **`configuration.yaml`-based setup** — config flow only
- ❌ **Separate web server or ingress panel** — everything is native HA UI
- ❌ **TellStick Net (LAN device)** — USB Duo only
- ❌ **Firmware flashing** — out of scope
- ❌ **HAOS older than 2026.2** — no backward compatibility

---

### Reference Implementations

HA core is **Apache 2.0** licensed. This project is **GPL v3**. Apache 2.0 code
can be incorporated into GPL v3 with attribution (see `NOTICE`).

| Project                  | What to borrow                                                                                                                                                         |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`rfxtrx`** (HA core)   | **Primary reference.** 433 MHz, auto-add, options-flow device management (add by listening or by event code), device triggers with command subtypes, entity base class |
| **`rflink`** (HA core)   | Asyncio TCP protocol handling, auto-add from received messages                                                                                                         |
| **`zwave_js`** (HA core) | `async_step_hassio` — Supervisor discovery flow (app starts → HA auto-offers integration setup)                                                                        |

When adapting HA core code: add a file-level comment noting the source URL and
Apache 2.0 license. Update `NOTICE`.

---

### Implementation Phases

| Phase                         | Status  | What it delivers                                                                                                                                      |
| ----------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1 – Foundation**            | ✅ Done | App: no Telldus Live, TCP 50800/50801. Integration: config flow, auto-add, switch/light/sensor entities, device triggers                              |
| **2 – Supervisor auto-setup** | ✅ Done | `discovery: tellstick_local` in app → `async_step_hassio` in integration → app start triggers HA setup prompt automatically                           |
| **3 – Self-learning teach**   | ✅ Done | Options flow "Add device": pick protocol, generate house+unit code, send pairing signal via TCP, device appears in HA (model: `rfxtrx` options flow)  |
| **4 – Full GUI device mgmt**  | ✅ Done | Remove/re-teach via HA UI; devices persist in `entry.options["devices"]`; re-registered with telldusd on startup; auto-add suppressed for stored UIDs |

---

### Development Workflow

- `main` for stable releases; feature branches for new development
- **Bump `manifest.json` version on every code change** — HACS and HA use it to
  detect updates; browsers cache old versions if it doesn't change
- `tellsticklive/config.yaml` version stays `dev` on all branches (linter rule)
- Use **Create Test Release** workflow for prerelease HACS testing
- CI: yamllint, shellcheck, hadolint, pyflakes, Prettier, zizmor on every push

---

## MCP Tools Available

You have access to the ha-dev-platform orchestrator via MCP. Use these tools for testing:

- **`create_test_release(repo, branch, version_bump)`** — Create a pre-release for HACS testing.
- **`deploy_to_ha(repo, version)`** — Install via HACS, restart HA, verify integration loads.
- **`run_tests(scenarios_yaml)`** — Execute test scenarios (pass YAML from `tests/ha-tests-integration.yaml`). The file exists at `tests/ha-tests-integration.yaml`.
- **`get_ha_logs(domain, since_minutes)`** — Get filtered error logs when debugging failures.
- **`reset_ha_environment(domain)`** — Remove integration and restart to clean state.

## Testing Workflow

When asked to test or when you need to verify changes:

1. Create a test release from the current branch.
2. Deploy to the dev HA instance via HACS.
3. Run the test scenarios.
4. If tests fail, check logs and fix the code.
5. Repeat until all tests pass.

## Test Scenario Format

Test scenarios use the YAML format defined in the ha-dev-platform. See `tests/ha-tests-integration.yaml` for this project's test definitions.
