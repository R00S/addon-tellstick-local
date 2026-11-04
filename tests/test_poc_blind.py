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
    POC_BLIND_PAYLOADS,
    PREAMBLE_GAP_US,
    PREAMBLE_MARK_US,
    build_frame_timings,
    build_poc_command,
    payload_to_bits,
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

    timings = build_frame_timings(POC_BLIND_PAYLOADS["down"])
    check("preamble mark", timings[0] == PREAMBLE_MARK_US, timings[0])
    check("preamble gap", timings[1] == -PREAMBLE_GAP_US, timings[1])
    check("timing count is preamble + 40 bit pairs", len(timings) == 2 + 2 * 40, len(timings))
    check("marks are positive", all(value > 0 for value in timings[0::2]))
    check("gaps are negative", all(value < 0 for value in timings[1::2]))

    ticks = timings_to_tellstick_bytes(timings)
    check("one tick byte per timing", len(ticks) == len(timings), len(ticks))
    check("ticks inside firmware range 1..255", all(1 <= byte <= 255 for byte in ticks))
    check("preamble ticks", (ticks[0], ticks[1]) == (146, 152), (ticks[0], ticks[1]))

    command = build_poc_command(POC_BLIND_PAYLOADS["down"])
    check("command starts with P pause", command[:2] == b"P\x02", command[:2])
    check("repeat byte is R10", command[2:4] == bytes([ord("R"), 10]), command[2:4])
    check("data marker is S", command[4:5] == b"S", command[4:5])
    check("command ends with +", command[-1:] == b"+", command[-1:])
    check("command length is 4 + 1 + 82 + 1", len(command) == 88, len(command))

    commands = {
        name: build_poc_command(payload) for name, payload in POC_BLIND_PAYLOADS.items()
    }
    check("three buttons give three distinct commands", len(set(commands.values())) == 3)
    check(
        "variant b differs from variant a",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "b") != commands["up"],
    )
    check(
        "repeat 0 clamps to 1",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "a", 0)[3] == 1,
    )
    check(
        "repeat 255 is not clamped away",
        build_poc_command(POC_BLIND_PAYLOADS["up"], "a", 255)[3] == 255,
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
