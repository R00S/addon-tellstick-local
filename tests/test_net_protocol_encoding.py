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
            _TURNON,
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

        # Dim goes out as a native dict, not raw pulses: handleSend() does not
        # forward the level, so the firmware's TURNON -> DIM(255) workaround is
        # used instead of an S-key pulse train.
        result = _encode_arctech_command("selflearning-dimmer", "12345", "1", "dim", 128)
        report("dim returns native dict", isinstance(result, dict), f"type={type(result)}")
        if isinstance(result, dict):
            report(
                "dim model=selflearning-dimmer",
                result.get("model") == "selflearning-dimmer",
            )
            report("dim sent as TURNON (firmware DIM(255))", result.get("method") == _TURNON)

        # Dim on TellStick Net v1: raw S pulse train, no protocol key, because
        # the v1 C send() handler only accepts model="selflearning" and drops
        # everything else before RF (issue #130).
        train = _encode_arctech_command(
            "selflearning-dimmer", "12345", "1", "dim", 128, net_v1=True
        )
        report("dim (Net v1) returns dict", isinstance(train, dict), f"type={type(train)}")
        if isinstance(train, dict):
            report("dim (Net v1) is S-only", list(train) == ["S"], f"keys={list(train)}")
            pulses = train.get("S")
            report("dim (Net v1) S is bytes", isinstance(pulses, bytes), f"type={type(pulses)}")
            report(
                "dim (Net v1) pulse train is 147 bytes",
                isinstance(pulses, bytes) and len(pulses) == 147,
                f"len={len(pulses) if isinstance(pulses, bytes) else '?'}",
            )
            report(
                "dim (Net v1) train starts 18ff and ends 18",
                isinstance(pulses, bytes)
                and pulses[:2] == b"\x18\xff"
                and pulses[-1:] == b"\x18",
            )
            level_hi = _encode_arctech_command(
                "selflearning-dimmer", "12345", "1", "dim", 255, net_v1=True
            )
            level_lo = _encode_arctech_command(
                "selflearning-dimmer", "12345", "1", "dim", 16, net_v1=True
            )
            report(
                "dim (Net v1) level changes the frame",
                isinstance(level_hi, dict)
                and isinstance(level_lo, dict)
                and level_hi.get("S") != pulses
                and level_lo.get("S") != level_hi.get("S"),
            )

        # v1 dim at level 0 is still TURNOFF via the native dict
        level_zero = _encode_arctech_command(
            "selflearning-dimmer", "12345", "1", "dim", 0, net_v1=True
        )
        report(
            "dim (Net v1) level 0 -> TURNOFF",
            isinstance(level_zero, dict) and level_zero.get("method") == 2,
            f"result={level_zero}",
        )

        # Unsupported method
        result = _encode_arctech_command("selflearning-switch", "12345", "1", "invalid")
        report("invalid method returns None", result is None)

    except Exception as e:
        report("Arctech encoder", False, str(e))
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------------
    # Test 3b: Net v1 raw pulse-train encoders (Duo protocol parity)
    #   Ported from telldus-core; every frame is S-only (plus R/P).
    # ---------------------------------------------------------------
    print("\n=== Test 3b: Net v1 raw encoders ===")
    try:
        from custom_components.tellstick_local.net_client import (
            _NET_V1_MAX_PULSES,
            _encode_net_v1_raw,
        )

        # (name, protocol, model, house, unit, method, param, expected len, prefix)
        cases = [
            ("arctech on", "arctech", "selflearning-switch", 12345, "1", "turnon", None, 131, b"\x18\xff"),
            ("arctech dim", "arctech", "selflearning-dimmer", 12345, "1", "dim", 128, 147, b"\x18\xff"),
            ("arctech codeswitch", "arctech", "codeswitch", "C", "5", "turnon", None, 50, b"$k$k"),
            ("arctech bell", "arctech", "bell", "C", "1", "bell", None, 82, b"$k$k"),
            ("comen", "comen", "selflearning-switch", 100, "1", "turnon", None, 131, b"\x18\xff"),
            ("everflourish", "everflourish", "selflearning-switch", 100, "1", "turnon", None, 108, b"\x3c"),
            ("sartano", "sartano", "codeswitch", "0101010101", "1", "turnon", None, 50, b"$kk$"),
            ("yidong", "yidong", "goobay", "0", "3", "turnon", None, 50, b"$k$k"),
            ("waveman", "waveman", "codeswitch", "K", "5", "turnon", None, 50, b"$k$k"),
            ("upm", "upm", "selflearning", 2047, "2", "turnon", None, 41, b";"),
            ("fuhaote", "fuhaote", "codeswitch", "0101010101", "1", "turnon", None, 49, b"\x13\x3a"),
            ("brateck up", "brateck", "codeswitch", "01010100", "1", "up", None, 49, b"!V"),
            ("risingsun selflearning", "risingsun", "selflearning", 1000, "3", "turnon", None, 66, b"\x78"),
            ("risingsun codeswitch", "risingsun", "codeswitch", "2", "3", "turnoff", None, 50, b".e"),
            ("x10", "x10", "codeswitch", "B", "5", "turnon", None, 75, b"\xff\x01"),
            ("hasta v1 up", "hasta", "selflearning", 1234, "2", "up", None, 85, b"\xa4\x01"),
            ("hasta v2 stop", "hasta", "selflearningv2", 1234, "2", "stop", None, 92, b"\xf5\x01"),
            ("ikea dim", "ikea", "selflearning", 3, "1,4", "dim", 100, 39, b"\x54"),
            ("silvanchip kp100", "silvanchip", "kp100", 123456, "1", "up", None, 126, b"\x64"),
            ("silvanchip ecosavers", "silvanchip", "ecosavers", 123456, "2", "turnon", None, 60, b"\x25"),
        ]
        for name, proto, model, house, unit, method, param, exp_len, prefix in cases:
            res = _encode_net_v1_raw(proto, model, house, unit, method, param)
            ok = isinstance(res, dict) and isinstance(res.get("S"), bytes)
            report(f"{name}: returns S bytes", ok, f"result={type(res)}")
            if not ok:
                continue
            pulses = res["S"]
            report(
                f"{name}: length {exp_len}",
                len(pulses) == exp_len,
                f"len={len(pulses)}",
            )
            report(
                f"{name}: prefix",
                pulses.startswith(prefix),
                f"head={pulses[:4].hex()}",
            )
            report(
                f"{name}: S-only (+R/P)",
                set(res) <= {"S", "R", "P"},
                f"keys={sorted(res)}",
            )
            report(
                f"{name}: within firmware limit",
                len(pulses) <= _NET_V1_MAX_PULSES,
                f"len={len(pulses)}",
            )

        # Per-protocol repeat/pause parameters
        # hasta must NOT set R/P: telldus-core's hasta string carries none, so
        # the Duo sends it with hardware defaults.  "Duo parity" means the same.
        hasta = _encode_net_v1_raw("hasta", "selflearning", 1234, "2", "up")
        report(
            "hasta v1 uses Duo defaults (no R/P)",
            isinstance(hasta, dict) and set(hasta) == {"S"},
            f"{hasta and {k: v for k, v in hasta.items() if k != 'S'}}",
        )
        rising_learn = _encode_net_v1_raw(
            "risingsun", "selflearning", 1000, "3", "learn"
        )
        report(
            "risingsun learn requests P=5 R=50",
            isinstance(rising_learn, dict)
            and rising_learn.get("P") == 5
            and rising_learn.get("R") == 50,
        )

        # Unsupported method/model must fall through, never build a bad frame
        report(
            "arctech codeswitch dim -> None",
            _encode_net_v1_raw("arctech", "codeswitch", "C", "5", "dim", 128) is None,
        )
        report(
            "brateck turnon -> None",
            _encode_net_v1_raw("brateck", "codeswitch", "01010100", "1", "turnon") is None,
        )
        report(
            "silvanchip unknown model -> None",
            _encode_net_v1_raw("silvanchip", "mystery", 1, "1", "turnon") is None,
        )
        report(
            "kangtai has no Duo encoder -> None",
            _encode_net_v1_raw("kangtai", "selflearning-switch", 1, "1", "turnon") is None,
        )
        report(
            "sartano rejects non-binary code",
            _encode_net_v1_raw("sartano", "codeswitch", "ABCDEF", "1", "turnon") is None,
        )

    except Exception as e:
        report("Net v1 raw encoders", False, str(e))
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------------
    # Test 3c: Duo-style raw commands (P/R + S) translated for Net v1
    #   Covers the protocols we added on the Duo path on top of telldus-core:
    #   luxorparts, generic_rf record & replay, and the Tuya curtain motor.
    # ---------------------------------------------------------------
    print("\n=== Test 3c: Duo raw commands on Net v1 ===")
    try:
        from custom_components.tellstick_local.const import (
            generic_rf_build_raw_command,
            luxorparts_build_raw_command,
            timings_to_tellstick_bytes,
        )
        from custom_components.tellstick_local.net_client import (
            _parse_duo_raw_command,
        )

        pulses, pause, repeats = _parse_duo_raw_command(b"P\x02R\x0aS\x01\x02+")
        report("parses P/R prefix", pause == 2 and repeats == 10, f"P={pause} R={repeats}")
        report("strips S/+ markers", pulses == b"\x01\x02", f"pulses={pulses!r}")

        plain, plain_pause, plain_repeats = _parse_duo_raw_command(b"S\x18\xff+")
        report(
            "plain S command keeps firmware defaults",
            plain == b"\x18\xff" and plain_pause is None and plain_repeats is None,
        )

        # generic_rf record & replay
        timings = [392, -1148, 392, -1148]
        cmd = generic_rf_build_raw_command(timings, repeat_count=5)
        gp, gpause, grepeats = _parse_duo_raw_command(cmd)
        report(
            "generic_rf pulses survive translation",
            gp == timings_to_tellstick_bytes(timings),
            f"len={len(gp)}",
        )
        report("generic_rf repeat/pause preserved", grepeats == 5 and gpause == 2)

        # luxorparts
        lp, lpause, lrepeats = _parse_duo_raw_command(
            luxorparts_build_raw_command(1, "")
        )
        report(
            "luxorparts frame parsed (50 pulses)",
            isinstance(lp, bytes) and len(lp) == 50,
            f"len={len(lp) if isinstance(lp, bytes) else '?'}",
        )
        report(
            "luxorparts within v1 limit",
            len(lp) <= 199 and lrepeats is not None and lpause is not None,
            f"R={lrepeats} P={lpause}",
        )

        # Tuya / Kjell curtain motor (84-byte frames in the Duo builder)
        from custom_components.tellstick_local.tuya_curtain import (
            build_curtain_command,
            payload_for_button,
        )

        tp, tpause, trepeats = _parse_duo_raw_command(
            build_curtain_command(payload_for_button("up"), "a")
        )
        report(
            "tuya curtain frame parsed",
            isinstance(tp, bytes) and len(tp) > 0 and trepeats is not None,
            f"len={len(tp) if isinstance(tp, bytes) else '?'} R={trepeats} P={tpause}",
        )

    except Exception as e:
        report("Duo raw command translation", False, str(e))
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

        # Raw catalog = full catalog + legacy EF variants + new raw + new native
        from custom_components.tellstick_local.const import (
            _EF_RAW_VARIANTS,
            _EF_TEST_NATIVE_VARIANTS,
            _EF_TEST_RAW_VARIANTS,
        )

        expected_raw = (
            len(PROTOCOL_MODEL_CATALOG)
            + len(_EF_RAW_VARIANTS)
            + len(_EF_TEST_RAW_VARIANTS)
            + len(_EF_TEST_NATIVE_VARIANTS)
        )
        report(
            "raw catalog = full catalog + all EF variants",
            len(PROTOCOL_RAW_CATALOG) == expected_raw,
            f"raw={len(PROTOCOL_RAW_CATALOG)} vs expected={expected_raw}",
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
