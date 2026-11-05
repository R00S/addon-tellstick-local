# TellStick Local — User Guide

> **Applies to:** TellStick Local v3.3+ · Home Assistant Core 2025.2+
>
> This guide covers every feature from first installation through advanced use.
> Use the table of contents to jump to the section you need.

---

## Table of Contents

1. [What is TellStick Local?](#1-what-is-tellstick-local)
2. [Prerequisites](#2-prerequisites)
3. [How it works](#3-how-it-works)
4. [Installation](#4-installation)
   - 4.1 [Install the TellStick Local app](#41-install-the-tellstick-local-app)
   - 4.2 [Accept the setup prompt](#42-accept-the-setup-prompt)
5. [Pairing devices](#5-pairing-devices)
   - 5.1 [Automatic add (press-to-discover)](#51-automatic-add-press-to-discover)
   - 5.2 [Self-learning teach (Add device button)](#52-self-learning-teach-add-device-button)
   - 5.3 [Kjell & Company / Tuya-MOES curtain motor (Duo only)](#53-kjell--company--tuya-moes-curtain-motor-duo-only)
6. [Editing a device](#6-editing-a-device)
7. [Grouping devices](#7-grouping-devices)
   - 7.1 [Grouping multi-probe sensors](#71-grouping-multi-probe-sensors)
   - 7.2 [Grouping any device under a shared HA device](#72-grouping-any-device-under-a-shared-ha-device)
8. [Mirror / range extender](#8-mirror--range-extender)
9. [Removing and ignoring devices](#9-removing-and-ignoring-devices)
10. [Pre-configuring devices in the app YAML](#10-pre-configuring-devices-in-the-app-yaml)
11. [Supported devices](#11-supported-devices)
    - 11.1 [Auto-discoverable (press a button → device appears)](#111-auto-discoverable-press-a-button--device-appears)
    - 11.2 [TX only (add via Add device button)](#112-tx-only-add-via-add-device-button)
12. [Events for automations](#12-events-for-automations)
    - 12.1 [Device events (remote button presses)](#121-device-events-remote-button-presses)
    - 12.2 [Sensor events (temperature, humidity, etc.)](#122-sensor-events-temperature-humidity-etc)
13. [Debugging](#13-debugging)
14. [Troubleshooting](#14-troubleshooting)
15. [Known limitations](#15-known-limitations)
16. [Migrating from the old add-on (with Telldus Live)](#16-migrating-from-the-old-add-on-with-telldus-live)

---

## 1. What is TellStick Local?

TellStick Local makes **TellStick Duo** (USB) and **TellStick Net / ZNet** (LAN) 433 MHz
hardware work in Home Assistant OS with no cloud, no Telldus Live account, and no YAML
file editing. Every device is managed entirely through the HA GUI and the HA companion app
(Android/iOS).

**What you get:**

| Capability | Description |
|---|---|
| **Auto install prompt** | Install the app → HA automatically offers "Set up TellStick Local?" |
| **Press-to-discover** | Press any 433 MHz remote → device appears in HA |
| **Add device button** | Choose "Add by brand" or "Add by protocol" → send pairing signal |
| **Ignore unwanted devices** | Permanently hide false-positive detections from the discovery form |
| **Learn button per device** | Each switch/light device has a "Send learn signal" button on its device page |
| **Edit existing devices** | Change name, house/unit codes, or sensor ID — with entity history preserved |
| **Replace device (sensor)** | After battery replacement, reassign a new sensor ID to an existing device |
| **Group sensor probes** | Multi-probe weather stations: group extra probes under one device |
| **Group any devices** | Group switches, lights, or covers under one shared HA device card |
| **Multi-select removal** | Select and delete multiple devices at once from integration options |
| **Per-device deletion** | Delete any device from its device page ⋮ menu |
| **Device state info** | Protocol, model, house code and unit code shown as entity state attributes |
| **GUI-only management** | Add, rename, edit and remove devices via HA UI — no YAML, no restart |
| **Local push** | RF events arrive in real time; no polling, no cloud |
| **Automations** | Device triggers on any 433 MHz button press |
| **HA bus events** | Every RF signal fires a `tellstick_local_event` on the HA bus |
| **Mirror / range extender** | Use a second TellStick to extend RF coverage |
| **Companion app** | Identical UX in the HA Android/iOS app |
| **No Telldus Live required** | Zero cloud, zero account, zero internet dependency |

---

## 2. Prerequisites

- **Hardware:** TellStick Duo (USB), TellStick Net, or TellStick ZNet connected or reachable
- **Software:** Home Assistant OS with **HA Core 2025.2 or later**

> **Why 2025.2?** The "Add device" button on the integration card uses the
> ConfigSubentryFlow API introduced in HA 2025.2. Older HA versions still work
> for auto-add and discovery — only the manual "Add device" button requires 2025.2+.

No HACS required — the integration is bundled inside the app and installs itself
automatically.

---

## 3. How it works

This project has **two components** — the same architecture used by Z-Wave JS,
deCONZ, and other USB-dongle integrations. Both run on the **same HAOS machine**,
but HAOS enforces a hard separation between two execution environments:

| Component | Runs in | USB access | HA entities |
|---|---|---|---|
| **App** | Docker container | ✅ Yes | ❌ No |
| **Integration** | HA Core (Python) | ❌ No | ✅ Yes |

The app gets USB passthrough from the Supervisor, runs the `telldusd` C daemon, and
exposes it via TCP on ports **50800** (commands) and **50801** (events). The
integration connects over those TCP ports to create HA entities.

**The app automatically installs the integration** by copying it to
`/config/custom_components/` at startup — no manual integration install step needed.

---

## 4. Installation

### 4.1 Install the TellStick Local app

1. In HAOS go to **Settings → Apps** (or Add-ons on older versions)
2. Click the **⋮ menu → Repositories** (or "Add custom repository")
3. Add: `https://github.com/R00S/addon-tellstick-local`
4. Select category **App** (or Add-on) and click **Add**
5. Find **TellStick Local** in the app store and click **Install**
6. Click **Start** — wait for the log to show `TellStick Local is ready!`

The app copies the integration into your HA config automatically on startup.

> **TellStick Duo USB:** Plug the USB stick into your HAOS machine before starting
> the app. Go to **Settings → Apps → TellStick Local → Hardware** to confirm the
> device is visible.

> **TellStick Net / ZNet:** No USB needed. The integration connects to the ZNet via
> local UDP on your LAN — no Telldus Live account required.

### 4.2 Accept the setup prompt

When the app starts for the first time, Home Assistant automatically shows a
notification:

> **New device found: TellStick Local — Set up?**

Click it and then **Submit** to confirm. The integration connects to the app
automatically — no host or port entry needed.

**If the notification does not appear:**  
Go to **Settings → Devices & Services → Add Integration**, search for
**TellStick Local**, and click through the manual setup flow.

> **Manual setup hostname:** If the host field is empty, check the app log for
> a line like `use host: e9305338-tellsticklive  ports: 50800 / 50801` and enter
> that hostname. Apps installed from a custom repository include a hex prefix.

---

## 5. Pairing devices

### 5.1 Automatic add (press-to-discover)

Works for any device that transmits 433 MHz when a button is pressed (remotes,
wall switches, wireless sensors).

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Configure** (⚙ icon)
3. Make sure **Automatically add new devices** is enabled and click **Submit**
4. Press the button or remote you want to pair
5. The device appears in HA — click its name to rename it

> **When automatic add is disabled:** Detected devices still show up in the
> **Discovered** section of Devices & Services (like BLE devices). You can review
> them and click **Configure** to accept only the ones you want. Each discovery
> form includes an **"Ignore this device"** checkbox — check it to permanently
> hide false-positive detections. Ignored devices can be un-ignored later from
> **Configure → Manage ignored devices**.

> **Multiple devices from one button press:** `telldusd` runs all protocol decoders
> on every RF signal. A single button press can trigger 2–3 different protocol
> interpretations (e.g. arctech + everflourish + waveman). This is normal. Add only
> the correct one for your device brand and ignore the rest.

> **Wireless sensors (temperature, humidity):** These broadcast automatically on a
> timer — you do not need to press a button. Just wait a few minutes and they should
> appear on their own.

### 5.2 Self-learning teach (Add device button)

Use this for self-learning receivers (Nexa, KAKU, Proove, Intertechno, etc.) that
need to be taught a code before they respond.

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Add device** (the button on the integration card)
3. Choose how to find your device:
   - **Add by brand** — browse supported brands (e.g. "Nexa — Self-learning on/off")
   - **Add by protocol** — pick directly by protocol name (useful if your brand is not listed)
4. Pick your device type and enter a name, then click **Submit**
5. A house code and unit code are generated automatically — click **Submit** again
6. Put the receiver in **learn mode** (hold its button until it blinks)
7. HA sends the pairing signal — the receiver learns the code and blinks confirmation
8. The device appears in HA and can now be controlled

> **Re-teaching a device:** Each switch/light device has a **"Send learn signal"**
> button on its device page. Use it to re-pair a receiver without deleting and
> re-adding the device — put the receiver in learn mode and press the button.

> **Luxorparts / Cleverio 50969, 50970, 50972 (beta, Duo only):** Add by brand →
> "Luxorparts — On/off (beta, Duo only)" → pick an LPD number (1–24). Put the
> receiver in learn mode, then press Learn. See [Section 15](#15-known-limitations)
> for details.

### 5.3 Kjell & Company / Tuya-MOES curtain motor (Duo only)

Some 433 MHz remotes are **transmit-only**: no TellStick can receive them, so
their device can never be discovered by pressing a button. The Kjell & Company /
Tuya-MOES curtain motor from issue #100 is one of those — its handset only ever
sends. The frame format was captured over the air with an RTL-SDR at 433.92 MHz
and is regenerated by the integration.

**The motor is self-learning**, so Home Assistant can be the remote: the device
mints a code of its own and the motor is taught that code during pairing. **No
RTL-SDR is needed.** Users who *did* capture their own remote can paste its code
instead so the handset and Home Assistant share one identity.

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Add device** (the button on the integration card)
3. Choose **Add by brand** → **Kjell & Company — Tuya curtain motor
   (self-learning, Duo only)**, or **Add by protocol** → the same entry under
   `generic_rf`. It has no line of its own on the Add-device menu, because it
   is a brand/protocol choice like any other
4. Enter a name, leave **Captured code** empty, click **Submit**
5. The next screen explains pairing — the cover is added, but the motor does
   not know its code yet
6. Put the motor in pairing mode: press and hold **Stop on the motor** until its
   Stop indicator flashes red
7. Press **Open** on the new cover
8. The Up and Down LEDs flash → paired. **Open**, **Stop** and **Close** now work

> The code Home Assistant minted is logged when the device is added
> (`Adding curtain cover … identity 6c82xxxx`). The three codes are that identity
> followed by `ee` (up), `aa` (stop) and `cc` (down).

**Several motors.** Each added device mints its own identity, so motors can live
side by side — pair each one separately, from its own cover.

**Reusing a real remote's code (RTL-SDR owners).** Record one button press at
433.92 MHz with rtl_433 and copy the decoded 40-bit code (10 hex characters).
Paste it into **Captured code** when adding the device — only the first eight
characters (the identity) are used, because the button bytes are fixed. Home
Assistant then transmits exactly what your handset transmits, the handset keeps
working, and that motor needs no pairing step. Use this when a motor remembers
only one remote, or when the physical remote should stay authoritative.

**Requirements and limits**

- **TellStick Duo only.** The replay sends raw pulse trains
  (`tdSendRawCommand`), which Net/ZNet cannot do — on those backends the flow
  stops with an explanation instead of creating a device.
- **No feedback.** Nothing receives this remote, so the cover reports an assumed
  state; there is no position and no "it worked" confirmation.
- **The burst matters.** A real button press is five identical 40-bit frames
  with ~16.3–16.8 ms of silence between them, and each frame starts with a
  ~4.9 ms mark. The replay reproduces exactly that — five frames, 17 ms apart.
  Both values are fixed rather than settings: this motor has only ever answered
  this burst, so there is nothing to tune. One frame on its own, or frames a
  couple of milliseconds apart, is ignored by the receiver.
- **Variant** only matters to the debug actions below; the device itself always
  transmits `a`, the reading derived from the captures. `c`/`d` reverse the 40
  bits (bit order cannot be read off the pulse counts) and `e`–`h` repeat the
  four readings with the 1.46 ms frame start that single-frame decodes report.
  `tellstick_local.poc_sweep_blind` (Developer Tools → Actions, `button: down`)
  transmits all eight in turn so the log shows which one a motor answered.
- **Actions:** `tellstick_local.poc_send_blind` transmits one variant
  (`button`, `variant`, `repeat`, `pause_ms`) and
  `tellstick_local.poc_sweep_blind` transmits all eight in sequence
  (`button`, `repeat`, `pause_ms`, and `gap` — the pause in seconds between
  variants). Both return the payload and variant they sent so the log shows
  what the motor heard last.
- **Sending a different code.** Both actions accept an optional `payload`
  (10 hex characters) that overrides the button's own code, e.g.
  `payload: 6c82050ecc`. All three codes are now confirmed on hardware:
  `up` = `6c82050eee`, `stop` = `6c82050eaa`, `down` = `6c82050ecc`. Down was
  never captured in the issue — it was found by sending the doubled-nibble
  family `6c82050e00` … `6c82050eff` one code at a time until the motor moved.
  If another motor of this type answers to a different code, the override lets
  you test it without a rebuild.
- **Devices added before 3.3.2.0** stored the issue #100 remote's own code
  (`6c82050e…`). They still work, but only against a motor paired to that code.
  Delete and re-add them to give each one a code of its own.

### 5.4 Pairing, factory reset and end positions (the motor's own buttons)

These three procedures are performed on the motor and its remote, not in Home
Assistant. They are repeated from the motor's manual because they decide whether
a replay can work at all — a factory reset makes the motor forget the very
remote whose codes §5.3 replays, and no TellStick command can undo that.

**Pair a remote with a motor.** A remote only controls a motor it has been
paired with.

1. Press and hold **Stop** on the motor (the main unit) until the Stop
   indicator flashes red.
2. Press **Up** on the remote — or press **Open** on the cover Home Assistant
   added (§5.3); the motor cannot tell the two apart.
3. The pairing is successful when the **Up and Down** LEDs on the motor flash.

Step 2 is *press Up*: while the motor is in pairing mode it stores whatever
identity it hears on an **up** frame.

**Reset to factory settings.** Press and hold **Up and Down on the motor** — not
on the remote — for about 12 seconds, until the corresponding indicators flash
red, blue and green two to three times. Press **Stop** to finish. The motor
disconnects from the app and forgets its paired remote.

> A factory reset makes the motor forget its paired code, so the cover stops
> moving until it is paired again — repeat the pairing steps above, pressing
> **Open** on the cover instead of Up on a handset.

**Set the open and close positions**

1. Press **Up** until the blind reaches the position you want as open, then
   press **Stop**.
2. Press and hold **Stop** for about 5 seconds, until the indicator above the
   Stop button starts to flash red.
3. Press **Down** until the blind reaches the position you want as closed, then
   press **Stop**.

The motor stores both limits itself. The TellStick can neither set nor read them,
because nothing receives this remote (see the limits in §5.3).

#### Can Home Assistant pair a motor by generating a code?

Yes — confirmed on hardware (2026-11-05). While the motor is in pairing mode it
stores whichever 40-bit code it hears as a five-frame burst, so a code Home
Assistant invented is accepted exactly like a handset's. That is what §5.3
relies on, and why no RTL-SDR is required. It also means only your own mints can
open your blind: the identity is random per device, so it is not a fixed vendor
code shared by every motor of this model.

---

## 6. Editing a device

View and change parameters for any existing device:

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Configure** (⚙ icon) → **Edit a device**
3. Pick the device to edit — its current protocol, model, house and unit are shown
4. Change the name, house code, unit code, or sensor ID as needed

> **Sensor ID change (battery replacement):** When a wireless sensor gets a new
> ID after battery replacement, edit the existing device and enter the new sensor
> ID. The entity ID and all history are preserved — no need to delete and re-add.
>
> **Alternatively**, when the new sensor is discovered, the discovery form shows a
> **"Replace existing device"** dropdown. Select the old device to migrate its
> entity ID and history to the new sensor ID in one step.

---

## 7. Grouping devices

### 7.1 Grouping multi-probe sensors

Weather stations with multiple probes (e.g. an indoor + outdoor temperature sensor)
report each probe with a different sensor ID. By default each probe creates a separate
device in Home Assistant. You can group them under one device for a cleaner UI:

1. When the second probe is discovered, the discovery form shows:
   - **"— Add as new device —"** (default — creates a separate device)
   - **"Add to: _Outdoor station_"** — adds this probe's entities under the existing sensor device
2. Select **"Add to: …"** and give the probe a descriptive name (e.g. "Probe 2 temperature")
3. Both probes now appear as entities under the same device card

### 7.2 Grouping any device under a shared HA device

All device types — switches, lights, covers — can be grouped under a single shared
HA device. This is useful when several remotes or sockets belong to the same room
and you want them to appear as one device card instead of many.

1. Go to **Settings → Devices & Services → TellStick Local**
2. Click **Configure** (⚙ icon) → **Edit a device**
3. Select the device you want to group
4. Choose **Manage device → Group under a shared device**
5. Enter a group name (e.g. `Living Room`) — all devices with the same name are grouped together
6. Leave the field blank to remove the device from its group (back to standalone)

The integration reloads automatically after saving. The original per-device HA device card
disappears and all its entities appear under the shared group device.

> **Learn button:** The "Send learn signal" button moves with the device — after grouping
> it lives on the shared group device card.

---

## 8. Mirror / range extender

If your 433 MHz coverage does not reach every room, use a **second TellStick** as a
mirror (range extender). The mirror replicates every on/off/dim command to all
registered devices and forwards received RF events back to the primary.

**How to set up:**

1. Make sure the primary TellStick is already set up in HA
2. Connect and start your second TellStick (Duo or Net/ZNet)
3. Go to **Settings → Devices & Services → TellStick Local** and click **Add Hub**
4. Choose the hardware type and enter its connection details
5. On the **"Mirror / range extender"** step, select the primary TellStick from the dropdown
6. Click **Submit** — the mirror is set up

The mirror entry appears as _"TellStick (mirror of Primary)"_. It has no devices of its
own — all devices belong to the primary. Commands are sent through both units simultaneously.
RF events received by the mirror are forwarded to the primary for device detection.

> **Cross-backend mirroring:** A Duo (USB) can mirror a Net/ZNet (LAN) and vice versa.
>
> **Adding devices:** The **+ Add 433 MHz device** button is available for all entries,
> including mirrors. If you click it while a mirror entry is selected, the flow
> immediately shows _"This TellStick is a mirror — devices must be added through the
> primary hub entry."_ To add or teach devices, open the **primary** entry instead.

**All TellSticks receive events at the same time.** When you run several TellSticks
(a primary plus mirrors, or several independent hubs), each unit's sensor readings
and button-press events reach Home Assistant independently — one unit never blocks
another. This was fixed in **v3.3.1.8**; before that, only one of several Net/ZNet
units received events at a time while the others went silent (GitHub issue #115).

---

## 9. Removing and ignoring devices

### Removing a single device

Go to the device page, click the **⋮ menu** (three dots), and select **Delete**.

### Removing multiple devices

1. Go to **Configure** (⚙) → **Remove multiple devices**
2. Select the devices to remove and click **Submit**
3. Check **"Also add to ignore list"** to prevent them from being re-discovered

### Managing ignored devices

Devices that were ignored (from the discovery form or during deletion) can be un-ignored:

1. Go to **Configure** (⚙) → **Manage ignored devices**
2. Select the devices you want to un-ignore
3. Click **Submit** — they will appear again when detected via RF

---

## 10. Pre-configuring devices in the app YAML

For TX-only devices that never transmit RF (e.g. Brateck projector screens, Comen switches)
you can add them via the app's **Configuration** tab in the Supervisor before pressing any buttons.

At each startup, the integration automatically imports any device listed in the app configuration
that it does not already manage. They appear in **Settings → Devices & Services → TellStick Local**
exactly like GUI-added devices, and can be renamed, edited, or deleted from the integration — no
further YAML editing required.

> **One-way, one-time import.** After a device is imported, the integration owns it. Changes
> made to that device in the app YAML later are **not** automatically reflected — use the
> integration GUI to edit it instead.
>
> **Sensor protocols are excluded.** Devices with `fineoffset`, `oregon`, or `mandolyn`
> protocol are never imported — they appear automatically when the sensor transmits.

See the [app documentation](../tellsticklive/DOCS.md) for the full YAML schema and
learn-signal options.

---

## 11. Supported devices

### 11.1 Auto-discoverable (press a button → device appears)

| Protocol | Entity type | Brands |
|---|---|---|
| `arctech` | Switch / Light | Nexa, Proove, KlikAanKlikUit, Intertechno, HomeEasy, Chacon, CoCo, Kappa, Bye Bye Standby, Elro |
| `everflourish` | Switch | GAO, Everflourish, Rusta |
| `hasta` | Cover | Hasta (v1 + v2), Rollertrol motorised blinds (UP/DOWN/STOP) |
| `mandolyn` | Sensor | Mandolyn / Summerbird (temperature/humidity) |
| `sartano` | Switch | Sartano, Brennenstuhl, Rusta, Elro (**opt-in** — see note) |
| `waveman` | Switch | Waveman |
| `x10` | Switch | X10 |
| `fineoffset` | Sensor | Nexa LMST-606 / WDS-100 thermometers, Fine Offset weather stations |
| `oregon` | Sensor | Oregon Scientific weather sensors (temp, humidity, rain, wind, UV) |

> **Nexa note:** Nexa _switches, dimmers, remotes and buttons_ use the `arctech` protocol.
> Nexa _thermometers and weather sensors_ (LMST-606, WDS-100 etc.) use `fineoffset` — they
> appear automatically as sensor entities.

> **Arctech dimmer note:** Variable-brightness dimming (`selflearning-dimmer`) works fully
> on **TellStick Duo** only. On **TellStick Net / ZNet**, dimmers are limited to on/off.

> **Sartano note:** Sartano/codeswitch auto-detection is **off by default** because
> `telldusd` often falsely decodes arctech signals as sartano. Enable the
> **"Detect sartano/codeswitch devices"** toggle in **Configure → Settings** if you
> have real sartano hardware.

### 11.2 TX only (add via Add device button)

These devices must be added via **Method B** (Add device → Add by brand or Add by protocol).

| Protocol | Entity type | Brands |
|---|---|---|
| `brateck` | Cover | Roxcore projector screens |
| `comen` | Switch | Anslut / Jula |
| `fuhaote` | Switch | HQ |
| `ikea` | Switch | IKEA Koppla |
| `risingsun` | Switch | Conrad, GAO, Kjell & Company, Otio |
| `silvanchip` | Switch | Ecosavers, KingPin KP100 |
| `upm` | Switch | UPM |
| `yidong` | Switch | Goobay |

---

## 12. Events for automations

Every RF signal received by the TellStick fires a **`tellstick_local_event`** on the
Home Assistant event bus. You can listen to these events in automations, scripts, or in
**Developer Tools → Events** (enter `tellstick_local_event` and click **Start listening**).

### 12.1 Device events (remote button presses)

Fired whenever a 433 MHz command signal is received — even from devices not yet in HA.

| Field | Example | Description |
|---|---|---|
| `type` | `turned_on` / `turned_off` | Action type (`turned_on`, `turned_off`, `up`, `down`, `stop`, `bell`, `learn`, `dim`) |
| `device_uid` | `arctech_selflearning_2673666_1` | Stable identifier built from protocol/model/house/unit |
| `protocol` | `arctech` | RF protocol name |
| `model` | `selflearning` | Device model |
| `house` | `2673666` | House code |
| `unit` | `1` | Unit number |

> **Multi-protocol note:** One physical button press can fire 2–3 events with different
> protocols. Filter on `device_uid` in your automation trigger to match only the correct one.

**Example automation trigger (YAML):**

```yaml
trigger:
  - platform: event
    event_type: tellstick_local_event
    event_data:
      type: turned_on
      device_uid: arctech_selflearning_2673666_1
```

### 12.2 Sensor events (temperature, humidity, etc.)

Fired when a wireless sensor sends a reading.

| Field | Example | Description |
|---|---|---|
| `type` | `sensor` | Always `sensor` |
| `sensor_id` | `135` | Integer sensor ID |
| `protocol` | `fineoffset` | Sensor protocol |
| `model` | `temperaturehumidity` | Sensor model string |
| `data_type` | `1` | 1=temp, 2=humidity, 4=rain_rate, 8=rain_total, 16=wind_dir, 32=wind_avg, 64=wind_gust |
| `value` | `21.3` | Sensor reading |

---

## 13. Debugging

### Listen for RF events in Developer Tools

Go to **Developer Tools → Events**, enter `tellstick_local_event`, and click
**Start listening**. Every RF signal received by the TellStick will appear with all
decoded parameters. This is the easiest way to verify the TellStick is receiving signals.

### Debug connection service

Call the **`tellstick_local.debug_connection`** service (from **Developer Tools →
Services**) to log the current connection state and recent event counts to the HA log.
The report is saved to `config/tellstick_local_debug.txt`. For each TellStick Net/ZNet
entry it includes **Last packet received** (when, how long ago, and how many packets) —
this shows whether a unit is receiving anything at all, even when its connection
status shows OK.

### App log

Open **Settings → Apps → TellStick Local → Log**. Raw RF events appear in the log when
buttons are pressed. Look for `TellStick Local is ready!` at startup.

---

## 14. Troubleshooting

### "A notification appeared saying restart is required"

Go to **Settings → Developer tools → Restart** and restart Home Assistant to load the
newly installed integration version. The notification dismisses itself after restart.

### "No setup prompt appeared after installing the app"

Go to **Settings → Devices & Services → Add Integration**, search **TellStick Local**
and run the manual setup flow.

### "Integration cannot connect"

1. Confirm the app is **running** and the log shows `TellStick Local is ready!`
2. Ports 50800 and 50801 must be reachable from HA Core (they are on the Supervisor
   internal network by default — no firewall config needed)

### "No devices appear after pressing remote"

1. Confirm **Automatically add new devices** is enabled in **Configure → Settings**
2. Go to **Developer Tools → Events**, listen for `tellstick_local_event` — if events
   appear the TellStick is receiving signals correctly
3. Open the app log — raw RF events should appear when a button is pressed
4. Confirm the TellStick Duo USB stick is connected:
   **Settings → Apps → TellStick Local → Hardware**

> **TellStick Net / ZNet in a separate VLAN or subnet:** The ZNet pushes RF events to
> the HA host on **UDP port 42314**. If that port is blocked, no devices will appear.
> Allow UDP 42314 from the ZNet to the HA host.
>
> **Thermometers / wireless sensors** broadcast on a timer — just wait a few minutes.

### "Receiver did not learn the code during teach"

1. Make sure the receiver was in learn mode _before_ clicking Submit
2. Try again — the pairing signal can be re-sent as many times as needed
3. Verify house/unit codes match via **Configure → Edit device**

### "On/off commands don't work (TellStick doesn't blink)"

1. Check the HA log for warnings like "No telldusd device ID for …"
2. Try deleting the device and re-adding it via **Add device**
3. Verify house/unit codes via **Configure → Edit device**

### "Sensor values / button presses stopped updating — I have several TellSticks"

Before **v3.3.1.8**, running several Net/ZNet TellSticks could starve all but
one of them (GitHub issue #115) — one unit received everything while the others
went silent. Update to v3.3.1.8 or later and restart Home Assistant. If it still
happens, run `TellStick Local: Debug connection` and check **Last packet
received** for each entry: a unit with no packets for minutes has a network
problem (check that UDP port 42314 is not blocked and the unit's IP is correct).

### "All sensors unavailable after updating Home Assistant (RTL-433)"

Home Assistant **2026.11.0** removed `EntityCategory` from
`homeassistant.components.sensor`. Versions before **v3.3.2.3** imported it from
there when creating RTL-433 **battery** and **voltage** entities, so a stored
battery or voltage entity made the sensor platform fail to import — every
sensor from this integration became unavailable, while switch, light and cover
entities kept working.

Update to **v3.3.2.3** or later and restart Home Assistant. If the sensors stay
unavailable, check the HA log for `ImportError` mentioning
`homeassistant.components.sensor`.

This is correct — mirror entries inherit their devices from the primary. Click
**+ Add 433 MHz device** from the **primary** TellStick hub entry instead.

### "Multiple devices appear from one remote button press"

This is normal — `telldusd` runs all protocol decoders on every RF signal. Add only
the correct one for your device brand. For the false-positive ones, check
**"Ignore this device"** on the discovery form to hide them permanently.

> **Sartano phantom devices:** The most common false positive is sartano/codeswitch
> appearing alongside arctech/selflearning. Sartano auto-detection is **off by default**
> to avoid this. Enable it only if you have real sartano hardware.

---

## 15. Known limitations

### Arctech dimmers on TellStick Net / ZNet — on/off only

The **TellStick Net / ZNet** firmware cannot perform variable-brightness dimming for
arctech `selflearning-dimmer` devices. Dimmer entities still appear in HA, but the
brightness slider has no effect on ZNet.

**Workaround:** Use a **TellStick Duo** (USB) as your primary device, and add the
Net/ZNet as a **mirror/range extender** — the Duo handles all dimming while the
Net/ZNet relays on/off commands.

### Luxorparts / Cleverio 50969, 50970, 50972 — Beta (Duo only)

These Luxorparts / Cleverio 1000W remote-controlled sockets work on **TellStick Duo**
using raw RF pulse encoding with pre-captured Telldus Live codes (LPD 1–24).
**Not yet available on TellStick Net/ZNet.**

**How to add a Luxorparts device (Duo):**

1. **Configure → Add device → Add by brand**
2. Select **"Luxorparts — On/off (beta, Duo only)"**
3. Pick an **LPD number** (1–24) — each number is a unique code pair
4. Put the receiver in learn mode (hold button until LED flashes)
5. Press **Learn** in HA

**Current limitations:**

- Only 24 pre-captured LPD codes are available
- The learn button sends the ON command (not a high-repeat learn signal)
- **TellStick Net/ZNet:** Not yet implemented

---

## 16. Migrating from the old add-on (with Telldus Live)

If you were using the previous TellStick add-on that required a Telldus Live account:

1. Remove `enable_live`, `live_uuid`, `live_delay`, and `sensors` from the app configuration
2. Remove `tellstick:` and any `platform: tellstick` entries from `configuration.yaml`
3. Restart HA — accept the new integration setup prompt
4. Re-pair devices using automatic add or the teach flow

> **Why no migration of old devices?** The old YAML-based integration stored device
> configurations in `configuration.yaml`. The new integration uses HA's config entry
> storage — it cannot automatically import from YAML. Re-pairing takes only a few
> minutes per device.
