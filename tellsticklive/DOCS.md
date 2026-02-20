# TellStick Local

TellStick and TellStick Duo local service – no cloud, no Telldus Live.

![Supports aarch64 Architecture][aarch64-shield] ![Supports amd64 Architecture][amd64-shield]
![Supports armhf Architecture][armhf-shield] ![Supports armv7 Architecture][armv7-shield]
![Supports i386 Architecture][i386-shield]

## About

This add-on runs the Telldus `telldusd` daemon and exposes it over TCP
(via socat bridges on ports **50800** and **50801**) so that the
**TellStick Local** custom integration can communicate with it from
Home Assistant. There is no Telldus Live cloud connection.

**Acknowledgments:**

- Fork of [erik73's addon-tellsticklive](https://github.com/erik73/addon-tellsticklive)
- Based on the now-deprecated official Home Assistant TellStick add-on
- Uses a fork of telldus-core maintained by [erik73](https://github.com/erik73/telldus)

## Installation

1. Add this repository to your Home Assistant add-on store:
   `https://github.com/R00S/addon-tellsticklive-roosfork`
2. Find the **TellStick Local** add-on and click **INSTALL**
3. (Optional) Configure pre-known devices – see Configuration below
4. Start the add-on
5. Install the **TellStick Local** custom integration from
   `custom_components/tellstick_local/` in this repository

## Configuration

You can optionally pre-configure devices so the integration can control
them immediately. If you use **automatic add** in the integration, you
do not need to list devices here – they will be discovered when you press
a remote.

```yaml
devices:
  - id: 1
    name: Living Room Light
    protocol: arctech
    model: selflearning-switch
    house: "12345678"
    unit: "1"
  - id: 2
    name: Kitchen Switch
    protocol: arctech
    model: selflearning-switch
    house: A
    unit: "4"
```

Each device entry requires:

| Option     | Required | Description                                                |
| ---------- | -------- | ---------------------------------------------------------- |
| `id`       | Yes      | Unique numeric identifier (≥ 1)                            |
| `name`     | Yes      | Human-readable name                                        |
| `protocol` | Yes      | RF protocol (arctech, everflourish, …)                     |
| `model`    | No       | Device model (selflearning-switch, selflearning-dimmer, …) |
| `house`    | No       | House code                                                 |
| `unit`     | No       | Unit code                                                  |
| `code`     | No       | Code (for some protocols)                                  |
| `fade`     | No       | Enable fade for dimmers                                    |

Restart the add-on after changing the device list.

## How to pair new devices (automatic add)

1. Start the add-on and confirm it logs:
   `TellStick Local is ready!`
2. In Home Assistant go to **Settings → Devices & Services → Add Integration**
   and search for **TellStick Local**.
3. Enter the hostname shown in the add-on log and click **Submit**.
4. Open the integration options and enable **Automatically add new devices**.
5. Press the button or remote of the device you want to pair.
6. The device appears in Home Assistant automatically.
7. Rename it under **Settings → Devices & Services → TellStick Local**.

## Service calls (stdin)

You can still control pre-configured devices via `hassio.addon_stdin`:

Turn on device 1:

```yaml
service: hassio.addon_stdin
data:
  addon: 32b8266a_tellsticklive
  input:
    function: "on"
    device: 1
```

Turn off device 1:

```yaml
service: hassio.addon_stdin
data:
  addon: 32b8266a_tellsticklive
  input:
    function: "off"
    device: 1
```

Set dimmer level (0–255):

```yaml
service: hassio.addon_stdin
data:
  addon: 32b8266a_tellsticklive
  input:
    function: "dim"
    device: 2
    level: 128
```

List configured devices:

```yaml
service: hassio.addon_stdin
data:
  addon: 32b8266a_tellsticklive
  input:
    function: "list"
```

List detected sensors:

```yaml
service: hassio.addon_stdin
data:
  addon: 32b8266a_tellsticklive
  input:
    function: "list-sensors"
```

## Troubleshooting

### Integration cannot connect

1. Confirm the add-on is **running** and the log shows `TellStick Local is ready!`
2. Verify the hostname in the integration matches the one in the add-on log
3. Ports **50800** and **50801** must be reachable from the HA core container

### No devices appear after pressing remote

1. Make sure **Automatically add new devices** is enabled in the integration options
2. Check the add-on log – raw RF events should appear when a button is pressed
3. Ensure the TellStick USB stick is connected (check **Settings → Add-ons → TellStick Local → Hardware**)

### Device protocol format

| Field      | Example               | Notes                                                                            |
| ---------- | --------------------- | -------------------------------------------------------------------------------- |
| `protocol` | `arctech`             | Must be a supported protocol identifier                                          |
| `model`    | `selflearning-switch` | Optional model name, optionally with brand suffix (`selflearning-switch:proove`) |

**Supported protocols:** arctech, brateck, comen, everflourish, fineoffset, fuhaote,
hasta, ikea, kangtai, mandolyn, oregon, risingsun, sartano, silvanchip, upm, waveman, x10, yidong

## Support

- [Open an issue on GitHub][issue]

## License

GNU General Public License v3.0 or later

Copyright (c) 2019–2024 Erik Hilton
Copyright (c) 2024–2025 R00S (roosfork modifications)

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg
[issue]: https://github.com/R00S/addon-tellsticklive-roosfork/issues
