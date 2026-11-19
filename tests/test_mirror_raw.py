"""Offline checks for mirroring raw pulse commands (no hardware).

Covers ``entity.async_mirror_raw_command`` — the path that replicates the
protocols we build ourselves (Luxorparts, Generic RF record & replay, the
Tuya/Kjell curtain motor) to every mirror controller, plus the API symmetry
that makes the call work on both the Duo and the Net controller.

Run with the project's Home Assistant venv:
    python tests/test_mirror_raw.py
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.tellstick_local import entity  # noqa: E402
from custom_components.tellstick_local.client import TellStickController  # noqa: E402
from custom_components.tellstick_local.const import DOMAIN, ENTRY_MIRRORS  # noqa: E402
from custom_components.tellstick_local.net_client import (  # noqa: E402
    TellStickNetController,
)

PASSED = 0
FAILED = 0

ENTRY_ID = "entry"
DEVICE_UID = "luxorparts_1"


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"[PASS] {name}")
    else:
        FAILED += 1
        print(f"[FAIL] {name} {detail}".rstrip())


class FakeController:
    """Records what a mirror controller was asked to transmit."""

    def __init__(self, result: int = 0) -> None:
        self.calls: list[tuple[bytes, bool]] = []
        self._result = result

    async def send_raw_command(
        self, command: bytes, reserved: int = 0, quiet: bool = False
    ) -> int:
        self.calls.append((bytes(command), quiet))
        return self._result


class NoRawController:
    """A controller with no raw TX capability at all."""


def make_hass(mirrors: list[dict[str, object]]) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        data={DOMAIN: {ENTRY_ID: {ENTRY_MIRRORS: mirrors}}}
    )


def run(hass, raw: bytes, uid: str = DEVICE_UID) -> None:
    asyncio.run(entity.async_mirror_raw_command(hass, ENTRY_ID, raw, uid))


# ---------------------------------------------------------------------------
# 1. Every capable mirror receives the identical pulse train, quietly.
# ---------------------------------------------------------------------------
RAW = b"S" + bytes([3, 1] * 8) + b"+"
duo_mirror = FakeController(0)          # Duo answers 0
v1_mirror = FakeController(-5)          # Duo-style ACK timeout is normal
run(make_hass([{"controller": duo_mirror}, {"controller": v1_mirror}]), RAW)

check("duo mirror got the frame", len(duo_mirror.calls) == 1)
check(
    "frame is byte-identical",
    duo_mirror.calls and duo_mirror.calls[0][0] == RAW,
    repr(duo_mirror.calls),
)
check("mirror sends request quiet=True", duo_mirror.calls and duo_mirror.calls[0][1] is True)
check("second mirror also got it", len(v1_mirror.calls) == 1)
check(
    "expected ACK timeout (-5) is not an error",
    v1_mirror.calls and v1_mirror.calls[0][0] == RAW,
)

# ---------------------------------------------------------------------------
# 2. Nothing to mirror / nothing to send.
# ---------------------------------------------------------------------------
idle = FakeController()
run(make_hass([]), RAW)
check("no mirrors → no transmission", idle.calls == [])

unused = FakeController()
run(make_hass([{"controller": unused}]), b"")
check("empty raw command is ignored", unused.calls == [])

# ---------------------------------------------------------------------------
# 3. A mirror without raw TX is skipped; the others still fire.
# ---------------------------------------------------------------------------
healthy = FakeController()
run(
    make_hass([{"controller": NoRawController()}, {"controller": healthy}]),
    RAW,
)
check("controller without raw TX is skipped", len(healthy.calls) == 1)

# ---------------------------------------------------------------------------
# 4. One failing mirror does not stop the remaining ones.
# ---------------------------------------------------------------------------
class RaisingController:
    async def send_raw_command(self, command, reserved=0, quiet=False):
        raise RuntimeError("UDP send failed")


after_failure = FakeController()
run(
    make_hass([{"controller": RaisingController()}, {"controller": after_failure}]),
    RAW,
)
check("failure in one mirror does not block the next", len(after_failure.calls) == 1)

# ---------------------------------------------------------------------------
# 5. Missing hass is a no-op (entity not added yet).
# ---------------------------------------------------------------------------
try:
    run(None, RAW)
    check("hass=None is a no-op", True)
except Exception as err:  # noqa: BLE001
    check("hass=None is a no-op", False, repr(err))

# ---------------------------------------------------------------------------
# 6. API symmetry: both controllers accept the quiet keyword.
# ---------------------------------------------------------------------------
for cls in (TellStickController, TellStickNetController):
    params = inspect.signature(cls.send_raw_command).parameters
    check(
        f"{cls.__name__}.send_raw_command accepts quiet",
        "quiet" in params,
        str(params),
    )

# ---------------------------------------------------------------------------
# 7. Each raw-building platform mirrors its own pulse train.
# ---------------------------------------------------------------------------
for module, expected in (("switch.py", 2), ("light.py", 1), ("cover.py", 1)):
    source = (ROOT / "custom_components" / "tellstick_local" / module).read_text()
    calls = source.count("_async_mirror_raw(")
    check(
        f"{module} mirrors raw commands ({expected} helper(s))",
        calls >= expected,
        f"found {calls}",
    )

button_source = (ROOT / "custom_components" / "tellstick_local" / "button.py").read_text()
check(
    "button.py mirrors the Luxorparts learn frame",
    "async_mirror_raw_command(" in button_source,
)

# Raw protocols must not ALSO go through the per-device mirror dispatch, which
# would send an unusable firmware dict after the correct pulse train.
for module in ("switch.py", "light.py", "cover.py"):
    source = (ROOT / "custom_components" / "tellstick_local" / module).read_text()
    check(
        f"{module} skips the dict mirror for raw protocols",
        "if not raw_sent:" in source,
    )

print()
print("=" * 50)
print(f"{PASSED} checks passed, {FAILED} failed")
if FAILED:
    print("SOME TESTS FAILED")
    raise SystemExit(1)
print("ALL TESTS PASSED")
