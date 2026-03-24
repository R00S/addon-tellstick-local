# Telldus Live Migration Plan

This document describes the strategy for helping users migrate from Telldus Live
to the TellStick Local integration, and the constraints imposed by each device type.

## Background

Telldus Technologies AB shut down (or may shut down) the Telldus Live cloud service.
The TellStick ZNet hardware itself continues to work — it is the cloud service that
disappears, not the device. This integration communicates with the ZNet via its local
UDP interface and needs no cloud connectivity at all.

The challenge for migration is that different device types have fundamentally
different constraints.

---

## Device type migration matrix

| Device type | Can pre-create without hardware? | Migration strategy |
|---|---|---|
| **433 MHz self-learning (arctech / 909xx)** | ✅ Yes | Pre-create devices in bulk via ZNet REST API, teach receivers any time |
| **433 MHz fixed-code (everflourish, waveman, etc.)** | ✅ Yes | Pre-create via REST API or press-to-discover |
| **Z-Wave** | ❌ No — physical inclusion required | Existing included devices are already saved; discovery-only for new ones |

---

## 433 MHz devices (arctech / selflearning / 909xx)

### Why pre-creation works

Arctech self-learning receivers (Nexa, KAKU, Proove, Intertechno, Anslut, etc.)
are protocol-agnostic: they learn whatever house/unit code is _sent to them_
during a teach sequence. The house/unit code is just a number — it can be chosen
freely and pre-created in the ZNet database via the REST API before any physical
device is touched.

This means:
- A user can set up their HA integration and devices **before** Telldus Live
disappears, purely by creating arctech proxy entries.
- After Telldus Live goes away, the user can still **teach new physical receivers**
to those pre-created codes using the "Send learn signal" button in HA.
- Devices the user currently controls via Telldus Live can be **migrated** by
matching their existing house/unit codes in the integration.

### Pre-creation via ZNet local REST API

The ZNet exposes a local REST API (no cloud, no account needed) that allows
creating arctech self-learning device entries:

```bash
# Authenticate first (if firmware requires it)
curl -X POST http://<ZNET_IP>/api/user/authenticateApplication \
  -H "Content-Type: application/json" \
  -d '{"password": "<local-password>"}'

# Create an arctech selflearning device
curl -X POST http://<ZNET_IP>/api/device/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Living Room Lamp",
    "protocol": "arctech",
    "model": "selflearning-switch",
    "parameters": [
      {"name": "house", "value": "12345678"},
      {"name": "unit",  "value": "1"}
    ]
  }'
```

Once created, these devices appear in the ZNet database permanently — even after
Telldus Live disappears. The HA integration discovers them via the same local API.

### Teaching new receivers after Telldus Live is gone

With the integration set up and devices created:

1. Buy any arctech / selflearning-compatible receiver (Nexa, KAKU, Proove, etc.)
2. Put the receiver in **learn mode** (hold its button until it blinks)
3. In HA, go to the device's page and press **"Send learn signal"**
4. The receiver learns the code — no cloud, no Telldus Live needed

This workflow is **fully functional** without Telldus Live.

---

## Z-Wave devices

### Why pre-creation is impossible

Z-Wave inclusion is a **protocol-level requirement** — it cannot be bypassed or
pre-emulated. During inclusion, the controller and device:

1. Exchange a unique **Node ID** assigned by the controller
2. Perform a cryptographic **security key exchange** (S0 / S2)
3. Exchange a **Node Information Frame (NIF)** where the device announces its
   command classes and capabilities

None of this information can be fabricated or pre-loaded. A ghost Z-Wave entry
without a real device behind it will simply never respond, causing network
instability.

**The ZNet is the Z-Wave controller.** Telldus Live was the cloud UI layered on
top of it. This means:

> ✅ All Z-Wave devices a user has **already included** into their ZNet are
> permanently stored in the ZNet's Z-Wave network database — completely
> independent of Telldus Live.

When Telldus Live disappears, those Z-Wave devices remain in the ZNet and are
immediately accessible via the local REST API. The HA integration discovers them
automatically on first setup.

### What is lost when Telldus Live disappears

| Scenario | Impact |
|---|---|
| Z-Wave devices already included in ZNet | ✅ No impact — devices survive, HA discovers them |
| Including **new** Z-Wave devices | ✅ Still possible — inclusion is a local ZNet operation, no cloud needed |
| Z-Wave devices **never** included | ❌ Cannot be added without physical inclusion |

### Migration steps for Z-Wave users

1. **Before Telldus Live shuts down (ideal):** No action needed for existing
devices — they are already in the ZNet.
2. **Include any Z-Wave devices you intend to use** while you still have the
   ZNet configured (inclusion is local, but good to do before any instability).
3. **Install this integration** — it discovers all included Z-Wave nodes via
the ZNet local API automatically.

---

## Summary: per-device-type action plan

### 433 MHz / arctech / selflearning (909xx)

- ✅ Pre-create device entries in ZNet via local REST API
- ✅ Teach physical receivers using "Send learn signal" in HA (no cloud needed)
- ✅ Existing Telldus Live devices: match house/unit codes in HA integration
- ✅ New receivers: buy and teach at any time after migration

### Z-Wave

- ✅ All currently included devices are safe — stored in ZNet hardware
- �� New inclusions: fully local (physical button press + ZNet web UI)
- ❌ Cannot pre-create Z-Wave devices without physical device presence
- ✅ HA discovery: automatic after installing this integration

---

## Further reading

- [ZNet local REST API reference](https://api.telldus.com/) *(community-documented)*
- [Pairing devices](../README.md#pairing-devices)
- [Migrating from the old add-on](../README.md#migrating-from-the-old-add-on-with-telldus-live)