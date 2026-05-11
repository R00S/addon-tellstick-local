# Branch: fix-comen-switch-mirror-issue — 3.3.1.x

## Issue

Comen selflearning-switch not working with Mirror / Range Extender (TellStick Net/ZNet).

## Root Cause

The Comen protocol fix (`_decode_comen`, `_encode_comen_command`, and the comen
branches in the decode chain and `_send_rf`) was implemented in
`custom_components/tellstick_local/net_client.py` but was never mirrored to the
runtime copy at `tellsticklive/rootfs/usr/share/tellstick_local/net_client.py`.

HAOS app installs copy the integration from
`tellsticklive/rootfs/usr/share/tellstick_local/` — so only the unpatched version
was actually running. Without the Comen encoder, the integration fell through to
`_encode_generic_command()` which fails silently on TellStick Net/ZNet.

## Fix Applied (3.3.1.1)

Mirrored all four Comen changes to the runtime file:

1. `_decode_comen()` function — reverses house transformation `(house - 2) >> 2`
2. Comen branch in protocol decode chain
3. `_encode_comen_command()` function — applies house transformation `(house << 2) + 2`
4. Comen branch in `_send_rf()` — dispatches to `_encode_comen_command`

## CHORES (3.3.1.2)

- Added standing CHORES.md task: after any runtime mirror operation, verify the two files
  are identical with `diff custom_components/tellstick_local/<file> tellsticklive/rootfs/usr/share/tellstick_local/<file>`
- Bumped version to 3.3.1.2
