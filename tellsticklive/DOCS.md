# TellStick Local

TellStick Duo local service for Home Assistant – no cloud, no Telldus Live.

## About

This app runs the Telldus `telldusd` daemon inside a Docker container managed by
the HAOS Supervisor and exposes it over TCP via socat bridges:

- **Port 50800** – command socket (turn on/off, dim)
- **Port 50801** – event socket (real-time RF events from remotes and sensors)

It exists because HAOS only allows USB hardware passthrough to Supervisor-managed
containers — a custom integration has no USB access. The app handles the hardware;
the **TellStick Local** integration handles everything in the HA UI.

**Acknowledgments:**

- Fork of [erik73's addon-tellsticklive](https://github.com/erik73/addon-tellsticklive)
- Based on the now-deprecated official Home Assistant TellStick add-on
- Uses a fork of telldus-core maintained by [erik73](https://github.com/erik73/telldus)

---

## Installation

1. In HAOS go to **Settings → Apps → ⋮ → Repositories**
2. Add: `https://github.com/R00S/addon-tellsticklive-roosfork`, category **App**
3. Find **TellStick Local** in the store and click **Install**
4. Click **Start** and wait for the log to show `TellStick Local is ready!`

After the app starts, Home Assistant automatically shows a notification:

> **New device found: TellStick Local — Set up?**

Click it and then **Submit** — no host or port entry is needed.

If the notification does not appear, go to **Settings → Devices & Services →
Add Integration**, search for **TellStick Local**, and run the manual setup.

---

## Next steps: install the integration

All device management (pairing, naming, automations) happens in the
**TellStick Local** custom integration, installed via HACS:

1. In HACS click **⋮ → Custom repositories**
2. Add: `https://github.com/R00S/addon-tellsticklive-roosfork`, category **Integration**
3. Find **TellStick Local**, click **Download**, then restart Home Assistant

See the [project README](https://github.com/R00S/addon-tellsticklive-roosfork) for
full pairing and device management instructions.

---

## Optional: pre-configure devices

You only need this if you want to control a TX-only device (one that cannot send
RF signals itself) and want it available before any RF event arrives.

For all other devices (Nexa remotes, KAKU switches, Oregon sensors, etc.) just
use **automatic add** in the integration — no configuration here is needed.

```yaml
devices:
  - id: 1
    name: Bedroom Blind
    protocol: brateck
    model: ""
    house: "1"
    unit: "1"
```

| Option     | Required | Description                                                |
| ---------- | -------- | ---------------------------------------------------------- |
| `id`       | Yes      | Unique numeric identifier (≥ 1)                            |
| `name`     | Yes      | Human-readable name                                        |
| `protocol` | Yes      | RF protocol (see list below)                               |
| `model`    | No       | Device model (selflearning-switch, selflearning-dimmer, …) |
| `house`    | No       | House code                                                 |
| `unit`     | No       | Unit code                                                  |
| `code`     | No       | Code (for code-based protocols)                            |
| `fade`     | No       | Enable fade for dimmers (`true`/`false`)                   |

Restart the app after changing the device list.

**Supported protocols:** arctech, brateck, comen, everflourish, fineoffset, fuhaote,
hasta, ikea, mandolyn, oregon, risingsun, sartano, silvanchip, upm, waveman, x10, yidong

---

## Troubleshooting

### App log shows errors at startup

- Check **Settings → Apps → TellStick Local → Hardware** — the TellStick Duo
  USB stick must be listed there
- Try unplugging and re-plugging the USB stick, then restart the app

### Integration cannot connect

- Confirm the app is **running** and the log shows `TellStick Local is ready!`
- Ports 50800 and 50801 are on the Supervisor internal network — no manual
  firewall configuration is needed

### No RF events in the log when pressing a remote

- The TellStick Duo must be **physically connected** to the HAOS machine
- Verify USB is visible under the app Hardware tab
- Try a different USB port or a short USB extension cable to improve reception

---

## Support

- [Open an issue on GitHub][issue]

## License

GNU General Public License v3.0 or later

Copyright (c) 2019–2024 Erik Hilton
Copyright (c) 2024–2025 R00S (roosfork modifications)

[issue]: https://github.com/R00S/addon-tellsticklive-roosfork/issues
