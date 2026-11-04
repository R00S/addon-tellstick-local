"""Proof of concept: replay the issue #100 curtain-remote frames on a Duo.

Neither a TellStick Duo nor a Net/ZNet can *receive* this remote: the firmware
only reports a packet once one of its compiled protocol decoders accepts it, so
an unknown 40-bit frame is dropped with no event and no LED blink.  Transmission
is a different matter — ``tdSendRawCommand`` accepts an arbitrary pulse train,
so the frames captured with RTL-SDR can be replayed to move the blind.

Frame model, taken from the rtl_433 captures in issue #100 (2026-04-27):

    frame start  mark ~4900 us, sync gap 1524 us
    bit 1        short mark 380 us + long gap 744 us
    bit 0        long mark 776 us + short gap 348 us
    payload      40 bits, one frame ~47 ms
    press        5 identical frames, ~16.3-16.8 ms of silence between them

Two details from the captures decide whether a replay can work at all:

* **The burst.** A press is five frames, not one: the log shows five
  ``{40}6c82050eaa`` frames per press with 16352 us gaps between them.  Sending
  one frame (or frames 2 ms apart) does not reproduce what the receiver expects,
  so :func:`build_poc_command` defaults to ``P\\x11 R5`` — five frames with a
  17 ms pause, which is the only place a gap that long fits (a timing byte
  saturates at 255 ticks = 2550 us).
* **The frame-start mark.** Frames decoded on their own report a 1460 us start
  mark, frames inside a burst report 4876 us.  The short value is the same pulse
  clipped by the recorder, so the burst form (4900 us) is the faithful one; it
  exceeds the 2550 us tick limit and is therefore emitted as 2550 + 10 + 2340 —
  the 10 us seam is far below the receiver's slicer resolution.

The bit polarity is not taken on faith.  Comparing two captures: ``...ee`` holds
two more 1-bits than ``...aa``, and its frame shows exactly two more short marks
and two more long gaps — consistent only with 1 = short mark + long gap.  Bit
*order* cannot be read off the pulse counts, so variants ``c``/``d`` reverse the
40 bits, and ``e``-``h`` repeat the same four readings with the clipped 1460 us
start mark, in case the short value was real after all.

Payloads (last byte = button): aa = down, ee = up, e1 = stop.  The labels in the
issue contradict each other ("stop" repeats the first capture's payload), so the
mapping is probable, not proven.

Deliberately standalone and disposable — delete this module once real cover
support for these motors lands.
"""
from __future__ import annotations

from .const import generic_rf_build_raw_command

#: Button name -> 40-bit payload captured with rtl_433.
POC_BLIND_PAYLOADS: dict[str, str] = {
    "down": "6c82050eaa",
    "up": "6c82050eee",
    "stop": "6c82050ee1",
}

#: Home Assistant service that transmits one frame variant (Duo only).
SERVICE_POC_SEND_BLIND = "poc_send_blind"

#: Home Assistant service that walks every frame variant in one go (Duo only).
SERVICE_POC_SWEEP_BLIND = "poc_sweep_blind"

#: Label shown in the integration's "Add device" menu.
POC_DEVICE_LABEL = "Kjell & Co / Tuya curtain motor (issue #100, test device)"

#: One firmware tick is ~10 us, and a timing byte saturates at 255 ticks.
TICK_US = 10
MAX_MARK_US = 255 * TICK_US

#: Frame start marks: burst form from the multi-frame capture, and the 1460 us
#: value reported for frames decoded in isolation (a clipped burst edge).
PREAMBLE_MARK_BURST_US = 4900
PREAMBLE_MARK_SOLO_US = 1460
PREAMBLE_GAP_US = 1524

#: A real button press is five identical frames ~16-17 ms apart.
BURST_FRAMES = 5
BURST_GAP_MS = 17

#: Bit polarity tables: bit -> (mark us, gap us).
BIT_POLARITY: dict[str, dict[str, tuple[int, int]]] = {
    "short1": {"1": (380, 744), "0": (776, 348)},
    "short0": {"1": (776, 348), "0": (380, 744)},
}

