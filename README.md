# Home Assistant: TellStick Local

> [!NOTE]
> **🧪 Beta – looking for testers!** If you have a TellStick Duo USB stick and
> run Home Assistant OS, please install, test, and [open an issue][issue] if
> anything doesn't work.

![Project Stage][project-stage-shield]

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

[![Github Actions][github-actions-shield]][github-actions]
![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

Local-only TellStick Duo support for Home Assistant – no cloud, no YAML, full GUI.

---

## About

This project makes the **TellStick Duo USB stick** work in Home Assistant OS exactly
like other 433 MHz receivers (e.g. RFXtrx) — controlled entirely through the HA GUI
and the Home Assistant companion app, with no cloud, no Telldus Live account, and no
YAML file editing.

> **Terminology note:** HAOS 2026.2 renamed "Add-ons" to "Apps" in the UI. Both names
> refer to the same Supervisor-managed Docker container.

> **Note:** The official Home Assistant TellStick add-on was deprecated in December
> 2024 because the underlying Telldus library is no longer maintained by its original
> manufacturer. This project continues local TellStick Duo support.

### What you get

| Capability                  | Description                                                                        |
| --------------------------- | ---------------------------------------------------------------------------------- |
| **Auto install prompt**     | Install the app → HA automatically offers "Set up TellStick Local?"                |
| **Press-to-discover**       | Press any 433 MHz remote → device appears in HA (auto-add or discovery prompt)     |
| **Add device button**       | Click "Add device" on the integration card → pick protocol → send pairing signal   |
| **Ignore unwanted devices** | Check "Ignore" on the discovery form to permanently hide false-positive detections |
| **Learn button per device** | Each switch/light device has a "Send learn signal" button on its device page       |
| **Edit existing devices**   | Change name, house/unit codes, or sensor ID — with full entity history preserved   |
| **Replace device (sensor)** | After battery replacement, reassign a new sensor ID to an existing device          |
| **Multi-select removal**    | Select and delete multiple devices at once from the integration options            |
| **Per-device deletion**     | Delete any device from its device page ⋮ menu                                      |
| **Device state info**       | Protocol, model, house code and unit code shown as entity state attributes         |
| **GUI-only management**     | Add, rename, edit and remove devices via HA UI — no YAML, no restart               |
| **Upgrade notifications**   | After an app update, HA shows a notification if a restart is needed                |
| **Local push**              | RF events arrive in real time; no polling, no cloud                                |
| **Automations**             | Device triggers on any 433 MHz button press, usable directly in HA automations     |
| **Companion app**           | Identical UX in the HA Android/iOS app                                             |
| **No Telldus Live**         | Zero cloud, zero account, zero internet dependency                                 |

---

## Prerequisites

- **Hardware:** TellStick Duo USB stick connected to the HAOS machine
- **Software:** Home Assistant OS with **HA Core 2025.2 or later**

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
3. Add: `https://github.com/R00S/addon-tellsticklive-roosfork`
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
3. Pick your **device type** from the dropdown (e.g. "Nexa — Self-learning on/off")
4. A house code and unit code are generated automatically — click **Submit**
5. Put the receiver in **learn mode** (hold its button until it blinks)
6. HA sends the pairing signal — the receiver learns the code
7. The device appears in HA and can now be controlled

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

| Protocol       | Entity type    | Brands                                                                                                                |
| -------------- | -------------- | --------------------------------------------------------------------------------------------------------------------- |
| `arctech`      | Switch / Light | Nexa, Proove, KlikAanKlikUit, Intertechno, HomeEasy, Chacon, CoCo, Luxorparts, Cleverio, Kappa, Bye Bye Standby, Elro |
| `everflourish` | Switch         | GAO, Everflourish, Rusta                                                                                              |
| `hasta`        | Cover          | Hasta, Rollertrol motorised blinds                                                                                    |
| `mandolyn`     | Switch         | Mandolyn / Summerbird                                                                                                 |
| `sartano`      | Switch         | Sartano, Brennenstuhl, Rusta, Elro                                                                                    |
| `waveman`      | Switch         | Waveman                                                                                                               |
| `x10`          | Switch         | X10                                                                                                                   |
| `fineoffset`   | Sensor         | Nexa LMST-606 / WDS-100 thermometers, Fine Offset weather stations                                                    |
| `oregon`       | Sensor         | Oregon Scientific weather sensors (temp, humidity, rain, wind, UV)                                                    |

> **Nexa note:** Nexa _switches, dimmers, remotes and buttons_ use the `arctech`
> protocol. Nexa _thermometers and weather sensors_ (LMST-606, WDS-100 etc.) use
> the `fineoffset` protocol — they appear automatically as sensor entities.

> **Self-learning receivers (Luxorparts 50969/50970, Nexa, etc.):** These receivers
> are dual-protocol — they learn whatever code is sent during pairing. Use
> Method B (Add device → pick brand → send teach signal) to pair them. The TellStick
> Duo includes a firmware-level repeat patch for reliable pairing with picky receivers.

### TX only (can be controlled but not auto-discovered)

These devices must be added via Method B (self-learning teach).

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

## Migrating from the old add-on (with Telldus Live)

1. Remove `enable_live`, `live_uuid`, `live_delay`, and `sensors` from the
   app configuration
2. Remove `tellstick:` and any `platform: tellstick` entries from `configuration.yaml`
3. Restart HA — accept the new integration setup prompt
4. Re-pair devices using automatic add or the teach flow

---

## Troubleshooting

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
2. Open the app log — raw RF events should appear when a button is pressed
3. Confirm the TellStick Duo USB stick is connected:
   **Settings → Apps → TellStick Local → Hardware**

### "Receiver did not learn the code during teach"

1. Make sure the receiver was in learn mode _before_ clicking Submit
2. Try again — the pairing signal can be re-sent as many times as needed
3. For picky receivers (like Luxorparts 50969), the TellStick Duo firmware patch
   repeats the learn signal 5 times automatically

### "On/off commands don't work (TellStick doesn't blink)"

1. Check the HA log for warnings like "No telldusd device ID for …"
2. Try deleting the device and re-adding it via the "Add device" button
3. Verify house/unit codes via Configure → Edit device

### "Multiple devices appear from one remote button press"

This is normal — `telldusd` runs all protocol decoders on every RF signal. A single
button press can trigger 2-3 different protocol interpretations (e.g. arctech +
everflourish + waveman). Add only the correct one for your device brand. For the
false-positive ones, check **"Ignore this device"** on the discovery form to hide
them permanently.

---

## Support

- [Open an issue on GitHub][issue]
- [☕ Buy me a coffee](https://buymeacoffee.com/r00s)

---

## License

GNU General Public License v3.0 or later

Copyright (c) 2019–2024 Erik Hilton
Copyright (c) 2024–2026 R00S (roosfork modifications)

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
[commits-shield]: https://img.shields.io/github/commit-activity/y/R00S/addon-tellsticklive-roosfork.svg
[commits]: https://github.com/R00S/addon-tellsticklive-roosfork/commits/main
[github-actions-shield]: https://github.com/R00S/addon-tellsticklive-roosfork/workflows/CI/badge.svg
[github-actions]: https://github.com/R00S/addon-tellsticklive-roosfork/actions
[issue]: https://github.com/R00S/addon-tellsticklive-roosfork/issues
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026.svg
[project-stage-shield]: https://img.shields.io/badge/project%20stage-beta-orange.svg
