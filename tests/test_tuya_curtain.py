"""Offline checks for the Tuya-MOES / Kjell curtain-motor support (no hardware).

Run with the project's Home Assistant venv:
    python tests/test_tuya_curtain.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from custom_components.tellstick_local.const import (  # noqa: E402
    timings_to_tellstick_bytes,
)
from custom_components.tellstick_local.tuya_curtain import (  # noqa: E402
    BURST_FRAMES,
    BURST_GAP_MS,
    BUTTON_BYTES,
    DEFAULT_DEVICE_NAME,
    FRAME_VARIANTS,
    MAX_MARK_US,
    PREAMBLE_GAP_US,
    PREAMBLE_MARK_BURST_US,
    PREAMBLE_MARK_SOLO_US,
    REFERENCE_PAYLOADS,
    VENDOR_PREFIX,
    build_curtain_command,
    build_frame_timings,
    mint_identity,
    normalize_identity,
    normalize_payload,
    parse_base_code,
    payload_for_button,
    payload_to_bits,
    payloads_for_identity,
    split_long_mark,
    timings_for_button,
    timings_for_identity,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: object = "") -> None:
    if condition:
        print(f"PASS {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name} {detail!r}")


def check_raises(name: str, func) -> None:
    try:
        func()
    except ValueError:
        print(f"PASS {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name} (no ValueError)")


def main() -> int:
    check(
        "three reference payloads present",
        sorted(REFERENCE_PAYLOADS) == ["down", "stop", "up"],
        sorted(REFERENCE_PAYLOADS),
    )
    check("eight frame variants", sorted(FRAME_VARIANTS) == list("abcdefgh"), sorted(FRAME_VARIANTS))
    check(
        "button bytes are up/stop/down = ee/aa/cc",
        BUTTON_BYTES == {"up": "ee", "stop": "aa", "down": "cc"},
        BUTTON_BYTES,
    )

    for button, payload in REFERENCE_PAYLOADS.items():
        check(f"{button}: 40 bits", len(payload_to_bits(payload)) == 40)

    down_bits = payload_to_bits(REFERENCE_PAYLOADS["down"])
    up_bits = payload_to_bits(REFERENCE_PAYLOADS["up"])
    stop_bits = payload_to_bits(REFERENCE_PAYLOADS["stop"])
    check("shared 32-bit device prefix", down_bits[:32] == up_bits[:32] == stop_bits[:32])
    check(
        "payloads differ in the last byte",
        len({down_bits[32:], up_bits[32:], stop_bits[32:]}) == 3,
    )

    ones = {name: payload_to_bits(p).count("1") for name, p in REFERENCE_PAYLOADS.items()}
    check("up has two more 1-bits than down", ones["up"] - ones["down"] == 2, ones)
    check("stop has as many 1-bits as down", ones["stop"] == ones["down"], ones)

    # -- Identity handling (what makes this a self-learning device) -----------
    identity = mint_identity()
    check("minted identity is 8 hex chars", len(identity) == 8, identity)
    check(
        "minted identity keeps the vendor prefix",
        identity.startswith(VENDOR_PREFIX),
        identity,
    )
    check(
        "minted identity is valid hex",
        all(char in "0123456789abcdef" for char in identity),
        identity,
    )
    check("minted identities are distinct", len({mint_identity() for _ in range(64)}) > 55)

    check(
        "reference identity parses out of a captured code",
        parse_base_code("6C82050EEE") == "6c82050e",
        parse_base_code("6C82050EEE"),
    )
    check(
        "reference identity round-trips to the confirmed codes",
        payloads_for_identity("6c82050e") == REFERENCE_PAYLOADS,
        payloads_for_identity("6c82050e"),
    )
    minted = payloads_for_identity(identity)
    check(
        "each button reuses the identity and only swaps the button byte",
        {p[:8] for p in minted.values()} == {identity}
        and {p[8:] for p in minted.values()} == {"ee", "aa", "cc"},
        minted,
    )
    check("normalize_identity lower-cases and trims", normalize_identity("  6C82050E ") == "6c82050e")
    check_raises("short identity rejected", lambda: normalize_identity("6c8205"))
    check_raises("non-hex identity rejected", lambda: normalize_identity("6c82050z"))
    check_raises("empty base code rejected", lambda: parse_base_code("   "))
    check_raises("base code must be a full 40-bit code", lambda: parse_base_code("6c82050e"))

    default_name = DEFAULT_DEVICE_NAME
    check("default device name is set", isinstance(default_name, str) and default_name, default_name)

    # -- The 4.9 ms frame start must be split around the 2550 us tick limit ----
    check(
        "long mark split",
        split_long_mark(PREAMBLE_MARK_BURST_US) == [MAX_MARK_US, -10, 2340],
        split_long_mark(PREAMBLE_MARK_BURST_US),
    )
    check(
        "split preserves the total on-air width (marks plus the 10 us seam)",
        sum(abs(v) for v in split_long_mark(PREAMBLE_MARK_BURST_US))
        == PREAMBLE_MARK_BURST_US,
    )
    check(
        "short mark is not split",
        split_long_mark(PREAMBLE_MARK_SOLO_US) == [PREAMBLE_MARK_SOLO_US],
        split_long_mark(PREAMBLE_MARK_SOLO_US),
    )

    timings = build_frame_timings(REFERENCE_PAYLOADS["down"])
    check(
        "burst frame start 2550 + 10 + 2340 then sync gap",
        timings[:4] == [MAX_MARK_US, -10, 2340, -PREAMBLE_GAP_US],
        timings[:4],
    )
    check("timing count is frame start + 40 bit pairs", len(timings) == 84, len(timings))
    check("marks are positive", all(value > 0 for value in timings[0::2]))
    check("gaps are negative", all(value < 0 for value in timings[1::2]))

    solo_timings = build_frame_timings(REFERENCE_PAYLOADS["down"], "e")
    check(
        "variant e uses the 1.46 ms start mark",
        solo_timings[:2] == [PREAMBLE_MARK_SOLO_US, -PREAMBLE_GAP_US],
        solo_timings[:2],
    )
    check("variant e has 82 timings", len(solo_timings) == 82, len(solo_timings))

    reversed_bits = payload_to_bits(REFERENCE_PAYLOADS["down"])[::-1]
    table = {"1": (380, 744), "0": (776, 348)}
    expected_c = [*split_long_mark(PREAMBLE_MARK_BURST_US), -PREAMBLE_GAP_US]
    for bit in reversed_bits:
        mark, gap = table[bit]
        expected_c.extend((mark, -gap))
    check(
        "variant c reverses the 40 bits",
        build_frame_timings(REFERENCE_PAYLOADS["down"], "c") == expected_c,
    )

    ticks = timings_to_tellstick_bytes(timings)
    check("one tick byte per timing", len(ticks) == len(timings), len(ticks))
    check("ticks inside firmware range 1..255", all(1 <= byte <= 255 for byte in ticks))
    check("frame start ticks", tuple(ticks[:4]) == (255, 1, 234, 152), tuple(ticks[:4]))

    command = build_curtain_command(REFERENCE_PAYLOADS["down"])
    check("command starts with the 17 ms pause", command[:2] == b"P\x11", command[:2])
    check(
        "repeat byte is R5 (five-frame burst)",
        command[2:4] == bytes([ord("R"), BURST_FRAMES]),
        command[2:4],
    )
    check("default gap is 17 ms", BURST_GAP_MS == 17)
    check("data marker is S", command[4:5] == b"S", command[4:5])
    check("command ends with +", command[-1:] == b"+", command[-1:])
    check("command length is 4 + 1 + 84 + 1", len(command) == 90, len(command))

    solo_command = build_curtain_command(REFERENCE_PAYLOADS["down"], "e")
    check("variant e command length is 88", len(solo_command) == 88, len(solo_command))

    commands = {
        name: build_curtain_command(payload) for name, payload in REFERENCE_PAYLOADS.items()
    }
    check("three buttons give three distinct commands", len(set(commands.values())) == 3)
    check(
        "variant b differs from variant a",
        build_curtain_command(REFERENCE_PAYLOADS["up"], "b") != commands["up"],
    )
    check(
        "variant c differs from variant a",
        build_curtain_command(REFERENCE_PAYLOADS["up"], "c") != commands["up"],
    )
    check(
        "eight variants give eight distinct commands",
        len({build_curtain_command(REFERENCE_PAYLOADS["up"], v) for v in FRAME_VARIANTS}) == 8,
    )
    check(
        "repeat 0 clamps to 1",
        build_curtain_command(REFERENCE_PAYLOADS["up"], "a", 0)[3] == 1,
    )
    check(
        "repeat 255 is not clamped away",
        build_curtain_command(REFERENCE_PAYLOADS["up"], "a", 255)[3] == 255,
    )
    check(
        "pause 0 clamps to 1 ms (0 would truncate the IPC chain)",
        build_curtain_command(REFERENCE_PAYLOADS["up"], "a", 5, 0)[1] == 1,
    )
    check(
        "pause above 255 clamps to 255",
        build_curtain_command(REFERENCE_PAYLOADS["up"], "a", 5, 300)[1] == 255,
    )

    # -- What the Add-device flow stores --------------------------------------
    identity_timings = timings_for_identity(identity)
    check(
        "timings exist for all three buttons",
        sorted(identity_timings) == ["down", "stop", "up"],
        sorted(identity_timings),
    )
    check(
        "each stored timing is one 84-entry frame",
        all(len(value) == 84 for value in identity_timings.values()),
        {k: len(v) for k, v in identity_timings.items()},
    )
    check(
        "a minted remote gives three distinct button frames",
        len({tuple(v) for v in identity_timings.values()}) == 3,
    )
    check(
        "stored timings are the frames of the minted payloads",
        identity_timings["up"] == build_frame_timings(identity + "ee"),
    )
    check(
        "a different identity moves the frames",
        timings_for_identity("6c82050e")["up"] != identity_timings["up"],
    )
    check(
        "timing bytes stay inside the firmware range for a minted remote",
        all(
            1 <= byte <= 255
            for value in identity_timings.values()
            for byte in timings_to_tellstick_bytes(value)
        ),
    )
    check(
        "unknown variant rejected for a whole identity",
        _raises(lambda: timings_for_identity(identity, "z")),
    )

    # -- Reference-remote helpers (used by the debug services) ----------------
    check(
        "payload override wins over the button",
        payload_for_button("down", "6C82050EAA") == "6c82050eaa",
        payload_for_button("down", "6C82050EAA"),
    )
    check(
        "payload override replaces a wrong button label",
        build_curtain_command(payload_for_button("down", "6c82050eee"))
        == build_curtain_command(REFERENCE_PAYLOADS["up"]),
    )
    check(
        "normalize lower-cases and trims",
        normalize_payload("  6C82050EEE ") == "6c82050eee",
    )
    check_raises("payload override rejects short input", lambda: normalize_payload("6c82"))
    check_raises(
        "payload override rejects non-hex input",
        lambda: normalize_payload("6c82050ezz"),
    )

    check(
        "down is the code found on the bench",
        REFERENCE_PAYLOADS["down"] == "6c82050ecc",
        REFERENCE_PAYLOADS["down"],
    )
    check(
        "every confirmed code ends in a doubled nibble",
        all(p[-2] == p[-1] for p in REFERENCE_PAYLOADS.values()),
        REFERENCE_PAYLOADS,
    )
    check(
        "reference timings helper matches the identity helper",
        timings_for_button("up") == build_frame_timings(REFERENCE_PAYLOADS["up"]),
    )

    check_raises("short payload rejected", lambda: payload_to_bits("6c82"))
    check_raises(
        "unknown variant rejected",
        lambda: build_frame_timings(REFERENCE_PAYLOADS["up"], "z"),
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


def _raises(func) -> bool:
    """Return True if ``func`` raises ValueError (for inline checks)."""
    try:
        func()
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
