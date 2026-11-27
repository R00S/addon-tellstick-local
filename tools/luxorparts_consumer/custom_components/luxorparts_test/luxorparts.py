"""Luxorparts 433 MHz protocol — timings only, no Home Assistant.

A Luxorparts socket (50969/50970/50972) listens for a 25-bit OOK-PWM packet:
one start bit followed by 24 encrypted payload bits.  Every bit is a pulse
followed by a gap, and the pairing is constant-period, so the two symbols
differ only in *where* the edge falls:

    bit 1 -> short pulse (390 us) + long gap  (1110 us)
    bit 0 -> long  pulse (1150 us) + short gap (350 us)

The payload is 3 bytes (address high, address low, count/state/unit) run
through the receiver's nibble-substitution cipher, which is the only part a
receiver checks to tell ON from OFF.

This module is pure Python on purpose: the timings are what the
radio_frequency API wants, and the socket is what decides whether they work.
"""

from __future__ import annotations

TICK_US = 10

PULSE_SHORT_US = 39 * TICK_US   # 390 us
PULSE_LONG_US = 115 * TICK_US   # 1150 us
GAP_SHORT_US = 35 * TICK_US     # 350 us
GAP_LONG_US = 111 * TICK_US     # 1110 us

# Silence after each packet, in us.  A real remote leaves about 2250 us.
# The TellStick Duo adds its own ~2 ms pause before every repeat, so 250 us
# here reproduces the exact bytes that are proven to work on hardware
# (250 + 2000 = 2250 us).  Set INTER_PACKET_US = 2250 for a provider that
# does not add a pause of its own.
INTER_PACKET_US = 250
NATURAL_INTER_PACKET_US = 2250

FREQUENCY_HZ = 433_920_000
BIT_COUNT = 25
REPEATS = 10
LEARN_REPEATS = 48

_LX_ENC_TABLE = (
    (10, 0, 4, 12, 2, 14, 7, 5, 1, 15, 11, 13, 9, 6, 3, 8),
    (2, 12, 5, 14, 7, 4, 1, 15, 11, 13, 6, 3, 8, 9, 10, 0),
)

def _lx_encrypt_payload(payload: tuple[int, int, int]) -> int:
    """Encrypt a 3-byte Luxorparts plaintext → 24-bit ciphertext integer.

    Implements the nibble substitution + XOR chain cipher from the Homey
    Luxorparts app (``lib/PayloadEncryption.js``).
    """
    table = _LX_ENC_TABLE[(payload[0] >> 5) & 1]
    nibbles = []
    for byte_val in payload:
        nibbles.append((byte_val >> 4) & 0xF)
        nibbles.append(byte_val & 0xF)

    # Encrypt: start from nibble 5 (LSB), chain XOR backwards
    enc = [0] * 6
    enc[0] = table[nibbles[5]]
    xor_count = 0
    for i in range(4, 0, -1):
        enc[4 - i + 1] = table[(nibbles[i] ^ enc[xor_count]) & 0xF]
        xor_count += 1
    enc[5] = nibbles[0] ^ 9
    # Reverse — last added nibble is actually the MSB
    enc.reverse()

    return (enc[0] << 20) | (enc[1] << 16) | (enc[2] << 12) | (enc[3] << 8) | (enc[4] << 4) | enc[5]

def codes(house: int, unit: int) -> dict[str, int]:
    """Return the ON and OFF code for a (house, unit) pair.

    ``house`` is the 16-bit address, ``unit`` maps to the low 5 bits of the
    third payload byte, and ``count`` is fixed at 1 — the value Telldus Live
    sends.  The result keeps the 25-bit code left-aligned in 32 bits, which is
    what ``timings()`` consumes.
    """
    address = int(house) & 0xFFFF
    proto_unit = max(0, int(unit) - 1) & 0x1F

    def payload(state: int) -> tuple[int, int, int]:
        return (
            address >> 8,
            address & 0xFF,
            (1 << 6) | (state << 5) | proto_unit,
        )

    return {
        "off": _lx_encrypt_payload(payload(0)) << 3,
        "on": _lx_encrypt_payload(payload(1)) << 3,
    }


def timings(code: int, inter_packet_us: int = INTER_PACKET_US) -> list[int]:
    """Turn a 28-bit code into signed microseconds, pulse first.

    Negative values are gaps.  The packet's own trailing gap is replaced by
    ``inter_packet_us``, which is the silence a receiver needs before it will
    accept the next packet.
    """
    packet: list[int] = []
    for bit in range(BIT_COUNT - 1, -1, -1):
        if (code >> 3) >> bit & 1:
            packet += [PULSE_SHORT_US, -GAP_LONG_US]
        else:
            packet += [PULSE_LONG_US, -GAP_SHORT_US]
    packet[-1] = -inter_packet_us
    return packet
