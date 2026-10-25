#!/usr/bin/env python3
"""Probe the local UDP "send" path of a TellStick Net / ZNet (issue #114).

Sends five packet variants one at a time and asks you to watch the TellStick's
LED after each one.  Run it from ANY machine on the same LAN as the device
(laptop, HA host, NAS — it does not need Home Assistant):

    python3 tools/probe_net_send.py 192.168.1.244 --house 292130 --unit 1

Use the same house/unit the receiver is paired to (unit is 1-indexed, as in
the integration).  For each test, answer whether the TellStick LED blinked
(TX activity) and whether the receiver responded.

The five variants and what the results mean:

  A  native dict, no P/R          what TellStick Local 3.3.1.x sends today
  B  native dict + P/R in dict    documented format (developer.telldus.com)
  C  native dict + trailing P/R   molobrakos/tellsticknet (PR #27) format
  D  raw S pulse bytes            the firmware's direct rfSend() playback path
  E  raw S + P/R in dict          documented S format with repeats

  * All five blink   -> TX path fine; problem is elsewhere (codes/network).
  * A fails, B or C  -> firmware parses P/R differently than expected;
                        fix = adjust repeat-parameter placement for v1.
  * Only D/E blink   -> native arctech dict unsupported in this firmware;
                        fix = send arctech as raw S bytes on TellStick Net v1.
  * None blink       -> the local "send" command itself is missing/disabled
                        in this firmware build; local TX is not possible.

The script also listens for 30 s at the end: press a remote control button.
If packets arrive, local *events* work on this unit (UDP delivery is fine);
if nothing arrives, suspect delivery/firewall/VM networking instead.
"""

import argparse
import socket
import sys
import time

_TAG_SEP = ord(":")
_TAG_INTEGER = ord("i")
_TAG_DICT = ord("h")
_TAG_END = ord("s")


def _enc_str(s: str) -> bytes:
    b = s.encode()
    return b"%X%c%s" % (len(b), _TAG_SEP, b)


def _enc_bytes(s: bytes) -> bytes:
    return b"%X%c%s" % (len(s), _TAG_SEP, s)


def _enc_int(d: int) -> bytes:
    return b"%c%X%c" % (_TAG_INTEGER, int(d), _TAG_END)


def _enc_dict(d: dict) -> bytes:
    out = bytes([_TAG_DICT])
    for k, v in d.items():
        out += _enc_str(k)
        if isinstance(v, bytes):
            out += _enc_bytes(v)
        elif isinstance(v, str):
            out += _enc_str(v)
        else:
            out += _enc_int(v)
    return out + bytes([_TAG_END])


def encode_packet(command: str, args: dict | None = None, trailing: bytes = b"") -> bytes:
    res = _enc_str(command)
    if args:
        res += _enc_dict(args)
    return res + trailing


# Arctech selflearning raw pulse train (port of telldus-core ProtocolNexa /
# molobrakos tellsticknet/protocols/arctech.py).  unit is 1-indexed here.
_SHORT = bytes([24])
_LONG = bytes([127])
_ONE = _SHORT + _LONG + _SHORT + _SHORT
_ZERO = _SHORT + _SHORT + _SHORT + _LONG


def arctech_selflearning_pulses(house: int, unit: int, turn_on: bool) -> bytes:
    unit0 = max(0, min(15, unit - 1))
    code = _SHORT + bytes([255])
    for i in range(25, -1, -1):
        code += _ONE if house & (1 << i) else _ZERO
    code += _ZERO                      # group bit = 0
    code += _ONE if turn_on else _ZERO  # on/off bit
    for i in range(3, -1, -1):
        code += _ONE if unit0 & (1 << i) else _ZERO
    return code + _SHORT


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("host", help="IP address of the TellStick Net/ZNet")
    ap.add_argument("--house", type=int, required=True, help="house code the receiver is paired to")
    ap.add_argument("--unit", type=int, required=True, help="unit (1-16)")
    ap.add_argument("--port", type=int, default=42314)
    args = ap.parse_args()

    house, unit = args.house, args.unit
    unit0 = max(0, min(15, unit - 1))  # wire unit is 0-indexed (button number)

    native = dict(protocol="arctech", model="selflearning",
                  house=house, unit=unit0, method=1)
    pr_dict = dict(native, P=20, R=15)          # documented placement
    pr_trail = _enc_str("P") + _enc_int(10) + _enc_str("R") + _enc_int(4)
    pulses = arctech_selflearning_pulses(house, unit, turn_on=True)

    tests = [
        ("A  native dict, no P/R (current integration)", encode_packet("send", native)),
        ("B  native dict + P/R inside dict (documented)", encode_packet("send", pr_dict)),
        ("C  native dict + trailing P/R (molobrakos)",    encode_packet("send", native, pr_trail)),
        ("D  raw S pulse bytes, no P/R",                  encode_packet("send", {"S": pulses})),
        ("E  raw S pulse bytes + P/R in dict",            encode_packet("send", {"S": pulses, "P": 20, "R": 15})),
    ]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", args.port))
    except OSError:
        sock.bind(("", 0))
    print(f"Sending to {args.host}:{args.port} from {sock.getsockname()}")
    print(f"Target code: house={house} unit={unit} (wire button={unit0})\n")

    for label, packet in tests:
        input(f"Press Enter to send test {label} ...")
        sock.sendto(packet, (args.host, args.port))
        print(f"  sent {packet!r}")
        blink = input("  Did the TellStick LED blink? [y/n] ").strip().lower()
        resp = input("  Did the receiver respond? [y/n] ").strip().lower()
        print(f"  => LED={'YES' if blink == 'y' else 'no'}  receiver={'YES' if resp == 'y' else 'no'}\n")

    print("Now listening 30 s for RF events — press a button on a 433 MHz remote")
    print("(or watch a sensor) near the TellStick...\n")
    sock.settimeout(1.0)
    deadline = time.time() + 30
    got = 0
    while time.time() < deadline:
        try:
            data, src = sock.recvfrom(4096)
        except socket.timeout:
            continue
        got += 1
        print(f"  received {len(data)} bytes from {src}: {data[:80]!r}")
    print(f"\nEvents received: {got} "
          f"({'local events WORK — UDP delivery is fine' if got else 'NOTHING — suspect UDP delivery/firewall/VM networking'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
