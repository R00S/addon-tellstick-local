"""Reproduce issue #131: the "Send learn signal" step of the add-device flow.

Three modes:

  python tools/repro_issue131.py                 # fake ZNet on 127.0.0.1
  python tools/repro_issue131.py --host 192.168.1.50 --product TellstickZnet
  python tools/repro_issue131.py --serve         # just run the fake ZNet

``--serve`` is the one to use against a real Home Assistant: run it on any
machine in the LAN, add that IP as a TellStick Net / ZNet hub, and press
"Send learn signal".  If Core still restarts, the integration is the cause;
if it does not, the unit's own reply is.  Every packet it receives is printed.

``--echo N`` sets how many ``RawData`` packets the fake unit sends back after a
learn (the real firmware sends its own transmission back, so a big number
models a chatty unit).

The default mode starts a fake TellStick Net v2 on 127.0.0.1:42314 that accepts
the integration's packets and echoes ``RawData`` events back the way the
firmware does after a learn.  The script then boots a minimal Home Assistant,
builds a Net config entry and runs the add-device flow's final ``confirm`` step
(the one behind the "Send learn signal" button) while a monitor task measures
how long the event loop is stalled.

With ``--host`` the learn signal is sent to a real unit instead; the script
still measures the loop and prints the ``RawData`` packets the unit sends back.
Nothing is written to the config entry in that mode.

Exit status: 0 = the step finished, 1 = the step raised or never returned.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import tempfile
import threading
import time
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

COMMAND_PORT = 42314


class FakeZNet(threading.Thread):
    """Minimal TellStick Net v2 on 127.0.0.1: accepts send, echoes RawData."""

    def __init__(self, echo: int = 4, verbose: bool = False) -> None:
        super().__init__(daemon=True)
        self.echo = echo
        self.verbose = verbose
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # 0.0.0.0 so a Home Assistant on another machine can reach it too.
        self.sock.bind(("", COMMAND_PORT))
        self.sock.settimeout(0.2)
        self.received: list[bytes] = []
        self.sent = 0
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            self.received.append(data)
            if self.verbose:
                print(f"  <- {data[:120]!r}", flush=True)
            if b"send" in data:
                self._echo_learn(data, addr)

    def _echo_learn(self, data: bytes, addr: tuple[str, int]) -> None:
        """Send the packets a v2/ZNet pushes after it transmits a learn burst."""
        from custom_components.tellstick_local.net_client import encode_packet

        for method in (32, 32, 1, 1) * max(1, self.echo // 4):
            # Same shape the panel firmware pushes back after its own TX.
            packet = encode_packet(
                "RawData",
                **{
                    "class": "command",
                    "protocol": "arctech",
                    "model": "selflearning",
                    "house": 12345678,
                    "unit": 0,
                    "method": method,
                    "data": 0x1234ABCD,
                },
            )
            try:
                self.sock.sendto(packet, addr)
                self.sent += 1
            except OSError:
                return

    def stop(self) -> None:
        self._stop.set()
        self.sock.close()


class LoopMonitor:
    """Track how long the event loop is unavailable."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.max_stall = 0.0
        self._task: asyncio.Task | None = None

    async def _run(self) -> None:
        while True:
            start = self.loop.time()
            await asyncio.sleep(0.02)
            stall = self.loop.time() - start - 0.02
            self.max_stall = max(self.max_stall, stall)

    def start(self) -> None:
        self._task = self.loop.create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()


