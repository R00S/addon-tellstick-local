# Branch: fix-issue-104-not-solved — 3.3.1.x

## Issue

Comen selflearning-switch not working with Mirror / Range Extender (TellStick Net/ZNet).
Version 3.3.1.2 fixed the missing runtime copy of the Comen encoder but the issue
persists because there is a second, independent bug (see below).

## Two Separate Problems

### Problem 1 (less urgent): ZNet Comen encoder was missing from runtime copy

**Status: Fixed in v3.3.1.1 / v3.3.1.2 (PR #108)**

`_encode_comen_command` and `_decode_comen` were added to
`custom_components/tellstick_local/net_client.py` but were never mirrored to
`tellsticklive/rootfs/usr/share/tellstick_local/net_client.py`.
PR #108 mirrored them. Both files are now identical.

### Problem 2 (URGENT): RF collision — primary Duo stops working when mirror is added

**Root cause**: `tdTurnOn()` / `tdTurnOff()` return from TCP as soon as the TellStick
firmware ACKs the USB command — **before the RF transmission is complete**.

The arctech selflearning signal for 10 repeats takes approximately 350–500 ms to
transmit. The firmware ACKs within ~2–5 ms (just buffering the command). So
`_controller.turn_on()` returns after ~5 ms while the Duo is still transmitting.

The mirror command is then fired immediately, causing the ZNet to also start
transmitting. With both devices transmitting on 433 MHz at the same time:

- RF signals overlap → constructive/destructive interference  
- Receiver cannot decode either signal  
- Physical device does not respond  
- Switch appears completely broken (though the HA state optimistically updates)

**Symptom**: Works perfectly with mirror disabled; breaks completely when mirror
is enabled — because without a mirror there is only one transmitter.

## Fix Applied (3.3.1.3)

Added `_RF_MIRROR_DELAY_S = 0.35` (350 ms) delay in
`entity.py::_async_mirror_command`, triggered only when mirrors are actually
present. This ensures the primary RF transmission completes before the mirror
begins its own transmission.

Additionally, `async_write_ha_state()` was moved to **before** the mirror command
in `switch.py` so the UI updates immediately (when the primary command is sent),
not 350 ms later.

Both files mirrored to `tellsticklive/rootfs/usr/share/tellstick_local/`.

## Why 350 ms?

Arctech selflearning per-repeat timing:
- Sync: ~10 ms
- 32 bits × ~640 µs/bit average ≈ 20 ms per repeat
- 10 repeats × ~30 ms = ~300 ms + gaps = ~350 ms total

350 ms ensures the primary RF is complete. The mirror then sends a reinforcing
transmission which the receiver can decode cleanly.

## Follow-up (3.3.1.4): 350 ms was too short for Comen — bumped to 700 ms

User reproduced "Duo emits corrupted Comen when ZNet mirror is present" on
their own hardware after 3.3.1.3 was deployed. rtl_433 captures provided:

- **Without mirror**: clean Comen frames, OOK_PPM `short_width 224 µs /
  long_width 1256 µs`, 32 bits, 4–6 frames per press, aggregate burst width
  **`Total count: 462, width: 533.18 ms`**.
- **With ZNet mirror**: the 224/1256 32-bit signature is **absent** from the
  log. Instead a dense burst of `Detected OOK package` and `Detected FSK
  package` lines with `Guessing modulation: No clue…` — the textbook
  fingerprint of two co-located 433.92 MHz transmitters jamming each other.

### Code-path audit (no Duo state mutation found)

For a Duo primary + ZNet mirror, the following touch the Duo's telldusd
device registry and outgoing TX:

| Code path                          | Mutates Duo telldusd state? |
| ---------------------------------- | --------------------------- |
| `_register_mirror_devices(NET)`    | No — only fills `mirror_device_id_map` |
| `_setup_mirror_entry`              | No — starts ZNet UDP listener only |
| `_mirror_event_callback`           | No — callback on ZNet controller |
| `_async_mirror_command`            | Sleeps then calls **ZNet's** `turn_on` |
| Mirror entry's stored devices      | Empty (`options={}` at create time) |

`tdTurnOn(int_id)` is what the Duo always sends; telldusd encodes from its
own registry which only the primary populates. There is no path by which
adding a ZNet mirror entry can change the bytes the Duo emits.

### Why 350 ms was not enough — timeline math

```
t=0       Duo TCP send acked (~5 ms)
t=5ms     Duo RF starts
t=355ms   ZNet UDP send fires (after _RF_MIRROR_DELAY_S = 0.35 sleep)
t=365ms   ZNet RF starts          ← Duo still has ~170 ms left
t=535ms   Duo RF ends             ← 170 ms of overlap → frames jammed
t=900ms   ZNet RF ends
```

For ~170 ms both transmitters are simultaneously on air at 433.92 MHz.
At the receiver this produces constructive/destructive interference that
destroys all overlapping Duo frames — observationally indistinguishable
from "the Duo is sending corrupted bytes".

### Fix

`_RF_MIRROR_DELAY_S` bumped from **0.35 → 0.7 s** in:
- `custom_components/tellstick_local/entity.py`
- `tellsticklive/rootfs/usr/share/tellstick_local/entity.py`

0.7 s exceeds the worst-case observed Comen burst width (533 ms) with margin,
and remains safe for the shorter arctech/everflourish bursts that motivated
the original 0.35 s value.

manifest.json bumped 3.3.1.3 → 3.3.1.4 in both locations.

## 3.3.1.5 — CHORES bump

Routine version bump per `CHORES.md` (D digit). No code changes; manifest
bumped 3.3.1.4 → 3.3.1.5 in both `custom_components/tellstick_local/` and
`tellsticklive/rootfs/usr/share/tellstick_local/`.
