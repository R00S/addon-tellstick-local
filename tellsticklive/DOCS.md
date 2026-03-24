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

- Originally based on [erik73's addon-tellsticklive](https://github.com/erik73/addon-tellsticklive) (thank you!)
- Based on the now-deprecated official Home Assistant TellStick add-on
- Uses [erik73's telldus-core fork](https://github.com/erik73/telldus) for the daemon build

---

## Installation

1. In HAOS go to **Settings → Apps → ⋮ → Repositories**
2. Add: `https://github.com/R00S/addon-tellstick-local`, category **App**
3. Find **TellStick Local** in the store and click **Install**
4. Click **Start** and wait for the log to show `TellStick Local is ready!`

After the app starts, Home Assistant automatically shows a notification:

> **New device found: TellStick Local — Set up?**

Click it and then **Submit** — no host or port entry is needed.

If the notification does not appear, go to **Settings → Devices & Services →
Add Integration**, search for **TellStick Local**, and run the manual setup.
If the host field is empty, check the app log for the line
`use host: …  ports: 50800 / 50801` and enter that hostname.

---

## Next steps

After the app starts, the **TellStick Local** integration is automatically installed
into `/config/custom_components/`. No HACS or manual download is needed.

All device management happens in the integration under **Settings → Devices & Services
→ TellStick Local**:

- **Automatic add** — click **Configure** (⚙), enable it, then press any 433 MHz
  remote to discover devices
- **Sartano opt-in** — sartano/codeswitch auto-detection is **off by default**
  because arctech signals are often falsely decoded as sartano. Enable the
  **"Detect sartano/codeswitch devices"** toggle in **Configure → Settings** if
  you have real sartano hardware
- **Add device button** — click **Add device** on the integration card, then choose
  **Add by brand** (browse by brand name, e.g. "Nexa — Self-learning on/off") or
  **Add by protocol** (pick by protocol name, e.g. "arctech — Self-learning on/off")
- **Ignore unwanted devices** — check "Ignore this device" on the discovery form to
  permanently hide false-positive detections
- **Learn button** — each switch/light device has a "Send learn signal" button on
  its device page to re-pair without deleting the device
- **Edit device** — change name, house/unit codes, or sensor ID via **Configure** (⚙)
  → **Edit a device** (entity ID and history are preserved)
- **Replace device** — when a sensor gets a new ID after battery replacement, the
  discovery form has a "Replace existing device" dropdown to migrate in one step
- **Remove devices** — delete from the device page ⋮ menu, or remove multiple from
  **Configure** (⚙) → **Remove multiple devices**
- **Manage ignored** — un-ignore devices from **Configure** (⚙) → **Manage ignored
  devices**

See the [project README](https://github.com/R00S/addon-tellstick-local) for
full pairing instructions and supported devices.

> **Upgrade notifications:** When the app updates the integration code, HA shows a
> persistent notification if a restart is needed. Go to
> **Settings → Developer tools → Restart** to apply the update.

---

## Mirror / range extender

If you have a **second TellStick** (Duo or Net/ZNet), you can set it up as a
**mirror** to extend RF coverage. The mirror replicates all commands sent to
the primary TellStick's devices and forwards received RF events back to the
primary for device detection and state updates.

This works across backend types — a TellStick Net/ZNet can mirror a Duo and
vice versa.

### How to set up

1. Make sure the primary TellStick is already set up in HA
2. Connect and start your second TellStick
3. Go to **Settings → Devices & Services → TellStick Local** and click
   **Add Hub** on the integration card
4. Choose the hardware type and enter its connection details
5. On the **"Mirror / range extender"** step, select the primary TellStick
   from the dropdown
6. Click **Submit**

The mirror appears as _"TellStick (mirror of Primary)"_ in Devices & Services.
It shares the primary's devices — no separate device management needed.

> **No Telldus Live required (Net/ZNet):** This integration talks to the Net/ZNet
> locally — no cloud account needed. If you also use Telldus Live on the same
> device, the two do not interfere — both work simultaneously.

---

## Optional: pre-configure devices

You only need this if you want to control a TX-only device (one that cannot send
RF signals itself) and want it available before any RF event arrives.

For all other devices (Nexa remotes, KAKU switches, Oregon sensors, etc.) just
use **automatic add** in the integration — no configuration here is needed.

### What happens when you add devices here?

When the app starts, the integration **automatically imports** any device in this
list that it does not already manage. Imported devices appear in
**Settings → Devices & Services → TellStick Local** exactly like any device added
through the GUI — you can rename, edit, or delete them from the integration's
Configure flow without touching YAML again.

> **One-way, one-time import.** After a device has been imported, the integration
> owns it. Changes you make to that device in this YAML list later are **not**
> reflected automatically in the integration — use the integration GUI to edit it
> instead. If you remove a device from this list, the integration entity is **not**
> deleted automatically; delete it via the integration.

> **Sensor protocols excluded.** Devices with `fineoffset`, `oregon`, or `mandolyn`
> protocol are never imported from this list — they appear automatically in HA when
> the sensor transmits its first RF signal.

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

Self-learning devices (Nexa, Proove, and other arctech-compatible
switches) must be paired using a **learn** signal. Sending a normal `on` command
is **not** sufficient — the receiver needs a special learning sequence to register
the house/unit code.

### Recommended: GUI pairing

The easiest way to pair self-learning devices is through the HA GUI:

1. **Add the device** via **Settings → Devices & Services → TellStick Local →
   Add device** — pick your device type, submit
2. **Put the receiver in learn mode** (hold its button until it blinks)
3. On the new device's page, press the **"Send learn signal"** button
4. The receiver stops blinking, confirming it learned the code

To **re-pair** a device later (e.g. after moving it), just press the "Send learn
signal" button on the device page again — no need to delete and re-add.

### Alternative: App configuration

You can also pre-configure devices in the app configuration. This is mainly useful
for TX-only devices or headless setups.

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

### ⛔ Luxorparts / Cleverio 50969, 50970, 50972 — NOT WORKING

These specific Luxorparts / Cleverio 1000W sockets **are not supported** and have
been removed from the "Add by brand" picker.

Learn and on/off signals sent via TellStick Duo or TellStick Net/ZNet are not
acknowledged by these receivers. Telldus Live controls them successfully via ZNet,
but the exact signal path it uses is not accessible through our interface.

Further investigation would require an **RTL-SDR USB dongle** to capture and
analyse the raw RF signal from the original remote. If you have an RTL-SDR
and find a working approach, please
[open an issue](https://github.com/R00S/addon-tellstick-local/issues).

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

### App version shows "dev" instead of a real version number

If the app version displays **dev** instead of a numbered version (e.g. 2.4.11.0),
the HAOS Supervisor did not find the correct stable release. To fix this:

1. **Uninstall** the app: Settings → Apps → TellStick Local → ⋮ → Uninstall
2. **Remove the repository**: Settings → Apps → ⋮ → Repositories → remove
   `https://github.com/R00S/addon-tellstick-local`
3. **Re-add the repository**: Settings → Apps → ⋮ → Repositories → add
   `https://github.com/R00S/addon-tellstick-local`, category **App**
4. **Install** TellStick Local from the store — it should now show the correct
   version number

> **Why this happens:** AwesomeVersion (used by the HAOS Supervisor) treats the
> string "dev" as a higher version than any numeric version. Once an app is
> installed with "dev", the Supervisor will never offer a numeric update because
> it considers "dev" to already be the newest version.

---

## Debugging with Developer Tools → Events

You can monitor raw 433 MHz traffic in real time using the Home Assistant
**Developer Tools → Events** page. This is useful for verifying that your
TellStick hardware is receiving RF signals and for diagnosing detection issues.

### Listening for events

1. Go to **Developer Tools → Events** (or press `e` on the HA keyboard shortcut)
2. In the **Listen to events** section, enter: `tellstick_local_event`
3. Click **Start listening**
4. Press a 433 MHz remote button — you should see events appear

### Event types

**Duo backend** — decoded RF events appear as:

```yaml
event_type: tellstick_local_event
data:
  type: raw
  protocol: arctech
  model: selflearning
  house: "2673666"
  unit: "1"
  method: turnon
```

**ZNet/Net backend** — raw packets from the ZNet firmware appear as:

```yaml
event_type: tellstick_local_event
data:
  type: znet_raw_packet
  protocol: arctech
  model: selflearning
  data: "0x511f590"
```

For the ZNet backend, the `data` field contains the raw RF payload as a hex
integer. The integration decodes this automatically for supported protocols
(arctech, waveman, sartano, everflourish, x10, hasta). If you see
`znet_raw_packet` events but no device is detected, it may mean the protocol
decoder is missing or the deduplication window is suppressing repeated signals.

### What to check

- **No events at all** — the TellStick hardware is not receiving signals.
  Check USB connection, antenna, and that the app is running.
- **Events appear but no device detected** — check that `automatic_add` is
  enabled in the integration options (Settings → Devices & Services →
  TellStick Local → Configure). Also check that the protocol is supported.
- **Multiple events per button press** — this is normal. The TellStick Duo
  runs all protocol decoders on every RF signal, so one button press can
  produce events for arctech, everflourish, and waveman simultaneously.
  Only the correct protocol should be added; the others are false positives.

---

## Support

- [Open an issue on GitHub][issue]

## License

GNU General Public License v3.0 or later

Copyright (c) 2019–2024 Erik Hilton
Copyright (c) 2024–2026 R00S

[issue]: https://github.com/R00S/addon-tellstick-local/issues
