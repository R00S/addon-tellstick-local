# Option B: MQTT Backend (Future Plan)

This document describes the planned third connection method for the TellStick
Local integration — MQTT transport via the
[quazzie/tellstick-plugin-mqtt-hass](https://github.com/quazzie/tellstick-plugin-mqtt-hass)
plugin. **Nothing described here is implemented yet.** It is a reference for
future development.

---

## Background: the three connection methods

The integration's config flow currently offers two ways to add a TellStick:

| Method | Constant | Hardware | Transport |
|---|---|---|---|
| **USB (Duo)** | `BACKEND_DUO` | TellStick Duo | TCP → socat → telldusd UNIX socket |
| **IP/UDP (Net/ZNet)** | `BACKEND_NET` | TellStick Net / ZNet | UDP direct to device |

Option B adds a third:

| Method | Constant | Hardware | Transport |
|---|---|---|---|
| **MQTT (ZNet + plugin)** | `BACKEND_MQTT` | TellStick ZNet v2 | MQTT via local broker |

---

## Why Option B is worth implementing

### Independence from the UDP protocol

The ZNet's local UDP protocol (`BACKEND_NET`) was reverse-engineered from
firmware. Telldus could change or remove it in a firmware update without
notice. The MQTT plugin installs onto the ZNet itself and survives firmware
updates — it is the stable long-term interface.

### Insurance against Telldus infrastructure changes

The quazzie plugin makes the ZNet publish events and accept commands through
the user's own local MQTT broker. Once installed, the ZNet works regardless
of what happens to Telldus Live, Telldus cloud, or even the ZNet firmware
update channel.

### Richer device management than autodiscovery alone

The plugin already does HA MQTT autodiscovery — devices appear in HA
automatically without this integration. Option B adds value on top of that:
the integration's options flow (teach self-learning receivers, rename/remove
devices, manual device add) works over MQTT just as it does over UDP.

---

## How the quazzie plugin's MQTT topics work

All topics follow this pattern (verified from plugin source):

```
<discovery_topic>/<entity_type>/<device_name>/<tellstick_id>/
```

Default values: `discovery_topic = "homeassistant"`, `device_name = <user-configured>`.

| Topic suffix | Direction | Payload | Purpose |
|---|---|---|---|
| `.../state` | Plugin → HA | `ON` / `OFF` (switch/light) or JSON (dimmer/sensor) | Current device state |
| `.../set` | HA → Plugin | `ON` / `OFF` (switch/light) or JSON (dimmer) | Turn on/off command |
| `.../config` | Plugin → HA | JSON autodiscovery config | Device registration |
| `.../pos` | HA → Plugin | `0`–`255` integer | Cover position |
| `.../setMode` | HA → Plugin | mode string | Thermostat mode |

### State payload details (from Devices.py)

| Entity type | `state` payload |
|---|---|
| Switch | `"ON"` or `"OFF"` |
| Light (dimmer) | `{"state": "ON"/"OFF", "brightness": 0–255}` |
| Cover | `"open"` / `"closed"` / `"stopped"` |
| Sensor (temp/humidity) | Numeric value string |

### Command payload details

| Entity type | `set` payload |
|---|---|
| Switch | `"ON"` or `"OFF"` |
| Light (dimmer) | `{"state": "ON"/"OFF"}` or `{"brightness": 0–255}` |
| Cover | `"OPEN"` / `"CLOSE"` / `"STOP"` |

---

## Technical design

### New constant

```python
# const.py
BACKEND_MQTT = "mqtt"   # TellStick ZNet v2 — MQTT via local broker + quazzie plugin
```

New config keys for the MQTT backend:

```python
CONF_MQTT_BROKER   = "mqtt_broker"    # hostname / IP of the MQTT broker
CONF_MQTT_PORT     = "mqtt_port"      # default 1883
CONF_MQTT_USER     = "mqtt_username"  # optional
CONF_MQTT_PASSWORD = "mqtt_password"  # optional
CONF_MQTT_TOPIC    = "mqtt_discovery_topic"   # default "homeassistant"
CONF_MQTT_DEVNAME  = "mqtt_device_name"       # must match plugin config
```

### Config flow changes

`async_step_backend_select` (already shows Duo vs Net) gains a third option:
**MQTT (ZNet with plugin)**. Selecting it routes to a new
`async_step_mqtt_setup` that asks for broker host/port, optional
credentials, discovery topic, and device name (the values configured in
the plugin).

A live MQTT connection test should be run before confirming the entry.

### New MQTT client

A new `client_mqtt.py` (or a new class in `client.py`) that:

1. **Connects** to the MQTT broker using `aiomqtt` (already an HA dependency,
   no new requirements needed).
2. **Subscribes** on connect to:
   - `<discovery_topic>/+/<device_name>/+/state` — live state updates
   - `<discovery_topic>/+/<device_name>/+/config` — autodiscovery payloads
     (used to build the device list on startup instead of a separate
     "list devices" command)
3. **Publishes** commands to `<discovery_topic>/<type>/<device_name>/<id>/set`.
4. **Maps** incoming autodiscovery payloads → `RawDeviceEvent` equivalents so
   the rest of `__init__.py` (entity creation, `device_id_map`, options flow)
   works without changes.

### What does NOT change

- `__init__.py` event dispatch logic — it already works from `RawDeviceEvent`
  objects regardless of transport.
- Options flow (teach, add, remove) — it calls `client.learn()` /
  `client.turn_on()` etc. The MQTT client implements the same interface.
- Switch / light / sensor / cover entity classes — unchanged.

---

## Prerequisites for users

1. **Install the quazzie plugin** on the ZNet v2 (requires a developer key from
   Telldus — contact `support@telldus.com` with the ZNet serial number; see
   the "Future-proofing" section in README.md for details).
2. **Configure the plugin** with the MQTT broker address and a device name.
3. **In HA**, add a TellStick Local integration entry, pick MQTT, and enter the
   same broker settings and device name.

> **Note:** The ZNet must stay connected to the local network but does **not**
> need Telldus Live or internet access once the plugin is installed.

---

## Implementation checklist

- [ ] Add `BACKEND_MQTT` to `const.py` with new `CONF_MQTT_*` keys
- [ ] Add `async_step_backend_select` MQTT option to `config_flow.py`
- [ ] Add `async_step_mqtt_setup` config flow step (broker, port, user, pass,
      discovery topic, device name)
- [ ] Write `MqttClient` class implementing the same interface as the existing
      Duo/Net clients (`turn_on`, `turn_off`, `dim`, `learn`, `list_devices`)
- [ ] Map MQTT autodiscovery payloads → internal device list on startup
- [ ] Map MQTT state messages → dispatcher signals (same path as UDP events)
- [ ] Add MQTT-specific entries to `strings.json` and `translations/en.json`
- [ ] Add integration test coverage for the MQTT config flow step
- [ ] Document the setup flow in README.md (expand the "Future-proofing" section)

---

## Relationship to the existing "Future-proofing" section in README

The README already mentions the quazzie plugin as optional insurance for ZNet
owners. Once Option B is implemented, that section should be updated to link
to this backend option as the recommended way to use the plugin together with
this integration.

---

## References

- [quazzie/tellstick-plugin-mqtt-hass](https://github.com/quazzie/tellstick-plugin-mqtt-hass) — plugin source
- [docs/telldus-live-shutdown-migration-plan.md](telldus-live-shutdown-migration-plan.md) — related migration plan
- `custom_components/tellstick_local/const.py` — `BACKEND_DUO`, `BACKEND_NET` constants
- `custom_components/tellstick_local/config_flow.py` — `async_step_backend_select`
