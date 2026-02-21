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

## Next steps

After the app starts, the **TellStick Local** integration is automatically installed
into `/config/custom_components/`. No HACS or manual download is needed.

All device management happens in the integration under **Settings → Devices & Services
→ TellStick Local**:

- **Automatic add** — click **Configure** (⚙), enable it, then press any 433 MHz
  remote to discover devices
- **Add device button** — click **Add device** on the integration card to manually
  pair a self-learning receiver (pick type, send pairing signal)
- **Remove a device** — go to the device page and select **Delete** from the ⋮ menu

See the [project README](https://github.com/R00S/addon-tellsticklive-roosfork) for
full pairing instructions and supported devices.

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
| `learn`    | No       | Send learn signal on next restart (`true`/`false`)         |

Restart the app after changing the device list.

**Supported protocols:** arctech, brateck, comen, everflourish, fineoffset, fuhaote,
hasta, ikea, mandolyn, oregon, risingsun, sartano, silvanchip, upm, waveman, x10, yidong

---

## Pairing self-learning devices

Self-learning devices (Nexa, Proove, Luxorparts, and other arctech-compatible
switches) must be paired using a **learn** signal. Sending a normal `on` command
is **not** sufficient — the receiver needs a special learning sequence to register
the house/unit code.

### Step-by-step pairing

1. **Configure the device** in the app configuration:

   ```yaml
   devices:
     - id: 1
       name: "My Switch"
       protocol: arctech
       model: selflearning-switch
       house: "12345678"
       unit: "1"
   ```

   For self-learning devices, the `house` code can be any number between 1 and 67108863. The receiver learns whatever code you send it.

2. **Restart the app** to apply the configuration.

3. **Put the receiver into learning mode** by pressing and holding its learning
   button until the indicator LED lights up or blinks.

4. **Send a learn command** using one of these methods:

   **Option A — GUI toggle:** Set `learn: true` on the device, then restart the
   app. The learn signal is sent automatically on startup.

   ```yaml
   devices:
     - id: 1
       name: "My Switch"
       protocol: arctech
       model: selflearning-switch
       house: "12345678"
       unit: "1"
       learn: true
   ```

   Set `learn` back to `false` after pairing is complete.

   **Option B — Service call:**

   ```yaml
   service: hassio.addon_stdin
   data:
     addon: YOUR_ADDON_SLUG
     input:
       function: "learn"
       device: 1
   ```

5. The receiver should click or blink to confirm it has learned the code.

6. **Repeat** for each additional receiver, using a different `unit` value.

Once paired, you can control the device with normal on/off commands through the
**TellStick Local** integration.

### Luxorparts 50969 and similar switches

The Luxorparts 50969 remote sends a **two-part signal**: first a codeswitch signal,
then a self-learning signal. The TellStick Duo detects the remote as a **codeswitch**
device (e.g., house A, unit 3), but the 50969 **receiver only responds to the
self-learning protocol**.

**If you configure the device as `codeswitch` based on what the TellStick Duo detects
from the remote, the switch will NOT respond.** You must configure it as
`selflearning-switch` and pair it using the learn function described above.

The 50969 receiver learns from **ON signals only**. The `learn` function handles
this correctly.

**Example configuration for Luxorparts 50969:**

```yaml
devices:
  - id: 1
    name: "Luxorparts Switch"
    protocol: arctech
    model: selflearning-switch
    house: "5096900"
    unit: "1"
    learn: true
```

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
Copyright (c) 2024–2026 R00S (roosfork modifications)

[issue]: https://github.com/R00S/addon-tellsticklive-roosfork/issues
