"""Tests for TellStick Net/ZNet protocol encoding.

Validates that:
1. The unit+1 firmware bug is compensated for in _encode_generic_command()
2. Raw pulse-train encoders produce correct output
3. Protocol catalog splits (raw vs native) are consistent

Usage:
    python tests/test_net_protocol_encoding.py
"""
from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

ALL_PASS = True


def report(name: str, ok: bool, detail: str = "") -> None:
    """Print a test result line."""
    global ALL_PASS  # noqa: PLW0603
    status = "PASS" if ok else "FAIL"
    if not ok:
        ALL_PASS = False
    suffix = f": {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")


def run_tests() -> None:
    """Run all protocol encoding tests."""

    # ---------------------------------------------------------------
    # Test 1: _encode_generic_command compensates for unit+1 bug
    # ---------------------------------------------------------------
    print("=== Test 1: Unit+1 bug compensation in _encode_generic_command ===")
    try:
        from custom_components.tellstick_local.net_client import (
            _encode_generic_command,
        )

        # If user sets unit=1 in the UI, we want the firmware to end up
        # with unit=1 after it adds 1.  So we send unit=0 (1-1=0), then
        # firmware does 0+1=1.
        result = _encode_generic_command("sartano", "codeswitch", "1", "1", "turnon")
        unit_sent = result["unit"]
        report(
            "Unit=1 → sent as 0 (firmware adds 1 → correct)",
            unit_sent == 0,
            f"unit_sent={unit_sent}",
        )

        result = _encode_generic_command("risingsun", "codeswitch", "2", "3", "turnon")
        unit_sent = result["unit"]
        report(
            "Unit=3 → sent as 2 (firmware adds 1 → correct)",
            unit_sent == 2,
            f"unit_sent={unit_sent}",
        )

        # Edge case: unit=0 → sent as -1 (unusual but consistent)
        result = _encode_generic_command("test", "model", "1", "0", "turnon")
        unit_sent = result["unit"]
        report(
            "Unit=0 → sent as -1 (edge case)",
            unit_sent == -1,
            f"unit_sent={unit_sent}",
        )

        # Non-integer unit: should pass through as string (no compensation)
        result = _encode_generic_command("test", "model", "A", "B", "turnon")
        report(
            "Non-integer unit passes through as string",
            result["unit"] == "B",
            f"unit={result['unit']}",
        )
    except Exception as e:
        report("Unit+1 compensation", False, str(e))
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------------
    # Test 2: Everflourish raw pulse encoder
    # ---------------------------------------------------------------
    print("\n=== Test 2: Everflourish raw pulse encoder ===")
    try:
        from custom_components.tellstick_local.net_client import (
            _encode_everflourish_command,
        )

        # Basic functionality
        result = _encode_everflourish_command(100, 1, "turnon")
        report("turnon returns bytes", isinstance(result, bytes), f"type={type(result)}")

        result = _encode_everflourish_command(100, 1, "turnoff")
        report("turnoff returns bytes", isinstance(result, bytes))

        result = _encode_everflourish_command(100, 1, "learn")
        report("learn returns bytes", isinstance(result, bytes))

        result = _encode_everflourish_command(100, 1, "dim")
        report("dim returns None (unsupported)", result is None)

        # Signal length: 8 preamble + (16+4+4)*4 data bits + 4 terminator = 108
        on_bytes = _encode_everflourish_command(0, 1, "turnon")
        report("Signal length = 108 bytes", len(on_bytes) == 108, f"len={len(on_bytes)}")

        # Different actions produce different bytes
        off_bytes = _encode_everflourish_command(0, 1, "turnoff")
        report("on ≠ off bytes", on_bytes != off_bytes)

        # Different units produce different bytes
        unit2_bytes = _encode_everflourish_command(0, 2, "turnon")
        report("unit=1 ≠ unit=2 bytes", on_bytes != unit2_bytes)

    except Exception as e:
        report("Everflourish encoder", False, str(e))
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------------
    # Test 3: Arctech encoder
    # ---------------------------------------------------------------
    print("\n=== Test 3: Arctech encoder ===")
    try:
        from custom_components.tellstick_local.net_client import (
            _encode_arctech_command,
        )

        # Native dict for turnon
        result = _encode_arctech_command("selflearning-switch", "12345", "1", "turnon")
        report("turnon returns dict", isinstance(result, dict), f"type={type(result)}")
        if isinstance(result, dict):
            report("protocol=arctech", result.get("protocol") == "arctech")
            report("model=selflearning", result.get("model") == "selflearning")
            # Unit should be 0-indexed (1-1=0)
            report("unit=0 (0-indexed)", result.get("unit") == 0, f"unit={result.get('unit')}")

        # Raw bytes for dim
        result = _encode_arctech_command("selflearning-dimmer", "12345", "1", "dim", 128)
        report("dim returns bytes (raw pulse)", isinstance(result, bytes), f"type={type(result)}")

        # Unsupported method
        result = _encode_arctech_command("selflearning-switch", "12345", "1", "invalid")
        report("invalid method returns None", result is None)

    except Exception as e:
        report("Arctech encoder", False, str(e))
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------------
    # Test 4: Protocol catalog splits are consistent
    # ---------------------------------------------------------------
    print("\n=== Test 4: Protocol catalog consistency ===")
    try:
        from custom_components.tellstick_local.const import (
            NET_RAW_PROTOCOLS,
            PROTOCOL_MODEL_CATALOG,
            PROTOCOL_NATIVE_CATALOG,
            PROTOCOL_NATIVE_LABELS,
            PROTOCOL_NATIVE_MAP,
            PROTOCOL_RAW_CATALOG,
            PROTOCOL_RAW_LABELS,
            PROTOCOL_RAW_MAP,
        )

        # Both catalogs now contain ALL protocols (users can test either path)
        report(
            "raw catalog = full catalog",
            len(PROTOCOL_RAW_CATALOG) == len(PROTOCOL_MODEL_CATALOG),
            f"raw={len(PROTOCOL_RAW_CATALOG)} vs full={len(PROTOCOL_MODEL_CATALOG)}",
        )
        report(
            "native catalog = full catalog",
            len(PROTOCOL_NATIVE_CATALOG) == len(PROTOCOL_MODEL_CATALOG),
            f"native={len(PROTOCOL_NATIVE_CATALOG)} vs full={len(PROTOCOL_MODEL_CATALOG)}",
        )

        raw_protos = {entry[1] for entry in PROTOCOL_RAW_CATALOG}
        native_protos = {entry[1] for entry in PROTOCOL_NATIVE_CATALOG}

        # Labels match catalog lengths
        report("Raw labels count", len(PROTOCOL_RAW_LABELS) == len(PROTOCOL_RAW_CATALOG))
        report("Native labels count", len(PROTOCOL_NATIVE_LABELS) == len(PROTOCOL_NATIVE_CATALOG))

        # Maps match catalog lengths
        report("Raw map count", len(PROTOCOL_RAW_MAP) == len(PROTOCOL_RAW_CATALOG))
        report("Native map count", len(PROTOCOL_NATIVE_MAP) == len(PROTOCOL_NATIVE_CATALOG))

        # Arctech and everflourish must be in BOTH catalogs
        report("arctech in raw", "arctech" in raw_protos)
        report("arctech in native", "arctech" in native_protos)
        report("everflourish in raw", "everflourish" in raw_protos)
        report("everflourish in native", "everflourish" in native_protos)

        # Other protocols must also be in both catalogs
        report("sartano in raw", "sartano" in raw_protos)
        report("sartano in native", "sartano" in native_protos)
        report("hasta in raw", "hasta" in raw_protos)
        report("hasta in native", "hasta" in native_protos)

    except Exception as e:
        report("Catalog consistency", False, str(e))
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------------
    # Test 5: Everflourish checksum
    # ---------------------------------------------------------------
    print("\n=== Test 5: Everflourish checksum algorithm ===")
    try:
        from custom_components.tellstick_local.net_client import (
            _everflourish_checksum,
        )

        # The checksum is 4 bits (0-15)
        for x in [0, 1, 100, 400, 16383]:
            cs = _everflourish_checksum(x)
            report(f"checksum({x}) in range", 0 <= cs <= 15, f"cs={cs}")

        # Checksum of 0 should be deterministic
        cs0 = _everflourish_checksum(0)
        report("checksum(0) is deterministic", cs0 == _everflourish_checksum(0))

        # Different inputs should (usually) give different checksums
        cs1 = _everflourish_checksum(1)
        cs100 = _everflourish_checksum(100)
        report("Different inputs → different checksums", cs1 != cs100 or cs0 != cs1)

    except Exception as e:
        report("Checksum", False, str(e))
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print(f"{'ALL TESTS PASSED' if ALL_PASS else 'SOME TESTS FAILED'}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    run_tests()
    sys.exit(0 if ALL_PASS else 1)
