# Home Assistant: TellStick Local

> [!WARNING]
> **🚧 Development repository – not ready for public testing.**
> This repo is under active development. Features may be incomplete, APIs may
> change without notice, and there may be known bugs. Do not use in production.

![Project Stage][project-stage-shield]

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
![Supports armhf Architecture][armhf-shield]
![Supports armv7 Architecture][armv7-shield]
![Supports i386 Architecture][i386-shield]

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

| Capability              | Description                                                                    |
| ----------------------- | ------------------------------------------------------------------------------ |
| **Auto install prompt** | Install the app → HA automatically offers "Set up TellStick Local?"            |
| **Press-to-discover**   | Enable automatic add → press any remote → device appears in HA                 |
| **Self-learning teach** | Options → Add device → pick protocol → send pairing signal → receiver learns   |
| **GUI-only management** | Add, rename and remove devices via HA UI — no YAML, no restart                 |
| **Local push**          | RF events arrive in real time; no polling, no cloud                            |
| **Automations**         | Device triggers on any 433 MHz button press, usable directly in HA automations |
| **Companion app**       | Identical UX in the HA Android/iOS app                                         |
| **No Telldus Live**     | Zero cloud, zero account, zero internet dependency                             |

---

## Prerequisites

- **Hardware:** TellStick Duo USB stick connected to the HAOS machine
- **Software:** Home Assistant OS **2026.2 or later** (HAOS, not Container/Core)

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
3. Enable **Automatically add new devices** and click **Submit**
4. Press the button or remote you want to pair
5. The device appears in HA — click its name to rename it

### Method B – Self-learning teach

Use this for self-learning receivers (Nexa, KAKU, Proove, Intertechno, etc.)
that need to be taught a code before they respond.

1. Go to **Settings → Devices & Services → TellStick Local → Configure**
2. Click **Add device**
3. Pick the **Protocol** (e.g. `arctech`) and **Model** (e.g. `selflearning-switch`)
4. A house code and unit code are generated automatically — click **Submit**
5. Put the receiver in **learn mode** (hold its button until it blinks)
6. HA sends the pairing signal — the receiver learns the code
7. The device appears in HA and can now be controlled

### Removing a device

1. Go to **Settings → Devices & Services → TellStick Local → Configure**
2. Click **Remove device**
3. Select the device and click **Submit**

---

## Supported devices

### Auto-discoverable (press a button → device appears)

| Protocol                          | Entity type    | Example brands / devices                                               |
| --------------------------------- | -------------- | ---------------------------------------------------------------------- |
| `arctech` — `codeswitch`          | Switch         | Old Nexa, KAKU dial-based remotes and wall switches                    |
| `arctech` — `selflearning-switch` | Switch         | Nexa, KAKU, Intertechno, Proove, HomeEasy, Chacon, CoCo                |
| `arctech` — `selflearning-dimmer` | Light (dimmer) | Nexa, Proove, KAKU dimmers                                             |
| `arctech` — `bell`                | Event          | Nexa doorbell                                                          |
| `everflourish`                    | Switch         | Everflourish, Rusta selflearning switches                              |
| `hasta`                           | Switch/Cover   | Hasta motorised blinds                                                 |
| `mandolyn`                        | Switch         | Mandolyn / Summerbird switches                                         |
| `sartano`                         | Switch         | Sartano, Kjell & Company switches                                      |
| `waveman`                         | Switch         | Waveman switches                                                       |
| `x10`                             | Switch         | X10 wall switches                                                      |
| `fineoffset`                      | Sensor         | **Nexa** LMST-606 / WDS-100 thermometers, Fine Offset weather stations |
| `oregon`                          | Sensor         | Oregon Scientific weather sensors (temp, humidity, rain, wind, UV)     |

> **Nexa note:** Nexa _switches, dimmers, remotes and buttons_ use the `arctech`
> protocol. Nexa _thermometers and weather sensors_ (LMST-606, WDS-100 etc.) use
> the `fineoffset` protocol — they appear automatically as sensor entities.

### TX only (can be controlled but not auto-discovered)

These devices must be added via Method B (self-learning teach).

| Protocol     | Entity type | Example brands / devices   |
| ------------ | ----------- | -------------------------- |
| `brateck`    | Cover       | Brateck motorised blinds   |
| `comen`      | Switch      | Comen devices              |
| `fuhaote`    | Switch      | Fuhaote remote switches    |
| `ikea`       | Switch      | IKEA Koppla 433 MHz        |
| `risingsun`  | Switch      | Rising Sun remote switches |
| `silvanchip` | Switch      | Silvanchip devices         |
| `yidong`     | Switch      | Yidong remotes             |

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
2. Open the app log — raw RF events should appear when a button is pressed
3. Confirm the TellStick Duo USB stick is connected:
   **Settings → Apps → TellStick Local → Hardware**

### "Receiver did not learn the code during teach"

1. Make sure the receiver was in learn mode _before_ clicking Submit
2. Try again — the pairing signal can be re-sent as many times as needed

---

## Support

- [Open an issue on GitHub][issue]

---

## License

GNU General Public License v3.0 or later

Copyright (c) 2019–2024 Erik Hilton
Copyright (c) 2024–2025 R00S (roosfork modifications)

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
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg
[commits-shield]: https://img.shields.io/github/commit-activity/y/R00S/addon-tellsticklive-roosfork.svg
[commits]: https://github.com/R00S/addon-tellsticklive-roosfork/commits/main
[github-actions-shield]: https://github.com/R00S/addon-tellsticklive-roosfork/workflows/CI/badge.svg
[github-actions]: https://github.com/R00S/addon-tellsticklive-roosfork/actions
[issue]: https://github.com/R00S/addon-tellsticklive-roosfork/issues
[maintenance-shield]: https://img.shields.io/maintenance/yes/2025.svg
[project-stage-shield]: https://img.shields.io/badge/project%20stage-experimental-orange.svg