#: variant -> (bit polarity, reverse the 40 bits, frame-start mark us).
FRAME_VARIANTS: dict[str, tuple[str, bool, int]] = {
    "a": ("short1", False, PREAMBLE_MARK_BURST_US),
    "b": ("short0", False, PREAMBLE_MARK_BURST_US),
    "c": ("short1", True, PREAMBLE_MARK_BURST_US),
    "d": ("short0", True, PREAMBLE_MARK_BURST_US),
    "e": ("short1", False, PREAMBLE_MARK_SOLO_US),
    "f": ("short0", False, PREAMBLE_MARK_SOLO_US),
    "g": ("short1", True, PREAMBLE_MARK_SOLO_US),
    "h": ("short0", True, PREAMBLE_MARK_SOLO_US),
}


def payload_to_bits(hex_payload: str) -> str:
    """Expand a 40-bit payload to transmitted bits (first transmitted bit first)."""
    cleaned = hex_payload.strip().lower()
    if len(cleaned) != 10 or any(char not in "0123456789abcdef" for char in cleaned):
        raise ValueError(
            f"expected 10 hex characters (40 bits), got {hex_payload!r}"
        )
    return "".join(f"{int(char, 16):04b}" for char in cleaned)


def split_long_mark(mark_us: int) -> list[int]:
    """Split a mark that exceeds the firmware's 2550 us tick limit.

    A timing byte is one 10 us tick and saturates at 255 ticks, so a 4900 us
    frame-start mark is sent as ``2550 on, 10 off, 2340 on``.  A 10 us notch is
    far below the bandwidth of any 433 MHz OOK receiver, so it reads as one
    continuous mark.
    """
    out: list[int] = []
    remaining = int(mark_us)
    while remaining > MAX_MARK_US:
        out.extend((MAX_MARK_US, -TICK_US))
        remaining -= MAX_MARK_US + TICK_US
    out.append(max(remaining, TICK_US))
    return out


def build_frame_timings(hex_payload: str, variant: str = "a") -> list[int]:
    """Return alternating pulse/space timings in us for a single frame."""
    try:
        polarity, reverse_bits, preamble_mark = FRAME_VARIANTS[variant.lower()]
    except KeyError as err:
        raise ValueError(
            f"unknown variant {variant!r}; expected one of {sorted(FRAME_VARIANTS)}"
        ) from err

    bits = payload_to_bits(hex_payload)
    if reverse_bits:
        bits = bits[::-1]

    table = BIT_POLARITY[polarity]
    timings = split_long_mark(preamble_mark)
    timings.append(-PREAMBLE_GAP_US)
    for bit in bits:
        mark, gap = table[bit]
        timings.extend((mark, -gap))
    return timings


def timings_for_button(button: str, variant: str = "a") -> list[int]:
    """Return the pulse/space timings for one captured button.

    Args:
        button: ``down``, ``up`` or ``stop``.
        variant: frame variant, one of :data:`FRAME_VARIANTS`.

    Raises:
        ValueError: if the button or the variant is unknown.
    """
    try:
        payload = POC_BLIND_PAYLOADS[button.lower()]
    except KeyError as err:
        raise ValueError(
            f"unknown button {button!r}; expected one of {sorted(POC_BLIND_PAYLOADS)}"
        ) from err
    return build_frame_timings(payload, variant)


def build_poc_command(
    hex_payload: str,
    variant: str = "a",
    repeat_count: int = BURST_FRAMES,
    pause_ms: int = BURST_GAP_MS,
) -> bytes:
    """Build the ``P<ms> R<n> S<ticks>+`` command for one frame.

    The firmware repeats the frame ``R`` times and inserts a ``P`` millisecond
    pause between repeats — that pause is what reproduces the ~16-17 ms silence
    the captures show between the five frames of a real button press.
    """
    return generic_rf_build_raw_command(
        build_frame_timings(hex_payload, variant), repeat_count, pause_ms
    )
