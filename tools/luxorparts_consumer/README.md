# Luxorparts socket — test consumer

A minimal Home Assistant integration that owns one Luxorparts 433 MHz socket:

- `luxorparts.py` — the protocol (25-bit OOK-PWM timings) and the 24 verified
  ON/OFF pairs captured from Telldus Live and confirmed at a receiver.
- `config_flow.py` — pick a `radio_frequency` transmitter and one of the 24
  devices. One parameter, no house/unit matrix: the recorded number *is* the
  address, so LPD 11 sends exactly what `switch.server` sends.
- `switch.py` — ON/OFF through `radio_frequency.async_send_command()`.
- `button.py` — **Learn**: the 48-repeat burst that pairs a socket.

It exists to prove the transmitter end to end from the consumer side, with the
protocol inside the consumer rather than in the transmitter provider.

## Install

Copy `custom_components/luxorparts_test` into `/config/custom_components/` and
restart Home Assistant. Then **Settings → Devices & services → Add integration
→ Luxorparts Socket (test consumer)**.

## Pair a socket

1. Pick the number whose socket you are testing (LPD 11 = house 11, unit 1).
2. If the socket already answers that pair, toggle the switch — no pairing.
3. For a socket paired to something else, hold its button until the LED
   blinks, then press the entry's **Learn** button within the learn window.

Remove the folder to uninstall.
