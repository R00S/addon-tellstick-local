"""Tuya-MOES / Kjell & Company curtain motor — self-learning 433 MHz cover.

These motors come with a three-button remote (up / stop / down) that no
TellStick can *receive*: the firmware only reports a packet once one of its
compiled protocol decoders accepts it, so an unknown 40-bit frame is dropped
with no event and no LED blink.  Transmission is a different matter —
``tdSendRawCommand`` accepts an arbitrary pulse train, so the motor can be
driven by replaying the frame format captured with RTL-SDR in issue #100.

Frame model, taken from the rtl_433 captures in issue #100 (2026-04-27):

    frame start  mark ~4900 us, sync gap 1524 us
    bit 1        short mark 380 us + long gap 744 us
    bit 0        long mark 776 us + short gap 348 us
    payload      40 bits, one frame ~47 ms
    press        5 identical frames, ~16.3-16.8 ms of silence between them

Two details from the captures decide whether a transmission can work at all:

* **The burst.** A press is five frames, not one: the log shows five
  ``{40}6c82050eaa`` frames per press with 16352 us gaps between them.  Sending
  one frame (or frames 2 ms apart) does not reproduce what the receiver expects,
  so :func:`build_curtain_command` defaults to ``P\\x11 R5`` — five frames with
  a 17 ms pause, which is the only place a gap that long fits (a timing byte
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

Payload layout (40 bits, one frame)::

    remote identity (4 bytes)     button (1 byte)
    6c 82 xx xx                   ee = up, aa = stop, cc = down

``6c82`` is the prefix every capture of this motor family shares; the last two
identity bytes are the remote's serial.  ``ee``/``aa``/``cc`` were each confirmed
on hardware (variant ``a``, five frames, 17 ms apart).

**These motors are self-learning.**  The receiver does not know or care which
identity it hears: in pairing mode it stores whatever 40-bit code arrives in a
proper burst.  That is what turns the issue #100 replay into a normal device —
the config flow mints a fresh identity per motor (:func:`mint_identity`), so
Home Assistant *is* the remote and no RTL-SDR is needed.  Pairing is the
procedure in the manual, with the app sending the up frame instead of a handset:
put the motor in pairing mode, then press Open on the new cover.

Users who do have an RTL-SDR can paste a code captured from their own remote
instead (:func:`parse_base_code`), which reuses that remote's identity — useful
when the handset must keep working and the motor only stores one remote.
"""
from __future__ import annotations

import secrets

from .const import generic_rf_build_raw_command

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

#: Identity prefix shared by every capture of this motor family (bytes 0-1).
VENDOR_PREFIX = "6c82"

#: Button -> last payload byte, each confirmed on hardware.
BUTTON_BYTES: dict[str, str] = {"up": "ee", "stop": "aa", "down": "cc"}

#: The issue #100 remote's own codes.  Not used by new devices — kept as a
#: known-good reference for the debug replay services and for the tests.
REFERENCE_PAYLOADS: dict[str, str] = {
    "up": "6c82050eee",
    "stop": "6c82050eaa",
    "down": "6c82050ecc",
}

#: Name the Add-device flow suggests.
DEFAULT_DEVICE_NAME = "Curtain motor"

#: The frame reading the device always transmits.  The flow used to offer all
#: eight variants because it was a bench experiment; a real motor answers one.
DEFAULT_VARIANT = "a"

#: Labels that put the motor in the ordinary "Add by brand" / "Add by protocol"
#: pickers.  It is not a telldusd protocol device, so it has no menu entry of
#: its own.
BRAND_CATALOG_LABEL = "Kjell & Company — Tuya curtain motor (self-learning, Duo only)"
PROTOCOL_CATALOG_LABEL = "generic_rf — Tuya curtain motor (self-learning, Duo only)"

#: Home Assistant services that transmit one frame / every variant (Duo only).
#: The names are historical (they shipped while this was a proof of concept)
#: and are kept so existing automations keep working.
SERVICE_POC_SEND_BLIND = "poc_send_blind"
SERVICE_POC_SWEEP_BLIND = "poc_sweep_blind"


