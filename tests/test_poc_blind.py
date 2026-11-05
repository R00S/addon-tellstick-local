"""Offline checks for the issue #100 blind replay PoC (no hardware needed).

Run with the project's Home Assistant venv:
    python tests/test_poc_blind.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from custom_components.tellstick_local.const import (  # noqa: E402
    timings_to_tellstick_bytes,
)
from custom_components.tellstick_local.poc_blind import (  # noqa: E402
    BURST_FRAMES,
    BURST_GAP_MS,
    FRAME_VARIANTS,
    MAX_MARK_US,
    POC_BLIND_PAYLOADS,
    PREAMBLE_GAP_US,
    PREAMBLE_MARK_BURST_US,
    PREAMBLE_MARK_SOLO_US,
    build_frame_timings,
    build_poc_command,
    normalize_payload,
    payload_for_button,
    payload_to_bits,
    split_long_mark,
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
        "three payloads present",
        sorted(POC_BLIND_PAYLOADS) == ["down", "stop", "up"],
        sorted(POC_BLIND_PAYLOADS),
    )
    check("eight frame variants", sorted(FRAME_VARIANTS) == list("abcdefgh"), sorted(FRAME_VARIANTS))

    for button, payload in POC_BLIND_PAYLOADS.items():
        check(f"{button}: 40 bits", len(payload_to_bits(payload)) == 40)

    down_bits = payload_to_bits(POC_BLIND_PAYLOADS["down"])
    up_bits = payload_to_bits(POC_BLIND_PAYLOADS["up"])
    stop_bits = payload_to_bits(POC_BLIND_PAYLOADS["stop"])
    check("shared 32-bit device prefix", down_bits[:32] == up_bits[:32] == stop_bits[:32])
    check(
        "payloads differ in the last byte",
        len({down_bits[32:], up_bits[32:], stop_bits[32:]}) == 3,
    )

    ones = {name: payload_to_bits(p).count("1") for name, p in POC_BLIND_PAYLOADS.items()}
    check("up has two more 1-bits than down", ones["up"] - ones["down"] == 2, ones)
    check("stop has as many 1-bits as down", ones["stop"] == ones["down"], ones)

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

    timings = build_frame_timings(POC_BLIND_PAYLOADS["down"])
    check(
        "burst frame start 2550 + 10 + 2340 then sync gap",
        timings[:4] == [MAX_MARK_US, -10, 2340, -PREAMBLE_GAP_US],
        timings[:4],
    )
    check("timing count is frame start + 40 bit pairs", len(timings) == 84, len(timings))
    check("marks are positive", all(value > 0 for value in timings[0::2]))
    check("gaps are negative", all(value < 0 for value in timings[1::2]))

    solo_timings = build_frame_timings(POC_BLIND_PAYLOADS["down"], "e")
    check(
        "variant e uses the 1.46 ms start mark",
        solo_timings[:2] == [PREAMBLE_MARK_SOLO_US, -PREAMBLE_GAP_US],
        solo_timings[:2],
    )
    check("variant e has 82 timings", len(solo_timings) == 82, len(solo_timings))

    reversed_bits = payload_to_bits(POC_BLIND_PAYLOADS["down"])[::-1]
    table = {"1": (380, 744), "0": (776, 348)}
    expected_c = [*split_long_mark(PREAMBLE_MARK_BURST_US), -PREAMBLE_GAP_US]
    for bit in reversed_bits:
        mark, gap = table[bit]
        expected_c.extend((mark, -gap))
    check(
        "variant c reverses the 40 bits",
        build_frame_timings(POC_BLIND_PAYLOADS["down"], "c") == expected_c,
    )

    ticks = timings_to_tellstick_bytes(timings)
    check("one tick byte per timing", len(ticks) == len(timings), len(ticks))
    check("ticks inside firmware range 1..255", all(1 <= byte <= 255 for byte in ticks))
    check("frame start ticks", tuple(ticks[:4]) == (255, 1, 234, 152), tuple(ticks[:4]))

    command = build_poc_command(POC_BLIND_PAYLOADS["down"])
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

    solo_command = build_poc_command(POC_BLIND_PAYLOADS["down"], "e")
    check("variant e command length is 88", len(solo_command) == 88, len(solo_command))

    commands = {
        name: build_poc_command(payload) for name, payload in POC_BLIND_PAYLOADS.items()
    }
    check("three buttons give three distinct commands", len(set(commands.values())) == 3)
    check(
        "variant b differs from variant a",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "b") != commands["up"],
    )
    check(
        "variant c differs from variant a",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "c") != commands["up"],
    )
    check(
        "eight variants give eight distinct commands",
        len({build_poc_command(POC_BLIND_PAYLOADS["up"], v) for v in FRAME_VARIANTS}) == 8,
    )
    check(
        "repeat 0 clamps to 1",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "a", 0)[3] == 1,
    )
    check(
        "repeat 255 is not clamped away",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "a", 255)[3] == 255,
    )
    check(
        "pause 0 clamps to 1 ms (0 would truncate the IPC chain)",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "a", 5, 0)[1] == 1,
    )
    check(
        "pause above 255 clamps to 255",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "a", 5, 300)[1] == 255,
    )

    check(
        "payload override wins over the button",
        payload_for_button("down", "6C82050EAA") == "6c82050eaa",
        payload_for_button("down", "6C82050EAA"),
    )
    check(
        "payload override replaces a wrong button label",
        build_poc_command(payload_for_button("down", "6c82050ee1"))
        == build_poc_command(POC_BLIND_PAYLOADS["stop"]),
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

    check_raises("short payload rejected", lambda: payload_to_bits("6c82"))
    check_raises(
        "unknown variant rejected",
        lambda: build_frame_timings(POC_BLIND_PAYLOADS["up"], "z"),
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
