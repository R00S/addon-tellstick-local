"""Test that the TellStick Local integration loads and works in Home Assistant.

Usage:
    pip install homeassistant pyflakes
    python tests/test_ha_integration.py

This boots a minimal HA Core instance with the custom integration installed
and verifies that all modules load, config flows work, and hassio discovery
is functional — without needing TellStick hardware.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import traceback

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


async def run_tests() -> None:
    """Run all integration tests."""
    from homeassistant import config_entries as ce_mod, loader
    from homeassistant.core import HomeAssistant

    # Set up a temp HA config dir with our custom_components
    config_dir = tempfile.mkdtemp(prefix="ha_test_")
    cc_src = os.path.join(REPO_ROOT, "custom_components")
    cc_dst = os.path.join(config_dir, "custom_components")
    shutil.copytree(cc_src, cc_dst)

    hass = HomeAssistant(config_dir)
    hass.config.config_dir = config_dir

    # Initialize data structures the HA loader needs
    hass.data.setdefault("integrations", {})
    hass.data.setdefault("custom_components", None)
    hass.data.setdefault("preload_platforms", set())
    hass.data.setdefault("components", {})
    hass.data.setdefault("missing_platforms", {})

    # Initialize config entries system (needed for flow tests)
    config_entries = ce_mod.ConfigEntries(hass, {})
    hass.config_entries = config_entries
    await config_entries.async_initialize()

    # -- Test 1: Load integration --
    print("=== Test 1: Load integration from custom_components ===")
    try:
        integration = await loader.async_get_integration(hass, "tellstick_local")
        report(
            "Load integration",
            True,
            f"{integration.name} v{integration.version}",
        )
    except Exception as e:
        report("Load integration", False, str(e))

        traceback.print_exc()
        shutil.rmtree(config_dir)
        return

    # -- Test 2: Import config flow module --
    print("\n=== Test 2: Import config flow (detects broken imports) ===")
    try:
        component = integration.get_component()
        report("Get component", True, str(component))
        config_flow_mod = integration.get_platform("config_flow")
        report("Get config_flow", True, str(config_flow_mod))
    except Exception as e:
        report("Import config flow", False, str(e))

        traceback.print_exc()

    # -- Test 3: User config flow --
    print("\n=== Test 3: Init user config flow ===")
    try:
        flow_result = await hass.config_entries.flow.async_init(
            "tellstick_local",
            context={"source": ce_mod.SOURCE_USER},
        )
        ok = flow_result.get("step_id") == "user"
        report(
            "User flow",
            ok,
            f"type={flow_result['type']} step={flow_result.get('step_id')}",
        )
    except Exception as e:
        report("User flow", False, str(e))

        traceback.print_exc()

    # -- Test 4: Hassio discovery flow --
    print("\n=== Test 4: Hassio discovery flow ===")
    try:
        from homeassistant.helpers.service_info.hassio import HassioServiceInfo

        info = HassioServiceInfo(
            config={"host": "test-host", "port": 50800},
            name="TellStick Local",
            slug="tellsticklive",
            uuid="testuuid1234",
        )
        flow_result = await hass.config_entries.flow.async_init(
            "tellstick_local",
            context={"source": ce_mod.SOURCE_HASSIO},
            data=info,
        )
        ok = flow_result.get("step_id") == "hassio_confirm"
        report(
            "Hassio discovery",
            ok,
            f"type={flow_result['type']} step={flow_result.get('step_id')}",
        )
    except Exception as e:
        report("Hassio discovery", False, str(e))

        traceback.print_exc()

    # -- Test 5: OptionsFlow --
    print("\n=== Test 5: OptionsFlow instantiation ===")
    try:
        from custom_components.tellstick_local.config_flow import (
            TellStickLocalOptionsFlow,
        )

        flow = TellStickLocalOptionsFlow()
        ok = isinstance(flow, TellStickLocalOptionsFlow)
        report("OptionsFlow", ok)
    except Exception as e:
        report("OptionsFlow", False, str(e))

        traceback.print_exc()

    # -- Test 6: All platform modules --
    print("\n=== Test 6: Import all modules ===")
    for mod in [
        "client",
        "const",
        "entity",
        "switch",
        "light",
        "sensor",
        "device_trigger",
    ]:
        try:
            __import__(f"custom_components.tellstick_local.{mod}")
            report(f"Import {mod}", True)
        except Exception as e:
            report(f"Import {mod}", False, str(e))

    print(f"\n{'=' * 50}")
    print(f"{'ALL TESTS PASSED' if ALL_PASS else 'SOME TESTS FAILED'}")
    print(f"{'=' * 50}")

    await hass.async_stop()
    shutil.rmtree(config_dir)


if __name__ == "__main__":
    asyncio.run(run_tests())
    sys.exit(0 if ALL_PASS else 1)