async def run(host: str, product: str, echo: bool) -> int:
    from homeassistant import config_entries as ce_mod
    from homeassistant.core import HomeAssistant

    from custom_components.tellstick_local.config_flow import (
        TellStickLocalAddDeviceFlow,
    )
    from custom_components.tellstick_local.const import (
        CONF_BACKEND,
        CONF_DEVICE_ENCODING,
        CONF_DEVICE_HOUSE,
        CONF_DEVICE_MODEL,
        CONF_DEVICE_NAME,
        CONF_DEVICE_PROTOCOL,
        CONF_DEVICE_UNIT,
        DOMAIN,
        ENTRY_DEVICE_ID_MAP,
        ENTRY_MIRRORS,
        ENTRY_TELLSTICK_CONTROLLER,
    )
    from custom_components.tellstick_local.net_client import TellStickNetController

    hass = HomeAssistant(tempfile.mkdtemp(prefix="ha_repro_"))
    hass.config.config_dir = tempfile.mkdtemp(prefix="ha_repro_cfg_")
    hass.data.setdefault("integrations", {})
    hass.data.setdefault("custom_components", None)
    hass.data.setdefault("preload_platforms", set())
    hass.data.setdefault("components", {})
    hass.data.setdefault("missing_platforms", {})
    hass.config_entries = ce_mod.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()

    class Entry:
        entry_id = "repro-entry"
        title = "TellStick Local"
        data = {CONF_BACKEND: "net", "host": host}
        options: dict = {}

    entry = Entry()
    stored: list[dict] = []

    def _update_entry(_entry, **kwargs):
        if "options" in kwargs:
            _entry.options = kwargs["options"]
            stored.append(dict(kwargs["options"]))

    hass.config_entries.async_update_entry = _update_entry  # type: ignore[assignment]

    events: list[str] = []
    controller = TellStickNetController(host=host, product=product)
    controller.add_callback(lambda ev: events.append(getattr(ev, "raw", repr(ev))))
    controller.add_raw_packet_callback(lambda pkt: events.append("raw:" + str(pkt)))
    await controller.connect()
    controller.start_event_listener()

    hass.data[DOMAIN] = {
        entry.entry_id: {
            ENTRY_TELLSTICK_CONTROLLER: controller,
            ENTRY_DEVICE_ID_MAP: {},
            ENTRY_MIRRORS: [],
        }
    }

    class Flow(TellStickLocalAddDeviceFlow):
        def _get_entry(self):  # noqa: ANN202
            return entry

    flow = Flow()
    flow.hass = hass  # type: ignore[assignment]
    flow.flow_id = "repro-flow"
    flow.handler = entry.entry_id
    flow._new_device = {  # noqa: SLF001
        CONF_DEVICE_NAME: "Nexa test",
        CONF_DEVICE_PROTOCOL: "arctech",
        CONF_DEVICE_MODEL: "selflearning-switch:nexa",
        CONF_DEVICE_HOUSE: "12345678",
        CONF_DEVICE_UNIT: "1",
        CONF_DEVICE_ENCODING: "",
    }

    monitor = LoopMonitor(asyncio.get_running_loop())
    monitor.start()
    started = time.monotonic()
    status = 0
    try:
        result = await asyncio.wait_for(
            flow.async_step_confirm(user_input={}), timeout=20
        )
        elapsed = time.monotonic() - started
        print(f"confirm step returned in {elapsed:.2f}s: {result}")
        print(f"config entry writes: {len(stored)}")
        if stored:
            print(f"stored devices: {sorted(stored[-1].get('devices', {}))}")
    except asyncio.TimeoutError:
        print("FAIL: the confirm step never returned (20s)")
        status = 1
    except Exception:  # noqa: BLE001
        print("FAIL: the confirm step raised")
        traceback.print_exc()
        status = 1

    await asyncio.sleep(1.5)  # let echoed packets be dispatched
    monitor.stop()

    print(f"event-loop max stall: {monitor.max_stall * 1000:.0f} ms")
    print(f"controller packets received: {controller.packets_received}")
    print(f"callbacks fired: {len(events)}")
    await controller.disconnect()
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--product", default="TellstickNetV2")
    parser.add_argument("--echo", type=int, default=4, help="RawData packets per learn")
    parser.add_argument("--serve", action="store_true", help="run the fake unit only")
    args = parser.parse_args()

    fake = None
    if args.host == "127.0.0.1" or args.serve:
        try:
            fake = FakeZNet(echo=args.echo, verbose=args.serve)
            fake.start()
            print(f"fake ZNet listening on 127.0.0.1:{COMMAND_PORT}", flush=True)
        except OSError as err:
            print(f"cannot bind {COMMAND_PORT}: {err}")
            return 1

    if args.serve:
        print("add 127.0.0.1 as a TellStick Net / ZNet hub, press learn, Ctrl-C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            fake.stop()
        return 0

    try:
        status = asyncio.run(run(args.host, args.product, fake is not None))
    finally:
        if fake is not None:
            time.sleep(0.2)
            print(f"fake ZNet sent {fake.sent} echo packets")
            fake.stop()

    return status


if __name__ == "__main__":
    sys.exit(main())
