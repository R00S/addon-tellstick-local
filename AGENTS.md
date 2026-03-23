# Agent Handover Document

This document provides context for AI agents working on this repository.

## Repository Overview

This is a Home Assistant add-on that provides local TellStick/TellStick Duo hardware support — no cloud, no Telldus Live. Originally based on erik73's addon-tellsticklive (which was based on the now-deprecated official Home Assistant TellStick add-on), this is now an independent project focused entirely on local control.

**Background**: The official Home Assistant TellStick add-on was deprecated in December 2024 because the underlying Telldus library is no longer maintained by its original manufacturer. This project continues to provide local TellStick support.

## Architecture

### Directory Structure

```
tellsticklive/
├── Dockerfile              # Container build instructions
├── config.yaml             # Add-on configuration schema
├── DOCS.md                 # User documentation (shown in HA UI)
└── rootfs/
    └── etc/
        ├── cont-init.d/    # Initialization scripts (run once at startup)
        │   ├── telldusd.sh     # Creates /etc/tellstick.conf
        │   └── tellivecore.sh  # Creates /etc/tellive.conf
        └── services.d/     # S6 service definitions
            ├── telldusd/       # Main TellStick daemon
            │   ├── run         # Service start script
            │   └── finish      # Service cleanup script
            ├── tellivecore/    # Telldus Live connector
            │   ├── run
            │   └── finish
            ├── runonce/        # One-time registration service
            │   └── run
            └── stdin/          # Home Assistant stdin service
                ├── run
                └── finish
```

### Service Flow

1. **Initialization Phase** (cont-init.d scripts):
   - `telldusd.sh`: Generates `/etc/tellstick.conf` from add-on config (devices, protocols, house codes)
   - `tellivecore.sh`: Generates `/etc/tellive.conf` if live is enabled (UUID, device/sensor mappings)

2. **Service Phase** (services.d):
   - `telldusd`: Starts the telldusd daemon, waits for UNIX sockets to be created, then starts socat TCP bridges
   - `tellivecore`: Waits for telldusd sockets, then connects to Telldus Live (if UUID configured)
   - `runonce`: Handles initial Telldus Live registration (when no UUID is set)
   - `stdin`: Processes Home Assistant service calls (on, off, dim, bell, list, list-sensors)

### Key Files

| File                  | Purpose                                                       |
| --------------------- | ------------------------------------------------------------- |
| `/etc/tellstick.conf` | TellStick device configuration (generated from add-on config) |
| `/etc/tellive.conf`   | Telldus Live connection configuration                         |
| `/tmp/TelldusClient`  | UNIX socket for TellStick commands                            |
| `/tmp/TelldusEvents`  | UNIX socket for TellStick events                              |

### Communication Architecture

```
Home Assistant <--TCP:50800/50801--> socat <--UNIX socket--> telldusd <--USB--> TellStick Hardware
                                                                  |
                                                                  v
                                                          tellive_core_connector --> Telldus Live Cloud
```

- **Port 50800**: TCP bridge to TelldusClient socket (commands)
- **Port 50801**: TCP bridge to TelldusEvents socket (events/sensor data)

## Configuration Format

