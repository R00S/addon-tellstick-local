"""Tests for the shared Net/ZNet UDP listener (issue #115).

Regression tests for the bug where every Net/ZNet config entry bound its own
SO_REUSEADDR socket to UDP port 42314: a unicast datagram was delivered to
only one of those sockets (the one bound last), so with a primary + mirror
entries only one entry saw traffic and dropped everything not from its own
TellStick host.  Sensors on the primary then stopped updating until it was
reloaded (binding last).

Verifies that:
1. Datagrams are dispatched by source IP to the matching entry's controller
   (not to whichever socket bound last)
2. Datagrams from hosts with no configured entry are ignored
3. Datagrams arriving before start_event_listener() are buffered, not lost
4. The shared socket is reference-counted: closed with the last controller,
   reopened when a controller connects again

Usage:
    python tests/test_net_udp_hub.py
"""
from __future__ import annotations

import asyncio
import os
import socket
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


def _make_packet(marker: str) -> bytes:
    """Build a RawData event packet tagged with a recognisable protocol."""
    from custom_components.tellstick_local.net_client import encode_packet

    return encode_packet(
        "RawData",
        _class="sensor",
        protocol=marker,
        model="temperaturehumidity",
        id=1,
        values=[{"type": 1, "value": "21.5"}],
    )


def _sender(ip: str) -> socket.socket | None:
    """Open a UDP sender socket bound to a source IP, or None if not possible."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((ip, 0))
    except OSError:
        sock.close()
        return None
    return sock


async def run_tests() -> None:
    """Run all shared-UDP-hub tests."""
    from custom_components.tellstick_local import net_client

    hub = net_client._NetUdpHub(port=0)
    net_client._HUB = hub  # route controllers created below onto the test hub

    ctrl_a = net_client.TellStickNetController(host="127.0.0.1")
    ctrl_b = net_client.TellStickNetController(host="127.0.0.2")
    got_a: list[object] = []
    got_b: list[object] = []
    ctrl_a.add_callback(got_a.append)
    ctrl_b.add_callback(got_b.append)

    # ---------------------------------------------------------------
    print("=== Test 1: datagrams dispatch by source IP to the right entry ===")
    # ---------------------------------------------------------------
    sender_a = _sender("127.0.0.1")
    sender_b = _sender("127.0.0.2")
    if sender_a is None or sender_b is None:
        report(
            "Source-IP routing (needs loopback aliases 127.0.0.1/127.0.0.2)",
            False,
            "could not bind test source addresses on this host",
        )
    else:
        await ctrl_a.connect()
        await ctrl_b.connect()
        ctrl_a.start_event_listener()
        ctrl_b.start_event_listener()
        port = hub._bound_port

        sender_a.sendto(_make_packet("proto-from-a"), ("127.0.0.1", port))
        await asyncio.sleep(0.5)
        report(
            "Host .1 packet reaches only the .1 entry",
            len(got_a) == 1 and not got_b
            and getattr(got_a[0], "protocol", "") == "proto-from-a",
            f"got_a={len(got_a)} got_b={len(got_b)}",
        )
        sender_b.sendto(_make_packet("proto-from-b"), ("127.0.0.2", port))
        await asyncio.sleep(0.5)
        report(
            "Host .2 packet reaches only the .2 entry",
            len(got_b) == 1 and len(got_a) == 1
            and getattr(got_b[0], "protocol", "") == "proto-from-b",
            f"got_a={len(got_a)} got_b={len(got_b)}",
        )

        # ---------------------------------------------------------------
        print("=== Test 2: packets from unknown hosts are dropped ===")
        # ---------------------------------------------------------------
        sender_c = _sender("127.0.0.3")
        if sender_c is None:
            report("Unknown-host drop", False, "could not bind 127.0.0.3")
        else:
            sender_c.sendto(_make_packet("proto-from-c"), ("127.0.0.1", port))
            await asyncio.sleep(0.5)
            report(
                "Packet from unconfigured host reaches no entry",
                len(got_a) == 1 and len(got_b) == 1,
                f"got_a={len(got_a)} got_b={len(got_b)}",
            )
            sender_c.close()

        # ---------------------------------------------------------------
        print("=== Test 3: packets before start_event_listener() are buffered ===")
        # ---------------------------------------------------------------
        await ctrl_a.disconnect()
        await ctrl_a.connect()  # subscribed, but not started yet
        sender_a.sendto(_make_packet("proto-buffered"), ("127.0.0.1", port))
        await asyncio.sleep(0.5)
        buffered = len(got_a)
        ctrl_a.start_event_listener()
        await asyncio.sleep(0.1)
        report(
            "Pre-start packet is delivered once the listener starts",
            len(got_a) == buffered + 1,
            f"before_start={buffered} after_start={len(got_a)}",
        )
        report(
            "Pre-start packet is not delivered twice",
            len(got_a) == 2,
            f"got_a={len(got_a)}",
        )

        # ---------------------------------------------------------------
        print("=== Test 4: shared socket is reference-counted ===")
        # ---------------------------------------------------------------
        await ctrl_a.disconnect()
        await ctrl_b.disconnect()
        report(
            "Hub socket closes with the last controller",
            hub._sock is None,
            f"sock={hub._sock}",
        )

        await ctrl_a.connect()
        ctrl_a.start_event_listener()
        port = hub._bound_port
        sender_a.sendto(_make_packet("proto-again"), ("127.0.0.1", port))
        await asyncio.sleep(0.5)
        report(
            "Hub reopens and routes again after all entries reloaded",
            len(got_a) == 3,
            f"got_a={len(got_a)}",
        )
        report(
            "last_packet_at is tracked for debug_connection",
            ctrl_a.last_packet_at is not None and ctrl_a.packets_received == 3,
            f"last={ctrl_a.last_packet_at} count={ctrl_a.packets_received}",
        )

        await ctrl_a.disconnect()
        sender_a.close()
        sender_b.close()

    net_client._HUB = None


def main() -> int:
    asyncio.run(run_tests())
    print("ALL PASS" if ALL_PASS else "SOME TESTS FAILED")
    return 0 if ALL_PASS else 1


if __name__ == "__main__":
    sys.exit(main())