def payload_to_bits(hex_payload: str) -> str:
    """Expand a 40-bit payload to transmitted bits (first transmitted bit first)."""
    cleaned = hex_payload.strip().lower()
    if len(cleaned) != 10 or any(char not in "0123456789abcdef" for char in cleaned):
        raise ValueError(
            f"expected 10 hex characters (40 bits), got {hex_payload!r}"
        )
    return "".join(f"{int(char, 16):04b}" for char in cleaned)


def normalize_payload(hex_payload: str) -> str:
    """Validate and lower-case a 40-bit payload for transmission.

    Raises:
        ValueError: if the string is not exactly 10 hex characters.
    """
    cleaned = hex_payload.strip().lower()
    payload_to_bits(cleaned)  # raises with a clear message
    return cleaned


def normalize_identity(identity: str) -> str:
    """Validate and lower-case a 32-bit remote identity (8 hex characters).

    Raises:
        ValueError: if the string is not exactly 8 hex characters.
    """
    cleaned = identity.strip().lower()
    if len(cleaned) != 8 or any(char not in "0123456789abcdef" for char in cleaned):
        raise ValueError(
            f"expected 8 hex characters (32-bit remote identity), got {identity!r}"
        )
    return cleaned


def mint_identity() -> str:
    """Return a fresh 32-bit remote identity for a new motor.

    ``6c82`` is kept because every captured code of this family starts with it;
    the serial bytes are random, which gives 65536 distinct remotes.  Two motors
    in the same home can therefore be independent, and the identity never
    collides with the issue #100 handset.
    """
    return VENDOR_PREFIX + secrets.token_hex(2)


def parse_base_code(code: str) -> str:
    """Return the 32-bit identity from a captured 40-bit payload.

    Users with an RTL-SDR can copy any of the three codes their own remote
    sends; only the first eight hex characters (the identity) are used, because
    the button byte is always taken from :data:`BUTTON_BYTES`.

    Raises:
        ValueError: if the string is not exactly 10 hex characters.
    """
    if not code or not code.strip():
        raise ValueError("expected a captured 40-bit code, got an empty value")
    return normalize_payload(code)[:8]


def payloads_for_identity(identity: str) -> dict[str, str]:
    """Return ``{button: 40-bit payload}`` for a remote identity.

    Raises:
        ValueError: if the identity is not exactly 8 hex characters.
    """
    cleaned = normalize_identity(identity)
    return {
        button: cleaned + button_byte
        for button, button_byte in BUTTON_BYTES.items()
    }


def payload_for_button(button: str, payload: str | None = None) -> str:
    """Return a payload for a button of the issue #100 remote, or an override.

    Used by the debug replay services; devices store their own timings, so this
    is not on the device path.  The override transmits an arbitrary code without
    re-labelling anything.

    Raises:
        ValueError: if the button is unknown or the override is not 10 hex chars.
    """
    if payload:
        return normalize_payload(payload)
    try:
        return REFERENCE_PAYLOADS[button.lower()]
    except KeyError as err:
        raise ValueError(
            f"unknown button {button!r}; expected one of {sorted(REFERENCE_PAYLOADS)}"
        ) from err


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


def timings_for_identity(identity: str, variant: str = "a") -> dict[str, list[int]]:
    """Return ``{button: timings}`` for a whole remote identity.

    This is what the Add-device flow stores on the device, so the cover entity
    never needs to encode anything at runtime.

    Raises:
        ValueError: if the identity is invalid or the variant is unknown.
    """
    return {
        button: build_frame_timings(payload, variant)
        for button, payload in payloads_for_identity(identity).items()
    }


def timings_for_button(button: str, variant: str = "a") -> list[int]:
    """Return the pulse/space timings for one button of the reference remote.

    Raises:
        ValueError: if the button or the variant is unknown.
    """
    return build_frame_timings(payload_for_button(button), variant)


def build_curtain_command(
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
