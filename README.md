# Home Assistant Add-on: TellStick Local

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

Local-only TellStick / TellStick Duo support for Home Assistant – no cloud required.

## About

This repository contains:

1. **TellStick Local add-on** (`tellsticklive/`) – runs the `telldusd` daemon and
   exposes it over TCP on ports **50800** (commands) and **50801** (events) via
   socat bridges.  No Telldus Live / cloud connection.

2. **TellStick Local custom integration** (`custom_components/tellstick_local/`) –
   a config-flow–based HA integration that connects to the add-on, subscribes to
   RF events, auto-adds devices, and provides switch, light and sensor entities
   plus device triggers for automations.

> **Note**: The official Home Assistant TellStick add-on was deprecated in
> December 2024 because the underlying Telldus library is no longer maintained.
> This fork continues to provide TellStick support for those who need it.

### Features

- **Local control** – no cloud, no account required
- **Automatic device pairing** – press a remote and the device appears in HA
- **Config flow** – set up the integration via the HA UI
- **Entities** – switch, light (dimmer), and wireless sensor
- **Device triggers** – use RF events in automations
- **Service calls** – control devices via `hassio.addon_stdin`

---

## Quick Start

### 1. Install the Add-on

1. Add this repository to your Home Assistant add-on store:
   `https://github.com/R00S/addon-tellsticklive-roosfork`
2. Find **TellStick Local** and click **Install**
3. Start the add-on
4. Note the hostname printed in the add-on log (e.g. `32b8266a-tellsticklive`)

### 2. Install the Custom Integration

Copy or symlink `custom_components/tellstick_local/` from this repository into
your Home Assistant `config/custom_components/` directory, then restart HA.

### 3. Add the Integration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **TellStick Local**
3. Enter the hostname from the add-on log and accept the default ports
4. Click **Submit**

### 4. Pair Devices (Automatic Add)

1. Open the integration options (⚙ icon) and enable
   **Automatically add new devices**
2. Press the remote or button of the device you want to add
3. The device appears in Home Assistant – rename it as desired

---

## Add-on Configuration

Pre-configure devices if you want to control them immediately without waiting
for an RF event.  See [tellsticklive/DOCS.md](tellsticklive/DOCS.md) for
full details.

```yaml
devices:
  - id: 1
    name: Living Room Light
    protocol: arctech
    model: selflearning-switch
    house: "12345678"
    unit: "1"
```

---

## Migrating from the Old Add-on

If you were using the previous version (with Telldus Live):

1. Remove `enable_live`, `live_uuid`, `live_delay`, and `sensors` from the
   add-on configuration
2. Remove `tellstick:` and platform entries from `configuration.yaml`
3. Install the **TellStick Local** custom integration via the UI
4. Re-pair devices using automatic add if needed

---

## Support

- [Open an issue on GitHub][issue]

## License

GNU General Public License v3.0 or later

Copyright (c) 2019–2024 Erik Hilton
Copyright (c) 2024–2025 R00S (roosfork modifications)

See [LICENSE.md](LICENSE.md) and [NOTICE](NOTICE) for full details.

## Acknowledgments

- **Erik Hilton (erik73)** – Original add-on and telldus-core fork
  - https://github.com/erik73/addon-tellsticklive
  - https://github.com/erik73/telldus
- **Erik Johansson (erijo)** – `tellcore-py` Python bindings
  - https://github.com/erijo/tellcore-py
- **Telldus Technologies AB** – Original TellStick hardware and telldus-core daemon
- **Home Assistant Team** – Platform and original TellStick add-on

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
