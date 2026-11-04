"""Proof of concept: replay the issue #100 curtain-remote frames on a Duo.

Neither a TellStick Duo nor a Net/ZNet can *receive* this remote: the firmware
only reports a packet once one of its compiled protocol decoders accepts it, so
an unknown 40-bit frame is dropped with no event and no LED blink.  Transmission
is a different matter — ``tdSendRawCommand`` accepts an arbitrary pulse train,
so the frames captured with RTL-SDR can be replayed to move the blind.

Frame model, taken from the rtl_433 captures in issue #100 (2026-04-27):

    preamble    mark 1460 us, sync gap 1524 us
    bit 1       short mark 380 us + long gap 744 us
    bit 0       long mark 776 us + short gap 348 us
    payload     40 bits, one frame ~47 ms, ~5 frames per button press

The bit polarity is not taken on faith.  Comparing two captures: ``…ee`` holds
two more 1-bits than ``…aa``, and its frame shows exactly two more short marks
and two more long gaps — consistent only with 1 = short mark + long gap.  The
other variants are kept because a replay attempt is how this gets confirmed on
real hardware: if the blind ignores variant "a", try "b"–"d" before drawing any
conclusion about the payloads themselves.

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

#: Home Assistant service that transmits one captured frame (Duo only).
SERVICE_POC_SEND_BLIND = "poc_send_blind"

#: Label shown in the integration's "Add device" menu.
POC_DEVICE_LABEL = "Kjell & Co / Tuya curtain motor (issue #100, test device)"

PREAMBLE_MARK_US = 1460
PREAMBLE_GAP_US = 1524

#: bit -> (mark us, gap us).  Variant "a" is the one derived from the captures.
BIT_VARIANTS: dict[str, dict[str, tuple[int, int]]] = {
    "a": {"1": (380, 744), "0": (776, 348)},
    "b": {"1": (776, 348), "0": (380, 744)},
    "c": {"1": (380, 348), "0": (776, 744)},
    "d": {"1": (776, 744), "0": (380, 348)},
}


def payload_to_bits(hex_payload: str) -> str:
    """Expand a 40-bit payload to transmitted bits (first transmitted bit first)."""
    cleaned = hex_payload.strip().lower()
    if len(cleaned) != 10 or any(char not in "0123456789abcdef" for char in cleaned):
        raise ValueError(
            f"expected 10 hex characters (40 bits), got {hex_payload!r}"
        )
    return "".join(f"{int(char, 16):04b}" for char in cleaned)


def build_frame_timings(hex_payload: str, variant: str = "a") -> list[int]:
    """Return alternating pulse/space timings in us for a single frame."""
    try:
        bits_to_timing = BIT_VARIANTS[variant.lower()]
    except KeyError as err:
        raise ValueError(
            f"unknown variant {variant!r}; expected one of {sorted(BIT_VARIANTS)}"
        ) from err

    timings = [PREAMBLE_MARK_US, -PREAMBLE_GAP_US]
    for bit in payload_to_bits(hex_payload):
        mark, gap = bits_to_timing[bit]
        timings.extend((mark, -gap))
    return timings


def timings_for_button(button: str, variant: str = "a") -> list[int]:
    """Return the pulse/space timings for one captured button.

    Args:
        button: ``down``, ``up`` or ``stop``.
        variant: bit-polarity variant, one of :data:`BIT_VARIANTS`.

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
    hex_payload: str, variant: str = "a", repeat_count: int = 10
) -> bytes:
    """Build the ``P\\x02 R<n> S<ticks>+`` command for one frame.

    One frame per transmission, repeated by the firmware's ``R`` counter.  The
    ~16 ms gap between frames in a real button press cannot be expressed at all
    (the tick field saturates at 255 = 2550 us), which is why a five-frame
    capture must not be replayed verbatim.
    """
    return generic_rf_build_raw_command(
        build_frame_timings(hex_payload, variant), repeat_count
    )
