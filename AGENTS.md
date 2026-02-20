# Agent Handover Document

This document provides context for AI agents working on this repository.

## Repository Overview

This is a Home Assistant add-on that provides TellStick/TellStick Duo hardware support with optional Telldus Live cloud integration. It's a fork of erik73's addon-tellsticklive, which itself was based on the now-deprecated official Home Assistant TellStick add-on.

**Background**: The official Home Assistant TellStick add-on was deprecated in December 2024 because the underlying Telldus library is no longer maintained by its original manufacturer. This fork continues to provide TellStick support for those who need it.

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
4. Consider retry logic for Telldus Live connection failures
5. Add MQTT support as an alternative to Telldus Live

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
