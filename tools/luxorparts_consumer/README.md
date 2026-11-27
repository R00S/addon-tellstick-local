# Luxorparts socket — test consumer

A minimal Home Assistant integration that owns one Luxorparts 433 MHz socket:

- `luxorparts.py` — the protocol (25-bit OOK-PWM, timings in µs).
- `config_flow.py` — pick a `radio_frequency` transmitter and a house/unit.
- `switch.py` — ON/OFF through `radio_frequency.async_send_command()`.
- `button.py` — **Learn**: the 48-repeat burst that pairs a socket.

It exists to prove the transmitter end to end from the consumer side, with the
protocol inside the consumer rather than in the transmitter provider.

## Install

Copy `custom_components/luxorparts_test` into `/config/custom_components/` and
restart Home Assistant. Then **Settings → Devices & services → Add integration
→ Luxorparts Socket (test consumer)**.

## Pair a socket

1. Put the socket in learn mode (hold its button until the LED blinks).
2. Press the entry's **Learn** button within the learn window.
3. Toggle the switch.

Remove the folder to uninstall.