The add-on configuration generates a tellstick.conf file that follows the [official TellStick configuration format](http://developer.telldus.com/wiki/TellStick_conf):

```conf
user = "root"
group = "plugdev"
ignoreControllerConfirmation = "false"

device {
  id = 1
  name = "Living Room Light"
  protocol = "arctech"
  model = "selflearning-switch"
  parameters {
    house = "12345678"
    unit = "1"
  }
}
```

## Common Issues and Solutions

### Issue: "Could not connect to the Telldus Service (-6)"

**Root Cause**: Race condition where socat TCP bridges started before telldusd created UNIX sockets.

**Solution Applied** (in this fork):

1. Modified `telldusd/run` to start telldusd first in background
2. Wait up to 60 seconds for UNIX sockets to be created
3. Only then start socat bridges

**If issue persists for users**: They should wait 30-60 seconds after add-on startup before restarting Home Assistant.

### Issue: Telldus Live not connecting after restart

**Root Cause**: Empty UUID written to config, or service starting before telldusd is ready.

**Solution Applied**:

1. Only write UUID to config when it has a value
2. Add socket readiness checks in tellivecore and runonce services
3. 60-second timeout for socket readiness

### Issue: New registration URL shown instead of connecting

**Root Cause**: `live_uuid` not properly saved or formatted incorrectly.

**Solution**: Ensure UUID format matches: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (lowercase hex)

### Issue: Sensors appearing as switches

**Root Cause**: Protocol mismatch or auto-discovery issues in Home Assistant.

**Solution**: Users should use `only_named` in their sensor configuration to avoid auto-discovery issues.

### Issue: Hasta blinds / Brateck screens do not respond to on/off commands

**Root Cause**: `hasta` and `brateck` protocols support only UP/DOWN/STOP
(`TELLSTICK_UP | TELLSTICK_DOWN | TELLSTICK_STOP`), NOT TURNON/TURNOFF.
Source: `ProtocolHasta.cpp::methods()` and `ProtocolBrateck.cpp::methods()`.
Earlier versions incorrectly created these devices as switch entities, so HA
sent `tdTurnOn`/`tdTurnOff` which telldusd silently rejected.

**Solution Applied**: Added `cover.py` platform. Both protocols are listed in
`_COVER_PROTOCOLS` in `cover.py` and `switch.py`. `_is_cover()` routes them to
`TellStickCover` (Up/Down/Stop); `_is_switch()` now explicitly excludes them.

Hasta remotes have **exactly three buttons**: Up, Down, Stop. Brateck has the
same three-button model. The cover entity state is updated optimistically from
remote button press events (method:up / method:down). No position feedback is
available from either protocol.

### Hasta protocol — two variants (verified from ProtocolHasta.cpp)

There are **two versions** of the Hasta protocol with completely different RF
encoding. Both are handled by the same `hasta` protocol name in telldusd; the
model string distinguishes them.

| Aspect           | v1 — `selflearning`                     | v2 — `selflearningv2`                         |
| ---------------- | --------------------------------------- | --------------------------------------------- |
| Model string     | `selflearning`                          | `selflearningv2`                              |
| Pulse values     | 33 ≈ 330 µs / 17 ≈ 170 µs               | 63 ≈ 630 µs / 35 ≈ 350 µs                     |
| Preamble         | `[164,1,164,1,164,164]` (3 × 2 pulses)  | `[245,1,245,245,63,1,63,1,35,35]` (5 × 2 + 2) |
| House byte order | Little-endian (bytes swapped on decode) | Big-endian (high byte first)                  |
| Method — UP      | high-nibble `0x0`                       | high-nibble `0xC`                             |
| Method — DOWN    | high-nibble `0x1`                       | high-nibble `0x1` (also `0x8`)                |
| Method — STOP    | high-nibble `0x5`                       | high-nibble `0x5`                             |
| Method — LEARN   | high-nibble `0x4`                       | high-nibble `0x4`                             |
| Checksum         | None                                    | Yes — `((sum/256+1)*256+1) - sum`             |
| Typical devices  | Older Hasta motors                      | Newer Hasta motors, Rollertrol                |

**Important:** The two variants are **not interchangeable**. A v2 remote cannot
teach a v1 motor and vice versa. The device catalog has separate entries:

- `"Hasta — Blinds"` → protocol `hasta`, model `selflearning:hasta`
- `"Hasta — Blinds (v2)"` → protocol `hasta`, model `selflearningv2:hasta`
- `"Rollertrol — Blinds"` → protocol `hasta`, model `selflearningv2:rollertrol`

**Integration behaviour**: `cover.py` handles both transparently — it only checks
`_is_cover(protocol)` which returns `True` for any `hasta` device regardless of
model. Both variants decode to the same `method:up/down/stop` event format, so
no model-specific code is needed in the integration.

### Issue: Mandolyn incorrectly listed as a TX (switch) protocol

**Root Cause**: `mandolyn` was in `TX_PROTOCOLS` and `PROTOCOL_DEFAULT_MODELS`
but it is **RX-only**. `ProtocolMandolyn` only has a `static decodeData()`
method, no `methods()` or `getStringForMethod()`, and is **not registered in
`Protocol::getProtocolInstance()`** (verified in
`telldus-core-2.1.3-beta1/service/Protocol.cpp`).

Mandolyn is a temperature/humidity **sensor** protocol used by Mandolyn/Summerbird
IVT wireless thermometers. Events arrive as
`class:sensor;protocol:mandolyn;model:temperaturehumidity;...` and are handled
automatically by the sensor platform — no device catalog entry needed.

**Solution Applied**: Removed `mandolyn` from `TX_PROTOCOLS` and
`PROTOCOL_DEFAULT_MODELS` in `const.py`.

## Supported Protocols and Device Catalog

### Protocol classification (verified from telldus-core source)

**TX+RX (can send commands AND receive events):** `arctech`, `brateck`, `comen`,
`everflourish`, `fuhaote`, `hasta`, `ikea`, `risingsun`, `sartano`, `silvanchip`,
`upm`, `waveman`, `x10`, `yidong`.
Source: `Protocol::getProtocolInstance()` in `service/Protocol.cpp`.

**RX-only (sensor/event receive only — cannot send commands):** `fineoffset`,
`mandolyn`, `oregon`.
These protocols have only `static decodeData()` and are NOT in
`getProtocolInstance()`. Do NOT add them to `TX_PROTOCOLS`.

### Protocol → HA entity type

| Protocol       | HA entity              | Commands     | Notes                                                                                                                      |
| -------------- | ---------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `arctech`      | switch / light / cover | ON/OFF/DIM   | Model decides: selflearning-switch → switch, selflearning-dimmer → light, bell → switch                                    |
| `hasta`        | **cover**              | UP/DOWN/STOP | Two variants: `selflearning` (v1, older motors) and `selflearningv2` (v2, newer motors + Rollertrol). NOT interchangeable. |
| `brateck`      | **cover**              | UP/DOWN/STOP | Projector screens/blinds. Do NOT use as switch.                                                                            |
| `comen`        | switch                 | ON/OFF/LEARN | Anslut/Jula brand                                                                                                          |
| `everflourish` | switch                 | ON/OFF/LEARN | GAO brand                                                                                                                  |
| `fuhaote`      | switch                 | ON/OFF       | HQ brand                                                                                                                   |
| `ikea`         | switch/light           | ON/OFF/DIM   | IKEA Koppla                                                                                                                |
| `mandolyn`     | **sensor**             | — (RX only)  | Mandolyn/Summerbird temperature+humidity sensors                                                                           |
| `fineoffset`   | **sensor**             | — (RX only)  | Nexa LMST-606/WDS-100 weather sensors                                                                                      |
| `oregon`       | **sensor**             | — (RX only)  | Oregon Scientific weather sensors                                                                                          |
| `risingsun`    | switch                 | ON/OFF       | Conrad, Otio, Kjell & Company                                                                                              |
| `sartano`      | switch                 | ON/OFF       | Brennenstuhl, Elro, Rusta, Sartano                                                                                         |
| `silvanchip`   | switch                 | ON/OFF/LEARN | Ecosavers, KingPin KP100                                                                                                   |
| `upm`          | switch                 | ON/OFF/LEARN | UPM                                                                                                                        |
| `waveman`      | switch                 | ON/OFF       | Old arctech family                                                                                                         |
| `x10`          | switch                 | ON/OFF       | X10 protocol                                                                                                               |
| `yidong`       | switch                 | ON/OFF       | Goobay                                                                                                                     |

### Brand → protocol mapping (device catalog)

The `DEVICE_CATALOG` in `const.py` maps user-friendly brand names to
`(protocol, model, widget)` tuples. Most European/Nordic 433 MHz brands use
`arctech` selflearning:

| Brand                  | Protocol                 | Notes                                        |
| ---------------------- | ------------------------ | -------------------------------------------- |
| Anslut (Jula)          | comen                    | Comen selflearning                           |
| Brennenstuhl           | sartano                  | Code switch                                  |
| Chacon                 | arctech                  | Code switch + selflearning                   |
| CoCo Technologies      | arctech                  | Code switch + selflearning                   |
| Conrad / Otio          | risingsun                | Selflearning                                 |
| Ecosavers              | silvanchip               | Ecosavers model                              |
| Elro                   | sartano / arctech        | AB600 uses arctech codeswitch                |
| GAO                    | risingsun / everflourish | Both code switch and selflearning            |
| Goobay                 | yidong                   |                                              |
| Hasta                  | hasta                    | **Cover** — UP/DOWN/STOP                     |
| HomeEasy (UK)          | arctech                  | Selflearning                                 |
| HQ                     | fuhaote                  | Code switch                                  |
| IKEA Koppla            | ikea                     | Selflearning on/off and dimmer               |
| Intertechno            | arctech                  | Code switch + selflearning                   |
| Kappa                  | arctech                  | Code switch + selflearning                   |
| KingPin                | silvanchip               | KP100 model                                  |
| Kjell & Company        | risingsun                | Code switch                                  |
| KlikAanKlikUit (KAKU)  | arctech                  | Code switch + selflearning (popular NL)      |
| **Lidl (Silvercrest)** | arctech                  | Selflearning — 433 MHz sockets               |
| Luxorparts / Cleverio  | arctech                  | Selflearning                                 |
| Nexa                   | arctech                  | Code switch + selflearning (popular Nordic)  |
| Otio                   | risingsun                | Selflearning                                 |
| **Profile**            | arctech                  | Selflearning — Nordic/Norwegian brand        |
| Proove                 | arctech                  | Code switch + selflearning (popular Nordic)  |
| Rollertrol             | hasta                    | **Cover** — selflearningv2                   |
| Roxcore                | brateck                  | **Cover** — projector screen                 |
| Rusta                  | sartano / arctech        | Both code switch and selflearning            |
| Sartano                | sartano                  | Code switch                                  |
| **Telldus**            | arctech                  | Own-branded devices use arctech selflearning |
| **Trust Smart Home**   | arctech                  | Selflearning on/off and dimmer (NL brand)    |
| UPM                    | upm                      | Selflearning                                 |
| Waveman                | waveman                  | Code switch                                  |
| X10                    | x10                      | Code switch                                  |

**Bold** = brands added in this PR (were missing from the original catalog).

### Mandolyn / Summerbird sensor note

Mandolyn (brand: Mandolyn, Summerbird IVT) makes wireless temperature/humidity
sensors that are automatically discovered by the sensor platform. They are NOT
switches and require no device catalog entry. The `mandolyn` protocol is
**sensor-only** (RX only).

## Home Assistant Integration

Users need to configure both the add-on AND their configuration.yaml:

**Add-on configuration** (devices with protocols/codes):

```yaml
devices:
  - id: 1
    name: Light
    protocol: arctech
    model: selflearning-switch
    house: "12345678"
    unit: "1"
```

**configuration.yaml** (integration setup):

```yaml
tellstick:
  host: 32b8266a-tellsticklive
  port: [50800, 50801]

switch:
  - platform: tellstick

light:
  - platform: tellstick

sensor:
  - platform: tellstick
    only_named:
      - id: 135
        name: Outside Temp
```

## Development Notes

### Shell Scripts

- All scripts use `#!/command/with-contenv bashio` shebang (Home Assistant bashio wrapper)
- Use `bashio::` functions for logging (`bashio::log.info`, `bashio::log.error`) and config access
- Socket checks use `[[ -S /path ]]` to verify UNIX socket existence
- Use `bashio::config 'option'` to read add-on configuration
- Use `bashio::config.true "option"` to check boolean options

**⚠️ Alpine / BusyBox pitfalls:**

- `grep -P` (Perl regex) does **not exist** in BusyBox — use `jq` for JSON parsing
- `jq` is always available in bashio-based containers
- `sed -i` works but some GNU extensions don't (e.g. `\x00` hex escapes)
- `find` lacks `-printf` — use `-exec` instead
- No `realpath` — use `readlink -f` instead

```bash
# ❌ BROKEN: grep -oP not supported in Alpine BusyBox
VERSION=$(grep -oP '"version":\s*"\K[^"]+' manifest.json)

# ✅ CORRECT: use jq
VERSION=$(jq -r '.version' manifest.json)
```

### Service Call Handling (stdin service)

The stdin service reads JSON from Home Assistant and executes tdtool commands:

```bash
# Input format
{"function": "on", "device": 1}
{"function": "dim", "device": 2, "level": 128}
{"function": "list-sensors"}

# tdtool commands
tdtool --on 1
tdtool --dim 128 2
tdtool --list-sensors
```

### Testing

There is an automated integration test that verifies the custom integration loads
correctly in a real Home Assistant instance:

```bash
pip install homeassistant pyflakes
python tests/test_ha_integration.py
```

This test boots a minimal HA Core instance, loads the integration from
`custom_components/`, and verifies config flows, hassio discovery, options flow
instantiation, and all module imports. It catches broken imports (e.g. removed HA
APIs) and deprecated patterns without needing TellStick hardware.

Full end-to-end testing requires:

1. Building the Docker image locally
2. Running in a Home Assistant environment with actual TellStick hardware
3. Verifying device control and sensor reading
4. Checking Telldus Live connection (if enabled)

### Linting

- ShellCheck for bash scripts (use `-s bash` flag due to bashio shebang)
- yamllint for YAML files
- hadolint for Dockerfile

### Known HA Breaking Changes

These broke the integration in production. Check the
[HA developer blog](https://developers.home-assistant.io/blog/) when users
report failures on newer HA versions.

- **`HassioServiceInfo` import** (removed from old path in HA 2025.11):
  Must use `from homeassistant.helpers.service_info.hassio import HassioServiceInfo`
  (not `from homeassistant.components.hassio`). Same for all `*ServiceInfo` classes.

- **OptionsFlow `config_entry`** (broken in HA 2025.12):
  `OptionsFlow.__init__` must NOT take `config_entry` param or set
  `self.config_entry` manually. Framework auto-provides it after init.
  Access `self.config_entry` in step methods, not in `__init__`.

- **Always run `python tests/test_ha_integration.py`** after any integration
  Python change to catch broken imports early.

## Key Dependencies

| Dependency    | Purpose                                                         |
| ------------- | --------------------------------------------------------------- |
| `telldusd`    | TellStick daemon (built from source: github.com/erik73/telldus) |
| `tellive-py`  | Python library for Telldus Live connection                      |
| `tellcore-py` | Python bindings for TellStick Core library                      |
| `socat`       | TCP to UNIX socket bridge                                       |
| `bashio`      | Home Assistant add-on helper library                            |

## Build Process

The Dockerfile:

1. Starts from `ghcr.io/erik73/base-python/amd64:4.0.8`
2. Installs build dependencies (cmake, gcc, git)
3. Clones and builds telldus-core from erik73's fork
4. Patches tellive-py for modern Python SSL compatibility
5. Installs Python packages (tellcore-py, tellive-py)
6. Copies rootfs scripts

## Future Improvements

1. Add health checks for service readiness signaling to Home Assistant
2. Consider automatic UUID persistence (though this requires HA Supervisor API access)
3. Add more detailed logging with configurable log levels
4. Cover position tracking — Hasta/Brateck do not report position; a future
   feature could use timed travel distance to estimate position.

## Dev / Stable Channel Split

This project uses two separate GitHub repositories to give users a choice between
a stable channel and a dev (edge) channel — the same pattern used by
[hassio-addons/repository](https://github.com/hassio-addons/repository) /
[hassio-addons/repository-edge](https://github.com/hassio-addons/repository-edge).

### Two repos, one codebase

| Repo | Purpose | Docker tag | HAOS repo URL |
| ---- | ------- | ---------- | ------------- |
| `R00S/addon-tellstick-local` | Stable releases | `:X.Y.Z` + `:latest` | `https://github.com/R00S/addon-tellstick-local` |
| `R00S/addon-tellsticklive-roosfork` | Dev/edge channel | `:dev` + `:edge` | `https://github.com/R00S/addon-tellsticklive-roosfork` |

The dev repo lives at the **old repository path** (`addon-tellsticklive-roosfork`).
This is intentional: existing users who already had that URL added to HAOS continue
to receive automatic updates without any action on their part. Without reusing the
old path they would be orphaned on the last release.

The dev repo is a **thin index** — it has no code, Dockerfile or build system of its
own. It only contains `repository.json` and `tellsticklive/config.yaml` with
`version: dev` pointing at the pre-built `:dev` Docker images. The actual builds
happen here in the main repo via `.github/workflows/edge.yaml`.

### How features flow

```
feature branch  ──→  dev branch  ──→  main branch
                          │                │
                     edge.yaml        deploy.yaml
                     builds :dev      builds :X.Y.Z
                     & :edge tags     & :latest tags
                          │
                addon-tellsticklive-roosfork
                (existing users on dev channel receive
                 updates on every restart)
```

1. Feature work happens on feature branches in this repo
2. When ready for wider testing, merge to the `dev` branch
3. `edge.yaml` automatically rebuilds `:dev` and `:edge` Docker images
4. Dev channel users (who had `addon-tellsticklive-roosfork` in HAOS) get the
   update on next app restart
5. When the feature is stable, open a PR from `dev` → `main`
6. On merge to `main`, create a GitHub release — `deploy.yaml` builds and
   publishes versioned stable images

### Setting up the dev repo (one-time)

The `dev-repository/` directory in this repo contains the exact files for
`R00S/addon-tellsticklive-roosfork`. To set it up:

1. Create a new GitHub repo named `addon-tellsticklive-roosfork`
2. Copy all files from `dev-repository/` to the root of the new repo
3. Push to `main` — that's it, the dev HAOS channel is live

Whenever the schema in `tellsticklive/config.yaml` (stable) changes, mirror
the same change in `dev-repository/tellsticklive/config.yaml`.

## Migration Notes

Users migrating from the deprecated official add-on should:

1. Change host in configuration.yaml from `core-tellstick` to `32b8266a-tellsticklive`
2. Keep the same device configuration format (it's compatible)
3. Restart both add-on and Home Assistant

## Related Resources

- [TellStick Configuration Reference](http://developer.telldus.com/wiki/TellStick_conf)
- [Home Assistant Add-on Development](https://developers.home-assistant.io/docs/add-ons)
- [S6 Overlay Documentation](https://github.com/just-containers/s6-overlay)
- [Bashio Library](https://github.com/hassio-addons/bashio)
- [Home Assistant TellStick Integration](https://www.home-assistant.io/integrations/tellstick/)
- [TellStick Deprecation Discussion](https://community.home-assistant.io/t/tellstick-addon-deprecated/728576)
