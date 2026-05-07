# Home Assistant: TellStick Local

> [!NOTE]
> **✅ v3.2 — RTL-433 Sensor Auto-discovery + Generic RF Record & Replay**
> This release adds **RTL-433 sensor auto-discovery** (integrate any 433 MHz sensor
> via the rtl_433 add-on) and **Generic RF record & replay** (capture and replay
> ANY 433 MHz signal, even from unsupported protocols). Also includes full
> **TellStick Net / ZNet** support, **Mirror / Range Extender**, and **manual
> device grouping**.
> If you hit any problem, please [open an issue][issue].

> [!WARNING]
> **🟡 TellStick Net / ZNet — Beta** – On/off commands, event reception, and sensor
> decoding work for all major protocols. A wide range of scenarios has been tested, but
> edge cases may remain. Feedback and bug reports are very welcome.

> [!CAUTION]
> **🟡 Luxorparts / Cleverio 50969, 50970, 50972 — Beta (Duo only)** – On/off works
> on TellStick Duo using raw RF pulse encoding with pre-captured Telldus Live codes
> (LPD 1–24). Not yet available on TellStick Net/ZNet. See [details below](#known-limitations).

![Project Stage][project-stage-shield]

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

[![Github Actions][github-actions-shield]][github-actions]
![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

Local-only TellStick Duo and TellStick Net/ZNet support for Home Assistant – no cloud, no YAML, full GUI.

**v3.2 highlights:** RTL-433 sensor auto-discovery · Generic RF record & replay · TellStick Net / ZNet support · Mirror / range extender · full GUI device management

📊 **Project presentation:** [English][presentation-en] · [Svenska][presentation-sv]

---

## About

This project makes **TellStick Duo** (USB) and **TellStick Net / ZNet** (LAN) devices
work in Home Assistant OS exactly like other 433 MHz receivers (e.g. RFXtrx) — controlled
entirely through the HA GUI and the Home Assistant companion app, with no cloud, no Telldus
Live account, and no YAML file editing.

> **Hardware support status:**
>
> - **TellStick Duo** (USB stick) — **Stable.** Core features are working and well-tested.
> - **TellStick Net / ZNet** (LAN device) — **Beta.** On/off and event reception work for all
>   major protocols (arctech, everflourish, waveman, sartano, x10, hasta, brateck). Sensor
>   decoding works for fineoffset, mandolyn, and oregon. Some edge cases may remain.
>   No Telldus Live account needed — the integration talks to the Net/ZNet via local UDP.
>   **Note:** arctech dimmers (`selflearning-dimmer`) only support on/off on Net/ZNet —
>   variable-brightness dimming requires a **TellStick Duo**.
> - **Mixing Duo and Net/ZNet:** If you have both, use the **Duo as your primary device**
>   and add the Net/ZNet as a mirror/range extender. The Duo supports full dimming; the
>   Net/ZNet does not.
> - **Mirror / range extender** — **Stable.** Use a second TellStick (any mix of Duo / Net /
>   ZNet) to extend 433 MHz coverage. Commands are replicated to both hardware units; events
>   received by either unit are forwarded to the primary.

> **Terminology note:** HAOS 2026.2 renamed "Add-ons" to "Apps" in the UI. Both names
> refer to the same Supervisor-managed Docker container.

> **Note:** The official Home Assistant TellStick add-on was deprecated in December
> 2024 because the underlying Telldus library is no longer maintained by its original
> manufacturer. This project continues local TellStick Duo support.

### What you get

| Capability                   | Description                                                                                                         |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Auto install prompt**      | Install the app → HA automatically offers "Set up TellStick Local?"                                                 |
| **Press-to-discover**        | Press any 433 MHz remote → device appears in HA (auto-add or discovery prompt)                                      |
| **Add device button**        | Click "Add device" → choose "Add by brand" or "Add by protocol" → send pairing signal                               |
| **Ignore unwanted devices**  | Check "Ignore" on the discovery form to permanently hide false-positive detections                                  |
| **Learn button per device**  | Each switch/light device has a "Send learn signal" button on its device page                                        |
| **Edit existing devices**    | Change name, house/unit codes, or sensor ID — with full entity history preserved                                    |
| **Replace device (sensor)**  | After battery replacement, reassign a new sensor ID to an existing device                                           |
| **Group sensor probes**      | Multi-probe weather stations: group extra probes under one device for a clean UI                                    |
| **Group any devices**        | Group switches, lights, or covers from the same room under one shared HA device — via Configure → Edit → Manage device |
| **Multi-select removal**     | Select and delete multiple devices at once from the integration options                                             |
| **Per-device deletion**      | Delete any device from its device page ⋮ menu                                                                       |
| **Device state info**        | Protocol, model, house code and unit code shown as entity state attributes                                          |
| **GUI-only management**      | Add, rename, edit and remove devices via HA UI — no YAML, no restart                                                |
| **Upgrade notifications**    | After an app update, HA shows a persistent notification to restart — go to **Settings → Developer tools → Restart** |
| **Local push**               | RF events arrive in real time; no polling, no cloud                                                                 |
| **Automations**              | Device triggers on any 433 MHz button press, usable directly in HA automations                                      |
| **HA bus events**            | Every RF signal fires a `tellstick_local_event` on the HA bus — use in automations or Developer Tools               |
| **Mirror / range extender**  | Use a second TellStick as a mirror to extend RF coverage — all commands are replicated automatically                |
| **RTL-433 sensors**          | Auto-discover ANY 433 MHz sensor via rtl_433 add-on + MQTT (temperature, humidity, rain, wind, etc.)                |
| **Generic RF record/replay** | Record ANY 433 MHz signal and replay it as a switch — works even for unsupported protocols                          |
| **Debug connection**         | Service action `tellstick_local.debug_connection` logs connection state and last events                             |
| **Companion app**            | Identical UX in the HA Android/iOS app                                                                              |
| **No Telldus Live required** | Zero cloud, zero account, zero internet dependency                                                                  |

---

## Prerequisites

- **Hardware:** TellStick Duo (USB), TellStick Net, or TellStick ZNet connected or reachable
- **Software:** Home Assistant OS with **HA Core 2025.2 or later**
- **Optional (for RTL-433 sensors):**
  - [rtl_433 add-on](https://github.com/pbkhrv/rtl_433-hass-addons) installed and running
  - MQTT integration configured in HA

> **Why 2025.2?** The "Add device" button on the integration card uses the
> ConfigSubentryFlow API introduced in HA 2025.2. Older HA versions still work
> for auto-add and discovery — only the manual "Add device" button requires 2025.2+.

No HACS required — the integration is bundled inside the app and installs itself
automatically.

---

## How it works

This project has **two components** — the same architecture used by Z-Wave JS,
deCONZ, and other USB-dongle integrations. Both run on the **same HAOS machine**,
but HAOS enforces a hard separation between two execution environments:

| Component       | Runs in          | USB access | HA entities |
| --------------- | ---------------- | ---------- | ----------- |
| **App**         | Docker container | ✅ Yes     | ❌ No       |
| **Integration** | HA Core (Python) | ❌ No      | ✅ Yes      |

The app gets USB passthrough from the Supervisor, runs the `telldusd` C daemon, and
exposes it via TCP. The integration connects over that TCP link to create HA entities.
This split is unavoidable: HAOS never grants USB access to a Python integration, and
the C daemon cannot run inside Python.

**The app automatically installs the integration** by copying it to
`/config/custom_components/` at startup — no manual integration install step needed.

---

## Installation

### Step 1 – Install the TellStick Local app (via Supervisor)

1. In HAOS go to **Settings → Apps** (or Add-ons on older versions)
2. Click the **⋮ menu → Repositories** (or "Add custom repository")
3. Add: `https://github.com/R00S/addon-tellstick-local`
4. Select category **App** (or Add-on) and click **Add**
5. Find **TellStick Local** in the app store and click **Install**
6. Click **Start** — wait for the log to show `TellStick Local is ready!`

The app will automatically copy the integration into your HA config.

### Step 2 – Accept the setup prompt

When the app starts for the first time, Home Assistant automatically shows a
notification:

> **New device found: TellStick Local — Set up?**

Click it and then **Submit** to confirm. The integration connects to the app
automatically — no host or port entry needed.

If the notification does not appear, go to **Settings → Devices & Services →
Add Integration**, search for **TellStick Local**, and click through the setup.

> **Manual setup hostname:** If the host field is empty, check the app log for
> a line like `use host: e9305338-tellsticklive  ports: 50800 / 50801` and enter
> that hostname. Apps installed from a custom repository include a hex prefix.

---

## Pairing devices

### Method A – Automatic add (press-to-discover)

Works for any device that transmits 433 MHz when a button is pressed (remotes,
wall switches, sensors).

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Configure** (⚙ icon)
3. Make sure **Automatically add new devices** is enabled and click **Submit**
4. Press the button or remote you want to pair
5. The device appears in HA — click its name to rename it

> **Tip:** With automatic add disabled, detected devices still show up in the
> **Discovered** section of Devices & Services (like BLE devices). You can review
> them and click **Configure** to accept only the ones you want. Each discovery
> form includes an **"Ignore this device"** checkbox — check it to permanently
> hide false-positive detections. Ignored devices can be un-ignored later from
> **Configure → Manage ignored devices**.

### Method B – Self-learning teach (Add device button)

Use this for self-learning receivers (Nexa, KAKU, Proove, Intertechno, etc.)
that need to be taught a code before they respond.

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Add device** (the button on the integration card)
3. Choose how to find your device:
   - **Add by brand** — browse a list of supported brands (e.g. "Nexa — Self-learning on/off", "KlikAanKlikUit — Self-learning on/off")
   - **Add by protocol** — pick directly by protocol name (e.g. "arctech — Self-learning on/off") — useful if your brand is not listed
4. Pick your device type and enter a name, then click **Submit**
5. A house code and unit code are generated automatically — click **Submit** again
6. Put the receiver in **learn mode** (hold its button until it blinks)
7. HA sends the pairing signal — the receiver learns the code
8. The device appears in HA and can now be controlled

> **Re-teaching a device:** Each switch/light device has a **"Send learn signal"**
> button on its device page. Use it to re-pair a receiver without deleting and
> re-adding the device — put the receiver in learn mode and press the button.

### Editing a device

View and change parameters for any existing device:

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Configure** (⚙ icon)
3. Select **Edit a device** from the menu
4. Pick the device to edit — its current protocol, model, house and unit are shown
5. Change the name, house code, unit code, or sensor ID as needed

> **Sensor ID change (battery replacement):** When a sensor gets a new ID after
> battery replacement, edit the existing device and enter the new sensor ID. The
> entity ID and all history are preserved — no need to delete and re-add.
>
> **Alternatively**, when the new sensor is discovered, the discovery form shows a
> **"Replace existing device"** dropdown. Select the old device to migrate its
> entity ID and history to the new sensor ID in one step.

### Grouping multi-probe sensors

Weather stations with multiple probes (e.g. an indoor + outdoor temperature
sensor) report each probe with a different sensor ID. By default each probe
creates a separate device in Home Assistant. You can group them under one
device for a cleaner UI:

1. When the second probe is discovered, the discovery form shows:
   - **"— Add as new device —"** (default — creates a separate device)
   - **"Add to: _Outdoor station_"** — adds this probe's entities under the
     existing sensor device
2. Select **"Add to: …"** and give the probe a descriptive name (e.g.
   "Probe 2 temperature")
3. Both probes now appear as entities under the same device card

### Grouping any device under a shared HA device

All device types — switches, lights, covers — can be grouped under a single shared
HA device. This is useful when several remotes or sockets belong to the same room
and you want them to appear as one device card instead of many.

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Configure** (⚙ icon) → **Edit a device**
3. Select the device you want to group
4. Choose **Manage device → Group under a shared device**
5. Enter a group name (e.g. `Living Room`) — all devices with the same name are
   grouped together
6. Leave the field blank to remove the device from its group (back to standalone)

The integration reloads automatically after saving. The original per-device HA
device card disappears and all its entities appear under the shared group device.

> **Learn button:** The "Send learn signal" button moves with the device — after
> grouping it lives on the shared group device card, not the original device card.

### Mirror / range extender

If your 433 MHz coverage does not reach every room, you can use a **second
TellStick** as a mirror (range extender) for the first one. The mirror
replicates every on/off/dim command sent to the primary TellStick's devices and
forwards any RF events it receives back to the primary for device discovery and
state updates. This works across backend types — a TellStick Net/ZNet can mirror
a Duo and vice versa.

**How to set up:**

1. Make sure the primary TellStick is already set up in HA
2. Connect and start your second TellStick (Duo or Net/ZNet)
3. Go to **Settings → Devices & Services → TellStick Local** and click
   **Add Hub** on the integration card
4. Choose the hardware type (Duo or Net/ZNet) and enter its connection details
5. On the **"Mirror / range extender"** step, select the primary TellStick
   from the dropdown (or choose **"— No, set up as standalone —"** if you don't
   want mirroring)
6. Click **Submit** — the mirror is set up

The mirror entry appears in Devices & Services as _"TellStick (mirror of Primary)"_.
It has no devices of its own — all devices belong to the primary. When you turn on a
switch, the command is sent through both the primary and the mirror simultaneously.
When someone presses a remote near the mirror, the signal is forwarded to the
primary and the device updates in HA as usual.

> **Cross-backend mirroring:** A Duo (USB) can mirror a Net/ZNet (LAN) and vice
> versa. This is useful when you have a TellStick Duo plugged into your HAOS server
> and a TellStick Net in a different part of the house.

> **No Telldus Live required (Net/ZNet):** This integration talks to the Net/ZNet
> locally — no cloud account needed. If you also use Telldus Live on the same
> device, the two do not interfere — both work simultaneously.

> **Limitations:** The mirror step is only offered when at least one standalone
> TellStick entry already exists. You cannot set up a mirror without a primary.
> Mirror entries do not load their own platform entities — they only forward.

> **Adding devices to a mirror:** The global **+ Add 433 MHz device** button
> is available for all entries, including mirrors. If you click it while a mirror
> entry is selected, the flow immediately shows:
> _"This TellStick is a mirror — devices must be added through the primary hub entry."_
> To add or teach devices, open the **primary** TellStick entry instead.

### Pre-configuring devices in the app YAML

If you need a TX-only device available immediately (e.g. a Brateck projector
screen or a Comen switch that can only receive commands, never send RF), you can
add it directly to the app's **Configuration** tab in the HAOS Supervisor before
pressing any buttons.

**What happens when you add devices to the app YAML?**

At each startup, the integration automatically imports any device listed in the
app configuration that it does not already manage. They appear in
**Settings → Devices & Services → TellStick Local** exactly like any device added
through the GUI, and can be renamed, edited, or deleted from the integration's
Configure flow — no further YAML editing required.

> **One-way, one-time import.** The import runs once per unknown device. After a
> device is imported, the integration owns it. Changes you make to that device in
> the app YAML later are **not** automatically reflected in the integration — use
> the integration GUI to edit it instead. If you remove a device from the app YAML,
> the integration entity is **not** deleted automatically; delete it via the
> integration.

> **Sensor protocols are excluded.** Devices with `fineoffset`, `oregon`, or
> `mandolyn` protocol are never imported this way — they appear automatically when
> the sensor transmits.

See the [app documentation](tellsticklive/DOCS.md) for the full YAML schema and
learn-signal options.

---

### Removing devices

- **Single device:** Go to the device page, click the **⋮ menu** (three dots),
  and select **Delete**.
- **Multiple devices:** Go to **Configure** (⚙) → **Remove multiple devices** →
  select the devices to remove and click **Submit**. You can also check
  **"Also add to ignore list"** to prevent them from being re-discovered.

### Managing ignored devices

Devices that were ignored (from the discovery form or during deletion) can be
un-ignored:

1. Go to **Configure** (⚙) → **Manage ignored devices**
2. Select the devices you want to un-ignore
3. Click **Submit** — they will appear again when detected via RF

---

## Supported devices

The device picker in the integration shows all brands from the TelldusCenter
device library (56 devices across 25+ brands). The table below summarizes what
each protocol supports.

### Auto-discoverable (press a button → device appears)

| Protocol       | Entity type    | Brands                                                                                          |
| -------------- | -------------- | ----------------------------------------------------------------------------------------------- |
| `arctech`      | Switch / Light | Nexa, Proove, KlikAanKlikUit, Intertechno, HomeEasy, Chacon, CoCo, Kappa, Bye Bye Standby, Elro |
| `everflourish` | Switch         | GAO, Everflourish, Rusta                                                                        |
| `hasta`        | Cover          | Hasta (v1 + v2), Rollertrol motorised blinds (UP/DOWN/STOP)                                     |
| `mandolyn`     | Sensor         | Mandolyn / Summerbird (temperature/humidity)                                                    |
| `sartano`      | Switch         | Sartano, Brennenstuhl, Rusta, Elro (**opt-in** — see note below)                                |
| `waveman`      | Switch         | Waveman                                                                                         |
| `x10`          | Switch         | X10                                                                                             |
| `fineoffset`   | Sensor         | Nexa LMST-606 / WDS-100 thermometers, Fine Offset weather stations                              |
| `oregon`       | Sensor         | Oregon Scientific weather sensors (temp, humidity, rain, wind, UV)                              |

> **Nexa note:** Nexa _switches, dimmers, remotes and buttons_ use the `arctech`
> protocol. Nexa _thermometers and weather sensors_ (LMST-606, WDS-100 etc.) use
> the `fineoffset` protocol — they appear automatically as sensor entities.

> **Arctech dimmer note:** Variable-brightness dimming (`selflearning-dimmer`) works
> fully on **TellStick Duo** only. On **TellStick Net / ZNet**, dimmers are limited to
> on/off — the ZNet firmware cannot pass a brightness level to the RF encoder. The
> dimmer entity still appears in HA but brightness sliders have no effect on ZNet.
> Use a TellStick Duo if you need variable dimming.

> **Sartano note:** Sartano/codeswitch auto-detection is **off by default**
> because `telldusd` often falsely decodes arctech signals as sartano. If you
> actually have sartano hardware, enable the **"Detect sartano/codeswitch
> devices"** toggle in **Configure → Settings**.

> **Self-learning receivers (Nexa, KAKU, Proove, etc.):** These receivers
> are dual-protocol — they learn whatever code is sent during pairing. Use
> Method B (Add device → Add by brand → pick your brand → send teach signal) to pair
> them. The TellStick Duo includes a firmware-level repeat patch for reliable pairing
> with picky receivers.

> **🟡 Luxorparts / Cleverio 50969, 50970, 50972 (beta, Duo only):** On/off works
> on TellStick Duo via raw RF pulse encoding. Add by brand → "Luxorparts — On/off
> (beta, Duo only)" → pick an LPD number (1–24). Put the receiver in learn mode, then
> press Learn in HA. Not yet available on TellStick Net/ZNet. See
> [Known limitations](#known-limitations) for details.

### TX only (can be controlled but not auto-discovered)

These devices must be added via **Method B** (Add device → Add by brand or Add by protocol).

| Protocol     | Entity type | Brands                             |
| ------------ | ----------- | ---------------------------------- |
| `brateck`    | Cover       | Roxcore projector screens          |
| `comen`      | Switch      | Anslut / Jula                      |
| `fuhaote`    | Switch      | HQ                                 |
| `ikea`       | Switch      | IKEA Koppla                        |
| `risingsun`  | Switch      | Conrad, GAO, Kjell & Company, Otio |
| `silvanchip` | Switch      | Ecosavers, KingPin KP100           |
| `upm`        | Switch      | UPM                                |
| `yidong`     | Switch      | Goobay                             |

---

## RTL-433 sensor auto-discovery

If you have an **RTL-SDR USB dongle**, you can use the
[rtl_433 add-on](https://github.com/pbkhrv/rtl_433-hass-addons) to receive
signals from ANY 433 MHz sensor — not just TellStick-compatible ones. This
opens up support for hundreds of additional sensor models: weather stations,
temperature/humidity sensors, rain gauges, soil moisture sensors, and more.

### Prerequisites

1. **RTL-SDR USB dongle** — [supported models](https://triq.org/rtl_433/HARDWARE.html)
2. **MQTT broker** — Install the [Mosquitto broker](https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md) add-on (recommended)
3. **rtl_433 add-on** — From the [pbkhrv repository](https://github.com/pbkhrv/rtl_433-hass-addons)

### Step 1: Install and configure Mosquitto broker

1. Go to **Settings → Add-ons → Add-on Store**
2. Search for **Mosquitto broker** and click **Install**
3. Start the add-on — no configuration needed for basic setup
4. The broker runs on `localhost:1883` by default

### Step 2: Install MQTT integration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **MQTT** and select it
3. If Mosquitto is running, HA will auto-discover it — just click **Submit**
4. Verify connection: the MQTT integration should show as "Connected"

### Step 3: Install rtl_433 add-on

1. Go to **Settings → Add-ons → ⋮ → Repositories**
2. Add: `https://github.com/pbkhrv/rtl_433-hass-addons`
3. Find **rtl_433** in the store and click **Install**
4. **Do not start yet** — configure it first

### Step 4: Configure rtl_433 add-on

Create a configuration file at `/config/rtl_433/rtl_433.conf.template`:

```conf
# rtl_433 configuration for TellStick Local integration

# MQTT output - connect to local Mosquitto broker
# Format: mqtt://HOST:PORT,user=USERNAME,pass=PASSWORD,retain=0,qos=0
# For local Mosquitto with no auth, use (retain=0 prevents database growth):
output mqtt://localhost:1883,retain=0,qos=0

# Listen frequency (433.92 MHz is default for most sensors)
frequency 433.92M

# Convert all units to SI (Celsius, meters, etc.)
convert si

# Report metadata for better debugging
report_meta level
report_meta time:usec
report_meta protocol

# Enable pulse detection optimizations
pulse_detect autolevel
pulse_detect squelch

# Capture unknown signals for Generic RF support
signal_grabber unknown

# Optional: Enable specific protocols only (improves performance)
# Uncomment and adjust based on your sensors
# Full list: https://github.com/merbanan/rtl_433/blob/master/README.md
# protocol 40    # Acurite 592TXR
# protocol 19    # Ambient Weather F007TH
# protocol 74    # LaCrosse TX141
# protocol 113   # Fineoffset WH1080
```

> **Note:** If using MQTT authentication, replace the `output` line with:
> ```conf
> output mqtt://localhost:1883,user=YOUR_USERNAME,pass=YOUR_PASSWORD,retain=0,qos=0
> ```

The add-on will automatically create `/config/rtl_433/` on first start if it doesn't exist.
Any `.conf.template` files in that directory will be processed.

### Preventing MQTT database growth

RTL-433 sensors transmit frequently (every 30-60 seconds), which can quickly fill your MQTT
broker's database and consume disk space. To prevent this, configure rtl_433 to publish
messages **without retention** and optionally disable Mosquitto persistence for sensor data.

#### Option 1: Non-retained messages (recommended)

Add `retain=0` to the rtl_433 MQTT output line to prevent messages from being stored by the broker:

```conf
output mqtt://localhost:1883,retain=0,qos=0
```

**Explanation:**
- `retain=0` — Messages are delivered to active subscribers but NOT stored on disk
- `qos=0` — Fire-and-forget delivery (no acknowledgment, no queuing)

This is the **recommended approach** — it prevents disk growth while allowing Home Assistant
to receive real-time sensor updates.

#### Option 2: Disable persistence entirely (optional)

If you want to completely prevent the MQTT broker from writing to disk, edit the Mosquitto
add-on configuration:

1. Go to **Settings → Add-ons → Mosquitto broker → Configuration**
2. Add these options under the **customize** section:
   ```yaml
   customize:
     active: true
     folder: mosquitto
   ```
3. Create `/config/mosquitto/mosquitto.conf` with:
   ```conf
   persistence false
   ```
4. Restart the Mosquitto add-on

> **Note:** Disabling persistence means all MQTT data is lost on broker restart. Only use this
> if you're comfortable with sensors briefly showing "unavailable" after a restart until they
> transmit again.

#### Default behavior

By default (without `retain=0`), rtl_433 messages **are retained** — the MQTT broker stores
the latest value for each sensor topic on disk. This causes:
- `/data/mosquitto/mosquitto.db` to grow continuously
- Potential disk space exhaustion on systems with many sensors
- Slower broker startup as retained messages are reloaded

Adding `retain=0` solves this without any downside for typical Home Assistant use.

### Step 5: Start rtl_433 add-on

1. Plug in your RTL-SDR dongle
2. Start the rtl_433 add-on
3. Check the logs — you should see messages like:
   ```
   Registered 1 out of 259 device decoding protocols
   Found Rafael Micro R820T tuner
   rtl_433 version 23.11 listening...
   ```
4. When a sensor transmits, you'll see JSON output:
   ```json
   {"time":"2026-05-07 06:22:15","protocol":40,"model":"Acurite-592TXR",...}
   ```

### Step 6: Enable in TellStick Local integration

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Configure** (⚙ icon)
3. Select **Settings** from the menu
4. Enable **"Listen for rtl_433 sensors via MQTT"**
5. Click **Submit**

The integration subscribes to `rtl_433/#` and auto-creates sensor entities when signals arrive.

### Verifying MQTT messages

To verify rtl_433 is publishing to MQTT:

1. Go to **Developer Tools → MQTT**
2. Subscribe to topic: `rtl_433/#`
3. Press a button on your sensor or wait for an automatic transmission
4. You should see JSON messages appear

### Supported sensor fields

The integration auto-creates sensors for these fields:

| Field                | Device class     | Unit  | Example sensors                    |
| -------------------- | ---------------- | ----- | ---------------------------------- |
| `temperature_C`      | temperature      | °C    | Weather stations, thermometers     |
| `temperature_F`      | temperature      | °F    | (auto-converted to °C if needed)   |
| `humidity`           | humidity         | %     | Humidity sensors                   |
| `rain_mm`            | precipitation    | mm    | Rain gauges (total)                |
| `rain_rate_mm_h`     | precipitation    | mm/h  | Rain rate                          |
| `wind_avg_m_s`       | wind_speed       | m/s   | Wind sensors                       |
| `wind_max_m_s`       | wind_speed       | m/s   | Wind gusts                         |
| `wind_dir_deg`       | —                | °     | Wind direction                     |
| `uv`                 | —                | index | UV sensors                         |
| `pressure_hPa`       | atmospheric_pressure | hPa | Barometers                     |
| `battery_ok`         | battery          | —     | Battery status (0=low, 1=ok)       |
| `moisture`           | moisture         | %     | Soil moisture sensors              |

See `RTL433_SENSOR_FIELDS` in `const.py` for the complete list.

### Troubleshooting

**No sensors appear:**
- Check rtl_433 add-on logs for received signals
- Verify MQTT broker is running and connected
- Use Developer Tools → MQTT to verify messages on `rtl_433/#`
- Make sure "Listen for rtl_433 sensors" is enabled in TellStick Local settings

**Sensors stop updating:**
- Check rtl_433 add-on is still running
- Restart the MQTT broker if needed
- Some sensors only transmit every 30-60 seconds

**Too many unknown sensors:**
- Edit `/config/rtl_433/rtl_433.conf.template` to enable only specific protocols
- Use `protocol <number>` lines to filter (see [protocol list](https://github.com/merbanan/rtl_433/blob/master/README.md))
- Restart rtl_433 add-on after config changes

**Note:** rtl_433 sensors are **receive-only** — you cannot send commands to them.
They appear as sensor entities in HA and update automatically when signals arrive.

---

## Generic RF record & replay

**Generic RF** lets you record ANY 433 MHz signal (even from unsupported protocols)
and replay it as a switch in Home Assistant. This works for:

- Devices from protocols not implemented in `telldusd`
- Proprietary remotes with unknown encoding
- Any On-Off-Keying (OOK) 433 MHz device

**How it works:**

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Add device** and select **"Record Generic RF"**
3. Choose whether to use **rtl_433** (RTL-SDR dongle) or **TellStick** hardware
   - rtl_433 (recommended): cleaner captures, more protocols, works with any RTL-SDR
   - TellStick: works if you don't have an RTL-SDR
4. Press the button you want to record — HA captures the signal
5. Test the replay — HA sends the signal back
6. If it works, confirm — a new switch entity is created
7. Repeat for the Off signal if needed

**Requirements:**

- For rtl_433 capture: rtl_433 add-on + MQTT integration must be running
- For TellStick capture: TellStick Duo or TellStick Net/ZNet
- For replay: TellStick Duo or TellStick Net/ZNet (any model can replay)

**Note:** The recorded signal is a raw RF waveform — it bypasses protocol decoding
entirely. This means it works for ANY 433 MHz device, but each button press must
be recorded separately (On and Off are two different captures).

---

## Migrating from the old add-on (with Telldus Live)

1. Remove `enable_live`, `live_uuid`, `live_delay`, and `sensors` from the
   app configuration
2. Remove `tellstick:` and any `platform: tellstick` entries from `configuration.yaml`
3. Restart HA — accept the new integration setup prompt
4. Re-pair devices using automatic add or the teach flow

---

## Events for automations (`tellstick_local_event`)

Every RF signal received by the TellStick fires a **`tellstick_local_event`** on the
Home Assistant event bus. You can listen to these events in automations, scripts, or
in **Developer Tools → Events** (enter `tellstick_local_event` and click **Start
listening**).

### Device events (remote button presses)

Fired whenever a 433 MHz command signal is received — even from devices that are
not registered in Home Assistant.

| Field        | Example                          | Description                                                                           |
| ------------ | -------------------------------- | ------------------------------------------------------------------------------------- |
| `type`       | `turned_on` / `turned_off`       | Action type (`turned_on`, `turned_off`, `up`, `down`, `stop`, `bell`, `learn`, `dim`) |
| `device_uid` | `arctech_selflearning_2673666_1` | Stable identifier built from protocol/model/house/unit                                |
| `protocol`   | `arctech`                        | RF protocol name                                                                      |
| `model`      | `selflearning`                   | Device model                                                                          |
| `house`      | `2673666`                        | House code                                                                            |
| `unit`       | `1`                              | Unit number                                                                           |

> **Multi-protocol note:** One physical button press can fire 2–3 events with
> different protocols (e.g. arctech + everflourish + waveman). This is normal.
> Filter on `device_uid` in your automation trigger to match only the correct one.

**Example automation trigger** (YAML mode):

```yaml
trigger:
  - platform: event
    event_type: tellstick_local_event
    event_data:
      type: turned_on
      device_uid: arctech_selflearning_2673666_1
```

### Sensor events (temperature, humidity, etc.)

Fired when a wireless sensor sends a reading.

| Field       | Example               | Description                                                                           |
| ----------- | --------------------- | ------------------------------------------------------------------------------------- |
| `type`      | `sensor`              | Always `sensor`                                                                       |
| `sensor_id` | `135`                 | Integer sensor ID                                                                     |
| `protocol`  | `fineoffset`          | Sensor protocol                                                                       |
| `model`     | `temperaturehumidity` | Sensor model string                                                                   |
| `data_type` | `1`                   | 1=temp, 2=humidity, 4=rain_rate, 8=rain_total, 16=wind_dir, 32=wind_avg, 64=wind_gust |
| `value`     | `21.3`                | Sensor reading                                                                        |

### ZNet raw packets (debugging)

When using the ZNet backend, every decoded UDP packet also fires with
`type: znet_raw_packet`, including unrecognized protocols. Useful for
debugging unknown device traffic.

---

## Debugging

### Developer Tools → Events

Go to **Developer Tools → Events**, enter `tellstick_local_event`, and click
**Start listening**. Every RF signal received by the TellStick will appear in
the event log with all decoded parameters. This is the easiest way to verify
that the TellStick is receiving signals.

### Debug connection service

Call the **`tellstick_local.debug_connection`** service (from **Developer Tools →
Services**) to log the current connection state and recent event counts to the
Home Assistant log.

---

## Troubleshooting

### "A notification appeared saying restart is required"

Go to **Settings → Developer tools → Restart** and restart Home Assistant to load the
newly installed integration version. The notification will dismiss itself after restart.

### "No setup prompt appeared after installing the app"

Go to **Settings → Devices & Services → Add Integration**, search **TellStick Local**
and run the manual setup flow.

### "Integration cannot connect"

1. Confirm the app is **running** and the log shows `TellStick Local is ready!`
2. Ports 50800 and 50801 must be reachable from HA Core (they are on the Supervisor
   internal network by default — no firewall config needed)

### "No devices appear after pressing remote"

1. Check that **Automatically add new devices** is enabled in the integration options
   (Configure → Settings → enable toggle)
2. Go to **Developer Tools → Events**, listen for `tellstick_local_event` — if events
   appear when you press buttons, the TellStick is receiving signals correctly
3. Open the app log — raw RF events should appear when a button is pressed
4. Confirm the TellStick Duo USB stick is connected:
   **Settings → Apps → TellStick Local → Hardware**

> **TellStick Net / ZNet in a separate VLAN or subnet:** The ZNet pushes RF events
> to the HA host on **UDP port 42314**. If that port is blocked by a firewall, no
> devices will appear. Also note that UDP broadcasts do not cross VLANs — if you had
> to type the ZNet IP manually during setup (instead of it being auto-discovered), your
> network is isolated enough that return traffic is likely blocked too. Allow UDP 42314
> from the ZNet to the HA host to fix this.
>
> **Thermometers / wireless sensors:** These broadcast automatically on a timer — you
> do not need to press a button. Just wait a few minutes after setup and they should
> appear on their own.

### "Receiver did not learn the code during teach"

1. Make sure the receiver was in learn mode _before_ clicking Submit
2. Try again — the pairing signal can be re-sent as many times as needed

### "On/off commands don't work (TellStick doesn't blink)"

1. Check the HA log for warnings like "No telldusd device ID for …"
2. Try deleting the device and re-adding it via the "Add device" button
3. Verify house/unit codes via Configure → Edit device

### "Add device shows 'This TellStick is a mirror' message"

This is correct — mirror entries inherit their devices from the primary and
cannot hold devices of their own. To add or teach a device, click **+ Add 433 MHz device**
from the **primary** TellStick hub entry instead.

### "Multiple devices appear from one remote button press"

This is normal — `telldusd` runs all protocol decoders on every RF signal. A single
button press can trigger 2-3 different protocol interpretations (e.g. arctech +
everflourish + waveman). Add only the correct one for your device brand. For the
false-positive ones, check **"Ignore this device"** on the discovery form to hide
them permanently.

> **Sartano phantom devices:** The most common false positive is sartano/codeswitch
> appearing alongside arctech/selflearning. To avoid this, sartano auto-detection
> is **off by default**. If you have real sartano hardware, enable the
> **"Detect sartano/codeswitch devices"** toggle in **Configure → Settings**.

---

## Known limitations

### Arctech dimmers on TellStick Net / ZNet — on/off only

The **TellStick Net / ZNet** firmware cannot perform variable-brightness dimming
for arctech `selflearning-dimmer` devices. The ZNet firmware's `handleSend()` call
does not pass the brightness level to the RF encoder, so any dim command falls back
to a full-brightness on command. Dimmer entities still appear in HA, but the
brightness slider has no effect.

**Workaround:** Use a **TellStick Duo** (USB) as your primary device. The Duo's
`telldusd` daemon supports the full arctech dim command including variable brightness.
If you have both a Duo and a Net/ZNet, add the Net/ZNet as a **mirror/range extender**
so it only relays on/off commands and the Duo handles all dimming.

### Luxorparts / Cleverio 50969, 50970, 50972 — Beta (Duo only)

These Luxorparts / Cleverio 1000W remote-controlled sockets work on
**TellStick Duo** using raw RF pulse encoding with pre-captured Telldus Live
codes (LPD 1–24). **Not yet available on TellStick Net/ZNet.**

**How to add a Luxorparts device (Duo):**

1. Go to **Configure → Add device → Add by brand**
2. Select **"Luxorparts — On/off (beta, Duo only)"**
3. Pick an **LPD number** (1–24) — each number is a unique code pair
4. Put the receiver in learn mode (hold button until LED flashes)
5. Press **Learn** in HA — the Duo sends the ON code to teach the receiver
6. The receiver should now respond to on/off commands

**Current limitations:**

- Only 24 pre-captured LPD codes are available. If none of them work with
  your receiver, you need a different LPD number or a fresh receiver.
- The learn button sends the ON command (not a high-repeat learn signal)
  because the actual learn signal does not flash the Duo hardware.
- **TellStick Net/ZNet:** Not yet implemented. The raw pulse encoding
  needs to be ported to the Net/ZNet UDP interface.

If you have an RTL-SDR and can capture additional working codes, please
[open an issue][issue].

---

## Future-proofing your TellStick ZNet (optional)

> **Context:** Telldus Live has shown signs of reduced maintenance. This
> integration does **not** use Telldus Live — it talks to the ZNet locally
> via UDP — so you are already independent of the cloud for normal use.
> The tip below is extra insurance in case Telldus discontinues the ZNet
> firmware update service or changes the device's local UDP protocol.

If you own a **TellStick ZNet**, you can install the open-source
**tellstick-plugin-mqtt-hass** plugin directly onto the device. With this
plugin installed, the ZNet can publish RF events to your local MQTT broker
and receive on/off commands over MQTT — fully independently of Telldus Live
and of this project.

**Why this is worth doing:**

- If Telldus Live is shut down, your ZNet continues to work via MQTT.
- The plugin survives on the device through firmware updates.
- Installation is free and requires no hardware modification.

**How to get the plugin installed:**

1. Download the latest release from the plugin repository:
   <https://github.com/quazzie/tellstick-plugin-mqtt-hass/releases>
2. The plugin requires your device to have **local plugin support** enabled.
   Open a support ticket at <http://support.telldus.com> and ask for an
   updated firmware with support for local plugins. In your request, also
   ask for the supported developer **quazzie@gmail.com** with the public key
   from the plugin repository. Based on community experience (April 2026),
   responses typically arrive in up to a month.
3. Once the support request is accepted, log in to your ZNet at
   <http://tellstick.local> using your Telldus Live credentials. Go to
   **Plugins (beta)** → **Manual upload** (↑) and upload the downloaded
   package. Reboot after install.

> **Note:** This plugin is independent of this integration. You do not
> need it for this project to work. It is purely an insurance measure —
> a ZNet with the plugin installed is safe from future Telldus Live
> disruptions regardless of what happens to the cloud service or to this
> project.

---

## Support

- [Open an issue on GitHub][issue]
- [☕ Buy me a coffee](https://buymeacoffee.com/r00s)

---

## License

GNU General Public License v3.0 or later

Copyright (c) 2019–2024 Erik Hilton
Copyright (c) 2024–2026 R00S

See [LICENSE.md](LICENSE.md) and [NOTICE](NOTICE) for full details.

## Acknowledgments

- **Erik Hilton (erik73)** – Original add-on and telldus-core fork
  — <https://github.com/erik73/addon-tellsticklive> / <https://github.com/erik73/telldus>
- **Erik Johansson (erijo)** – `tellcore-py` Python bindings
  — <https://github.com/erijo/tellcore-py>
- **Telldus Technologies AB** – Original TellStick hardware and telldus-core daemon
- **Home Assistant Team** – Platform and original TellStick add-on (Apache 2.0)

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[commits-shield]: https://img.shields.io/github/commit-activity/y/R00S/addon-tellstick-local.svg
[commits]: https://github.com/R00S/addon-tellstick-local/commits/main
[github-actions-shield]: https://github.com/R00S/addon-tellstick-local/workflows/CI/badge.svg
[github-actions]: https://github.com/R00S/addon-tellstick-local/actions
[issue]: https://github.com/R00S/addon-tellstick-local/issues
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026.svg
[presentation-en]: https://htmlpreview.github.io/?https://github.com/R00S/addon-tellstick-local/blob/main/presentation.html
[presentation-sv]: https://htmlpreview.github.io/?https://github.com/R00S/addon-tellstick-local/blob/main/presentation-sv.html
[project-stage-shield]: https://img.shields.io/badge/project%20stage-stable-brightgreen.svg
