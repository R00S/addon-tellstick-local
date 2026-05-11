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
