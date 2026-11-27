"""Offline checks for the radio_frequency transmitter helpers (no hardware).

Covers the µs → firmware-tick conversion, the splitting of durations that do
not fit a single timing byte, repeat handling and the TellStick Net v1 payload
limit.  The entity itself is not exercised (that needs a Home Assistant
instance, see ``tests/test_ha_integration.py``).

Run with:
    python tests/test_radio_frequency.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:  # normal package import, as used in the project's HA venv / CI
    from custom_components.tellstick_local.const import (  # noqa: E402
        NET_V1_MAX_PULSES,
        timings_to_raw_frame,
    )
except ModuleNotFoundError:
    # ``const`` itself only needs the standard library, but importing it as a
    # package submodule runs ``__init__.py``, which needs Home Assistant.  Load
    # the file directly so the conversion helpers can be tested on their own.
    import importlib.util

    _CONST_PATH = (
        pathlib.Path(__file__).resolve().parents[1]
        / "custom_components"
        / "tellstick_local"
        / "const.py"
    )
    _SPEC = importlib.util.spec_from_file_location("tellstick_const", _CONST_PATH)
    assert _SPEC is not None and _SPEC.loader is not None
    _CONST = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(_CONST)
    NET_V1_MAX_PULSES = _CONST.NET_V1_MAX_PULSES
    timings_to_raw_frame = _CONST.timings_to_raw_frame


def _payload(frame: bytes) -> bytes:
    """Return the S payload of a ``P/R/S`` frame."""
    assert frame[:1] == b"P", f"frame does not start with P: {frame[:4]!r}"
    start = frame.index(b"S") + 1
    assert frame[-1:] == b"+", f"frame does not end with +: {frame[-4:]!r}"
    return frame[start:-1]


def _ticks(timings: list[int], **kwargs) -> list[int]:
    return list(_payload(timings_to_raw_frame(timings, **kwargs)))


def test_quantisation() -> None:
    """Short durations map to 10 µs ticks, rounded."""
    assert _ticks([240]) == [24]
    assert _ticks([1270]) == [127]
    # 275 µs is 27.5 ticks → 28 (2750 µs/10 = 275; the encoder rounds up)
    assert _ticks([275]) == [28]
    assert _ticks([604]) == [60]
    # Never zero: a single 0 byte would end the payload.
    assert _ticks([1]) == [1]


def test_long_mark_is_split() -> None:
    """A ~4.9 ms mark becomes 2550 + 10 + rest, as already proven on hardware."""
    assert _ticks([4900]) == [255, 1, 235]
    # Alternation is preserved by position, so the split element stays one
    # continuous "pulse" from the receiver's point of view.
    assert _ticks([4900, -100]) == [255, 1, 235, 10]


def test_long_gap_is_split() -> None:
    """Spaces are split the same way, with the seam on the other polarity."""
    assert _ticks([-10_000]) == [255, 1, 255, 1, 255, 1, 235]


def test_frame_markers() -> None:
    """The frame carries a pause and a repeat byte around the payload."""
    frame = timings_to_raw_frame([240, -240], 1)
    assert frame[:4] == b"P\x02R\x01"
    assert frame.endswith(b"+")
    assert _payload(frame) == bytes([24, 24])


def test_repeat_is_clamped() -> None:
    """Repeat counts outside 1..255 are clamped rather than rejected."""
    assert timings_to_raw_frame([240], 0)[2:4] == b"R\x01"
    assert timings_to_raw_frame([240], 300)[2:4] == b"R\xff"
    assert timings_to_raw_frame([240], 5)[2:4] == b"R\x05"


def test_pause_is_clamped() -> None:
    """A zero pause would truncate the command chain, so the floor is 1 ms."""
    assert timings_to_raw_frame([240], 1, pause_ms=0)[:2] == b"P\x01"
    assert timings_to_raw_frame([240], 1, pause_ms=999)[:2] == b"P\xff"


def test_net_v1_repeat_is_trimmed() -> None:
    """A Net v1 frame trims repeats instead of refusing the whole command."""
    timings = [100] * 100  # 100 pulses
    frame = timings_to_raw_frame(
        timings, 10, max_pulses=NET_V1_MAX_PULSES
    )
    # 199 // 100 == 1 repeat, and the payload still fits.
    assert frame[2:4] == b"R\x01"
    assert len(_payload(frame)) == 100


def test_net_v1_frame_too_long() -> None:
    """A single frame that does not fit the Net v1 payload limit is refused."""
    try:
        timings_to_raw_frame([100] * 250, 1, max_pulses=NET_V1_MAX_PULSES)
    except ValueError as err:
        assert "exceeds" in str(err)
    else:  # pragma: no cover - only runs on a broken build
        raise AssertionError("expected ValueError for an oversized frame")


def test_empty_timings() -> None:
    """Nothing to send is an error, not an empty frame."""
    try:
        timings_to_raw_frame([])
    except ValueError as err:
        assert "no timings" in str(err)
    else:  # pragma: no cover - only runs on a broken build
        raise AssertionError("expected ValueError for empty timings")


def main() -> int:
    """Run every test_* function and report a summary."""
    failures = 0
    for name, func in sorted(globals().items()):
        if not name.startswith("test_") or not callable(func):
            continue
        try:
            func()
        except Exception as err:  # noqa: BLE001
            failures += 1
            print(f"  [FAIL] {name}: {err}")
        else:
            print(f"  [PASS] {name}")
    print(f"{'FAILED' if failures else 'OK'} — {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
