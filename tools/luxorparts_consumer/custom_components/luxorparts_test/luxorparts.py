"""Luxorparts 433 MHz protocol — the 24 verified code pairs.

Every one of these pairs was captured from Telldus Live with an RTL-SDR and
confirmed at a receiver, so they are the codes the sockets actually obey.
No generated or cipher-derived code is used here: the Homey cipher has never
made a socket respond, so it is not part of this integration.

A packet is 25 bits of OOK-PWM: one start bit followed by 24 payload bits.
Each bit is a pulse and a gap, and the pair is constant-period, so the two
symbols differ only in where the edge falls:

    bit 1 -> short pulse (390 us) + long gap  (1110 us)
    bit 0 -> long  pulse (1150 us) + short gap (350 us)

The payload is the receiver's address, channel and on/off state, already
encrypted as the receiver expects — which is exactly why a recorded pair
works and a re-derived one does not.
"""

from __future__ import annotations

TICK_US = 10

PULSE_SHORT_US = 39 * TICK_US   # 390 us
PULSE_LONG_US = 115 * TICK_US   # 1150 us
GAP_SHORT_US = 35 * TICK_US     # 350 us
GAP_LONG_US = 111 * TICK_US     # 1110 us

# Silence after each packet, in us.  A real remote leaves about 2250 us.
# The TellStick Duo adds its own ~2 ms pause before every repeat, so 250 us
# here reproduces the exact bytes proven on hardware (250 + 2000 = 2250 us).
#
# Anything longer breaks reception on a Luxorparts receiver, so this cannot be
# used to force the provider's split path — see the hardware note in
# docs/main-3.4.2.x.md.  6000 us and 2600 us were both tried and both failed.
INTER_PACKET_US = 250
NATURAL_INTER_PACKET_US = 2250

FREQUENCY_HZ = 433_920_000
BIT_COUNT = 25
REPEATS = 10
LEARN_REPEATS = 48

#: The 24 recorded pairs: (number, ON code, OFF code, where it was recorded).
#: The number is the receiver's recorded address — "LPD 11" is house 11, unit 1
#: in a TellStick device config.  Codes are 28-bit integers; the real 25-bit
#: code occupies the top 25 bits, which ``timings()`` shifts for.
VERIFIED_PAIRS: tuple[tuple[int, int, int, str], ...] = (
    (1, 0x5E14538, 0x5A59738, "H14466/U1"),
    (2, 0x559DBA8, 0x5CCC0A8, "H14468/U2"),
    (3, 0x5BD4B88, 0x51B1088, "H14268/U4"),
    (4, 0x340EBF8, 0x39785F8, "H21900/U1"),
    (5, 0x6BD1C38, 0x6DB7638, "H166/U3"),
    (6, 0x32128B8, 0x3E2CDB8, "H2190/U2"),
    (7, 0x2450C38, 0x2633638, "H16634/U3"),
    (8, 0x3757C38, 0x3B81638, "H21900/U3"),
    (9, 0x39785D8, 0x340EBD8, "H21900/U4"),
    (10, 0x3B81618, 0x3757C18, "H21900/U5"),
    (11, 0x35A0BF8, 0x339A5F8, "H21901/U1"),
    (12, 0x3034BF8, 0x3C4D5F8, "H29102/U1"),
    (13, 0x53F5EB8, 0x5C548B8, "H12639/U5"),
    (14, 0x57231E8, 0x5AC13E8, "H12639/U6"),
    (15, 0x5E8E608, 0x5BBFF08, "H12639/U7"),
    (16, 0x51DA248, 0x5467C48, "H12639/U8"),
    (17, 0x5BBFF28, 0x5E8E628, "H12639/U9"),
    (18, 0x5C54898, 0x53F5E98, "H12639/U10"),
    (19, 0x5AC13C8, 0x57231C8, "H12639/U11"),
    (20, 0x23CEC38, 0x292B638, "unknown"),
    (21, 0x21A7C38, 0x25F1638, "unknown"),
    (22, 0x206CC38, 0x289D638, "unknown"),
    (23, 0x2709C38, 0x224A638, "unknown"),
    (24, 0x2A86C38, 0x2FE8638, "maybe H12639/U4"),
)

#: The pairs, keyed by number, in the shape the entities want.
CODES: dict[int, dict[str, int]] = {
    number: {"on": on, "off": off}
    for number, on, off, _where in VERIFIED_PAIRS
}

#: Human-readable label per number, for the picker.
LABELS: dict[int, str] = {
    number: f"LPD {number} · recorded {where}"
    for number, _on, _off, where in VERIFIED_PAIRS
}


def codes(number: int) -> dict[str, int]:
    """Return the verified ON/OFF pair for one recorded device number."""
    try:
        return dict(CODES[int(number)])
    except (KeyError, TypeError, ValueError) as err:
        raise ValueError(f"no verified Luxorparts pair {number}") from err


def timings(code: int, inter_packet_us: int = INTER_PACKET_US) -> list[int]:
    """Turn a 28-bit code into signed microseconds, pulse first.

    Negative values are gaps.  The packet's own trailing gap is replaced by
    ``inter_packet_us``, the silence a receiver needs before the next packet.
    Keep it at the default: a longer silence stops the receiver responding.
    """
    packet: list[int] = []
    for bit in range(BIT_COUNT - 1, -1, -1):
        if (code >> 3) >> bit & 1:
            packet += [PULSE_SHORT_US, -GAP_LONG_US]
        else:
            packet += [PULSE_LONG_US, -GAP_SHORT_US]
    packet[-1] = -inter_packet_us
    return packet
