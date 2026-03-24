# Telldus Live Shutdown — Migration Plan (Future Work)

This document captures the technical plan for helping users migrate away from
Telldus Live if the service shuts down. **Nothing described here is implemented yet.**
It serves as a reference for future development.

---

## Background

The TellStick ZNet connects to Telldus Live over the cloud. If Telldus Live
disappears, users who depend on it to control and configure their ZNet devices
will lose that ability. This integration already operates fully locally, but
there are two device categories that need different migration strategies:

- **433 MHz switches (arctech/selflearning, a.k.a. 909xx-type devices)** — can be
  pre-provisioned on the ZNet without the physical device present.
- **Z-Wave devices** — require physical inclusion; cannot be created in advance.

---

## Strategy: 433 MHz / selflearning devices

The ZNet exposes a local REST API that can create arctech selflearning device
entries without the physical receiver being present. This means:

1. A one-time preparation script can pre-create a set of proxy devices on the
   ZNet via `POST /api/device/add` (house code + unit code only — no physical
   device needed).
2. The user puts their receiver in learn mode and triggers a learn signal from
   the HA device page — exactly as today, just without Telldus Live involved.
3. The integration discovers the proxy devices on startup via `/api/devices/list`
   and presents them in HA.

**Key point:** The user can add new 433 MHz receivers and teach them codes even
after Telldus Live is gone, because the ZNet REST API is fully local.

### Implementation tasks (not done)

- [ ] Add a ZNet REST API client for local device creation (`POST /api/device/add`)
- [ ] Verify local bearer token auth flow (`/api/user/authenticateApplication`)
- [ ] Add a "Prepare ZNet for offline use" flow or script that pre-creates
      arctech selflearning proxy devices in bulk
- [ ] Verify that devices created via REST are persistent across ZNet reboots

---

## Strategy: Z-Wave devices

Z-Wave inclusion is a mandatory protocol-level operation — a Node ID,
security keys (S0/S2), and the device's command classes are all exchanged
during physical inclusion. **There is no way to pre-create a Z-Wave device
entry without the physical device present.**

However, for users migrating from Telldus Live:

> **The Z-Wave devices are already included in the ZNet.** The ZNet _is_ the
> Z-Wave controller. Telldus Live was only the cloud UI on top. Switching to
> local-only operation does not require re-inclusion of existing Z-Wave devices.

The integration can discover all already-included Z-Wave nodes via
`/api/devices/list` on the local REST API — no Telldus Live involvement needed.

**Limitation:** Any Z-Wave device that was *not* included before Telldus Live
shuts down cannot be added afterwards without a local Z-Wave inclusion tool
(e.g. a separate Z-Wave USB stick + Z-Wave JS). This is a Z-Wave protocol
constraint, not a limitation of this integration.

### Implementation tasks (not done)

- [ ] Verify that all existing Z-Wave nodes are returned by `/api/devices/list`
      on a ZNet that has never connected to Telldus Live
- [ ] Document the Z-Wave inclusion limitation clearly in the user-facing docs
      once the feature is implemented

---

## Summary

| Device type | Can prepare without device? | Migration path |
|---|---|---|
| 433 MHz selflearning (arctech) | ✅ Yes — REST API pre-create | Pre-create proxies; user teaches receiver as normal |
| Z-Wave | ❌ No — physical inclusion required | Already included nodes are discoverable locally; new nodes cannot be added without physical inclusion tooling |

---

## References

- ZNet local REST API (community reverse-engineered): `http://<znet-ip>/api/`
- Z-Wave inclusion protocol: mandatory Node ID + security key exchange at pairing time
- See also: `custom_components/` source for the existing local UDP client