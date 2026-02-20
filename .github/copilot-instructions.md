# TellStick Local – Copilot Instructions

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
█   PROTOCOL BINARY FORMAT (telldusd socket encoding):                         █
█     → Edit: custom_components/tellstick_local/client.py                      █
█     → NEVER duplicate framing logic elsewhere                                 █
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

# Check version consistency (both must match)
grep '"version"' custom_components/tellstick_local/manifest.json
grep '^version:' tellsticklive/config.yaml
```

## What File to Edit for Each Change

| I want to change...                        | File to edit                                             |
|--------------------------------------------|----------------------------------------------------------|
| Device/protocol list in add-on             | `tellsticklive/config.yaml`                              |
| tellstick.conf generation logic            | `tellsticklive/rootfs/etc/cont-init.d/telldusd.sh`       |
| telldusd startup / socat bridge            | `tellsticklive/rootfs/etc/services.d/telldusd/run`       |
| stdin service call handling                | `tellsticklive/rootfs/etc/services.d/stdin/run`          |
| TCP socket binary protocol (framing)       | `custom_components/tellstick_local/client.py`            |
| HA config flow (host/port entry)           | `custom_components/tellstick_local/config_flow.py`       |
| Hub setup / event dispatch                 | `custom_components/tellstick_local/__init__.py`          |
| Base entity / device registry              | `custom_components/tellstick_local/entity.py`            |
| Switch entities                            | `custom_components/tellstick_local/switch.py`            |
| Light/dimmer entities                      | `custom_components/tellstick_local/light.py`             |
| Wireless sensor entities (temp/humidity)   | `custom_components/tellstick_local/sensor.py`            |
| Device automation triggers                 | `custom_components/tellstick_local/device_trigger.py`    |
| All domain constants                       | `custom_components/tellstick_local/const.py`             |
| UI strings (config flow labels, errors)    | `custom_components/tellstick_local/strings.json`         |
| English translations                       | `custom_components/tellstick_local/translations/en.json` |

---

## Project Overview

This repository provides local 433 MHz TellStick / TellStick Duo support for
Home Assistant — **no cloud, no Telldus Live account required**.

It has two parts:

### 1. Add-on (`tellsticklive/`)

Runs the `telldusd` daemon inside a Docker container and exposes it over TCP
via socat bridges:

- **Port 50800** → `TelldusClient` UNIX socket (commands: turn on/off, dim)
- **Port 50801** → `TelldusEvents` UNIX socket (events: RF button presses,
  sensor readings)

USB passthrough to the TellStick hardware is enabled via the add-on config.

### 2. Custom Integration (`custom_components/tellstick_local/`)

A config-flow hub integration that:

- Connects to the add-on TCP sockets
- Subscribes to 433 MHz RF events from the TelldusEvents socket
- Builds a stable device identifier from RF parameters
  (`protocol_model_house_unit`)
- Auto-adds switch / light / sensor entities when a 433 MHz signal is received
  (controlled by the `automatic_add` option)
- Fires HA bus events and dispatcher signals for automations / device triggers

---

## Key Files

### Add-on (`tellsticklive/`)

| File | Purpose |
|------|---------|
| `config.yaml` | Add-on metadata, version, device schema |
| `Dockerfile` | Container build: installs telldus-core from source, socat, tellcore-py |
| `rootfs/etc/cont-init.d/telldusd.sh` | Generates `/etc/tellstick.conf` from add-on config at startup |
| `rootfs/etc/services.d/telldusd/run` | Starts `telldusd`, waits for UNIX sockets, launches socat bridges |
| `rootfs/etc/services.d/telldusd/finish` | Halts add-on if telldusd crashes unexpectedly |
| `rootfs/etc/services.d/stdin/run` | Processes `hassio.addon_stdin` service calls (on/off/dim/list) |

### Custom Integration (`custom_components/tellstick_local/`)

| File | Purpose |
|------|---------|
| `manifest.json` | Domain, version, requirements (`tellcore-py`) |
| `const.py` | **SOURCE OF TRUTH** – all domain constants, event type IDs, method bitmasks, signal templates |
| `client.py` | **SOURCE OF TRUTH** – asyncio TCP client; telldusd binary framing (big-endian uint32-prefixed frames, UTF-8 strings) |
| `config_flow.py` | Config flow: host/port entry, live connection validation, options flow |
| `__init__.py` | Hub setup, event subscription, dispatcher + HA bus event dispatch |
| `entity.py` | Base entity: device registry, state restore |
| `switch.py` | Switch platform (on/off for codeswitch / selflearning-switch models) |
| `light.py` | Light platform (dim / on / off for selflearning-dimmer models) |
| `sensor.py` | Sensor platform (temperature, humidity from wireless sensors) |
| `device_trigger.py` | Device automation triggers: `turned_on` / `turned_off` |
| `strings.json` | UI strings (config flow labels, error messages) |
| `translations/en.json` | English translations (mirrors strings.json) |

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

## Version Numbering

The integration version lives in **two places** — both must stay in sync:

```
□ 1. custom_components/tellstick_local/manifest.json  → "version": "X.Y.Z"
□ 2. tellsticklive/config.yaml                        → version: X.Y.Z
```

**Quick verification:**

```bash
grep '"version"' custom_components/tellstick_local/manifest.json
grep '^version:' tellsticklive/config.yaml
```

If they don't match, fix them before committing.

---

## telldusd Binary Protocol

The `client.py` file implements the telldusd socket framing. Key facts:

- Every message is a **big-endian uint32 byte-length prefix** followed by payload
- Strings are encoded as **uint32 length** + UTF-8 bytes (length `0xFFFFFFFF` = null)
- Integers are **big-endian int32** (4 bytes signed)
- Event type IDs (from `const.py`):
  - `1` = `TELLDUSD_DEVICE_EVENT` – named device state change
  - `3` = `TELLDUSD_RAW_DEVICE_EVENT` – raw RF event string (key:value pairs separated by `;`)
  - `4` = `TELLDUSD_SENSOR_EVENT` – sensor reading

**NEVER duplicate this framing logic outside `client.py`.**

### Raw RF event format

Raw events arrive as a semicolon-separated `key:value` string, for example:

```
class:command;protocol:arctech;model:selflearning;house:A;unit:1;method:turnon;
```

The stable device UID is built from: `protocol_model_house_unit`.

---

## Supported 433 MHz Protocols

The add-on passes these through to `tellstick.conf` (enforced by config schema):

`arctech`, `brateck`, `comen`, `everflourish`, `fineoffset`, `fuhaote`,
`hasta`, `ikea`, `kangtai`, `mandolyn`, `oregon`, `risingsun`, `sartano`,
`silvanchip`, `upm`, `waveman`, `x10`, `yidong`

Common model types: `codeswitch`, `selflearning-switch`, `selflearning-dimmer`,
`bell`, `kp100`, `ecosavers`, `temperature`, `temperaturehumidity`

---

## Testing

Testing is manual on real HAOS with TellStick hardware:

1. Create a GitHub release from the branch using the **Create Test Release** workflow
   (`.github/workflows/create-test-release.yaml`)
2. Install the add-on from this repository in HA Supervisor
3. Install the integration version via HACS
4. Restart Home Assistant
5. Add the **TellStick Local** integration via Settings → Devices & Services
6. Enable **Automatically add new devices** in the integration options
7. Press a 433 MHz remote — the device should appear in HA automatically

No automated unit tests exist. All testing is on real hardware.

---

## Common Mistakes to Avoid

1. ❌ Editing the integration without checking the actual `client.py` framing first
2. ❌ Changing `const.py` event type IDs without verifying against telldusd source
3. ❌ Forgetting to update **both** version locations (manifest.json + config.yaml)
4. ❌ Using deprecated HA APIs — check HA 2024.1+ compatibility
5. ❌ Adding Telldus Live / cloud dependencies — this is intentionally local-only
6. ❌ **FABRICATING method/property names instead of reading the source code** (see below)

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

| Approach | Success Rate |
|----------|-------------|
| Code where source was READ first | 80–95% |
| Code with FABRICATED names (guessed from patterns) | **0%** |

---

## Project Goals & Architecture (ToR)

- **Objective**: Provide reliable local 433 MHz device control and sensor
  monitoring via TellStick hardware in Home Assistant, without any cloud dependency.
- **Scope**: Cover switch, dimmer, and wireless sensor entities; automation
  triggers; and automatic device pairing from RF events.

### HAOS Compatibility Guidelines

- Full compliance with Home Assistant OS add-on and integration standards
- Use HA APIs for config flow, device registry, entity registry, dispatcher
- Maintain backward compatibility with HA 2024.1.0+

### Data Separation Principles

- Add-on config (`config.yaml`) defines the device list for `tellstick.conf`
- Integration (`const.py`, `client.py`) defines the communication protocol
- No duplication of protocol constants between the add-on and the integration

### Architecture Principles

- Add-on is minimal: runs daemon + exposes TCP sockets; no business logic
- Integration handles all HA entity management and event dispatch
- Device identity is protocol-derived (no manual ID assignment required)

### Development Workflow

- `main` for stable releases, feature branches for new development
- Use **Create Test Release** workflow to publish prerelease versions for testing
- CI runs yamllint, shellcheck, hadolint, and pyflakes on every push
