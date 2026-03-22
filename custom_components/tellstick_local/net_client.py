"""Asyncio UDP client for TellStick Net / TellStick ZNet firmware.

The ZNet firmware exposes a UDP protocol on two ports:

- **Port 30303** -- Device discovery: broadcast b"D" and the device replies
  with a string like "TellStickNet:MAC:code:17" or "TellstickNetV2:MAC:code:1.1.0:uid".

- **Port 42314** -- RF command/event socket:
  - Bind a local UDP socket to port 42314 (SO_REUSEADDR) to receive events.
  - Send "reglistener" to host:42314 to subscribe to RF events.
    The ZNet pushes "7:RawData" packets to all clients bound on port 42314.
  - Send "send" packets to transmit 433 MHz commands via the hardware.
  - Re-register every 10 minutes to keep the subscription alive.

Protocol encoding (hex-length prefix -- different from telldusd's decimal encoding):
  - Strings:  hex(len(s)):text  e.g. "7:arctech", "B:reglistener"
  - Integers: ihex_values       e.g. "i0s", "i144f96s"  (lowercase hex!)
  - Dicts:    h<key-value pairs>s
  - Lists:    l<items>s

Event packets from the ZNet are "7:RawData" packets containing a dict with
the decoded protocol/model and a raw "data" integer.  Protocol-specific
decoders (ported from molobrakos/tellsticknet) extract house, unit, and method
from this raw integer.

Implementation ported from molobrakos/tellsticknet (MIT licence):
  https://github.com/molobrakos/tellsticknet
"""
from __future__ import annotations

import asyncio
import logging
import socket
from collections import OrderedDict
from collections.abc import AsyncGenerator, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from .client import RawDeviceEvent, SensorEvent
from .const import (
    NET_COMMAND_PORT,
    NET_DISCOVERY_PORT,
    NET_REGISTRATION_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol wire-format tags  (molobrakos/tellsticknet/protocol.py)
# ---------------------------------------------------------------------------
_TAG_INTEGER = ord("i")   # b"i"
_TAG_DICT = ord("h")      # b"h"
_TAG_LIST = ord("l")      # b"l"
_TAG_END = ord("s")       # b"s"
_TAG_SEP = ord(":")       # b":"

# Discovery
_SUPPORTED_PRODUCTS = {"TellStickNet", "TellstickNetV2", "TellstickZnet"}
_MIN_TELLSTICKNET_FIRMWARE = 17


# ---------------------------------------------------------------------------
# Encoding (port of molobrakos/tellsticknet/protocol.py)
# ---------------------------------------------------------------------------

def _encode_bytes_value(s: bytes) -> bytes:
    # Firmware LiveMessageToken.toByteArray() uses '%X:%s' (uppercase hex length).
    # The reglistener check is a raw byte comparison: data == 'B:reglistener'.
    # len("reglistener") = 11 = 0xB → must encode as 'B:reglistener', not 'b:reglistener'.
    return b"%X%c%s" % (len(s), _TAG_SEP, s)


def _encode_string(s: str) -> bytes:
    return _encode_bytes_value(s.encode("utf-8"))


def _encode_integer(d: int) -> bytes:
    """Encode integer as i<uppercase_hex>s (firmware LiveMessageToken uses '%X')."""
    return b"%c%X%c" % (_TAG_INTEGER, int(d), _TAG_END)


def _encode_dict(d: dict) -> bytes:
    if not isinstance(d, dict):
        raise ValueError("Expected dict")
    return b"%c%s%c" % (
        _TAG_DICT,
        b"".join(_encode_any(x) for kv in d.items() for x in kv),
        _TAG_END,
    )


def _encode_any(t: Any) -> bytes:
    if isinstance(t, int):
        return _encode_integer(t)
    if isinstance(t, bytes):
        return _encode_bytes_value(t)
    if isinstance(t, str):
        return _encode_string(t)
    if isinstance(t, dict):
        return _encode_dict(t)
    raise NotImplementedError(f"Cannot encode type {type(t)!r}")


def encode_packet(command: str, **args: Any) -> bytes:
    """Encode a ZNet UDP command packet.

    The ZNet firmware uses a strict parser that expects exactly:
      command_string [args_dict]
    with nothing after the dict.  P/R repeat parameters are NOT appended as
    trailing flat pairs -- the released molobrakos 0.1.2 (the reference that
    works with ZNet) does not append them, and ZNet rejects packets with extra
    bytes after the args dict.

    encode_packet("reglistener")  ->  b"B:reglistener"
    encode_packet("hello", foo="x")  ->  b"5:helloh3:foo1:xs"
    """
    res = _encode_string(command)
    if args:
        res += _encode_dict(args)
    return res


# ---------------------------------------------------------------------------
# Decoding (port of molobrakos/tellsticknet/protocol.py)
# ---------------------------------------------------------------------------

def _decode_string(packet: bytes) -> tuple[str, bytes]:
    sep = packet.find(_TAG_SEP)
    if sep <= 0:
        raise ValueError(f"No separator in {packet[:20]!r}")
    length = int(packet[:sep], 16)
    start = sep + 1
    end = start + length
    if end > len(packet):
        raise ValueError("Packet truncated")
    return packet[start:end].decode("utf-8", errors="replace"), packet[end:]


def _decode_integer(packet: bytes) -> tuple[int, bytes]:
    if packet[0] != _TAG_INTEGER:
        raise ValueError("Expected integer tag")
    end = packet.find(_TAG_END, 1)
    if end < 0:
        raise ValueError("Unterminated integer")
    val = int(packet[1:end], 16) if packet[1:end] else 0
    return val, packet[end + 1:]


def _decode_dict(packet: bytes) -> tuple[dict, bytes]:
    rest = packet[1:]
    d: dict = {}
    while rest and rest[0] != _TAG_END:
        k, rest = _decode_any(rest)
        v, rest = _decode_any(rest)
        d[str(k)] = v
    return d, rest[1:] if rest else b""


def _decode_list(packet: bytes) -> tuple[list, bytes]:
    rest = packet[1:]
    items: list = []
    while rest and rest[0] != _TAG_END:
        item, rest = _decode_any(rest)
        items.append(item)
    return items, rest[1:] if rest else b""


def _decode_any(packet: bytes) -> tuple[Any, bytes]:
    if not packet:
        return None, b""
    tag = packet[0]
    if tag == _TAG_INTEGER:
        return _decode_integer(packet)
    if tag == _TAG_DICT:
        return _decode_dict(packet)
    if tag == _TAG_LIST:
        return _decode_list(packet)
    return _decode_string(packet)


def decode_packet(raw: bytes | str) -> dict | None:
    """Decode a ZNet "7:RawData" event packet.

    Returns the inner args dict (containing class, protocol, model, data) or
    None if the packet is not a recognised RF event packet.
    """
    if isinstance(raw, str):
        raw = raw.encode("ascii", errors="replace")
    try:
        command, rest = _decode_any(raw)
        if not rest:
            return None
        args, _ = _decode_any(rest)
    except (ValueError, IndexError, UnicodeDecodeError) as err:
        _LOGGER.debug("Malformed packet %r: %s", raw[:40], err)
        return None

    if command != "RawData" or not isinstance(args, dict):
        return None

    return args


# ---------------------------------------------------------------------------
# Protocol-specific RF event decoders  (ported from molobrakos/protocols/)
# ---------------------------------------------------------------------------

def _decode_arctech_selflearning(data: int) -> dict | None:
    """Decode arctech selflearning raw data int -> house/unit/method."""
    house = (data & 0xFFFFFFC0) >> 6
    group = (data & 0x20) >> 5
    method_bit = (data & 0x10) >> 4
    unit = (data & 0xF) + 1
    if not (1 <= house <= 67108863 and 1 <= unit <= 16):
        return None
    return dict(
        _class="command", house=house, unit=unit,
        group=group, method="turnon" if method_bit else "turnoff",
    )


def _decode_arctech_codeswitch(data: int) -> dict | None:
    """Decode arctech codeswitch raw data int -> house/unit/method."""
    method_nib = (data & 0xF00) >> 8
    unit = ((data & 0xF0) >> 4) + 1
    house_nib = data & 0xF
    if house_nib > 15 or not (1 <= unit <= 16):
        return None
    house = chr(house_nib + ord("A"))
    if method_nib == 6:
        method = "turnoff"
    elif method_nib == 14:
        method = "turnon"
    elif method_nib == 15:
        method = "bell"
    else:
        return None
    return dict(_class="command", house=house, unit=unit, method=method)


def _decode_waveman(data: int) -> dict | None:
    method_nib = (data & 0xF00) >> 8
    unit = ((data & 0xF0) >> 4) + 1
    house_nib = data & 0xF
    if house_nib > 15 or not (1 <= unit <= 16):
        return None
    house = chr(house_nib + ord("A"))
    if method_nib == 0:
        method = "turnoff"
    elif method_nib == 14:
        method = "turnon"
    else:
        return None
    return dict(
        _class="command", protocol="waveman", model="codeswitch",
        house=house, unit=unit, method=method,
    )


def _decode_sartano(data: int) -> dict | None:
    data2 = 0
    mask = 1 << 11
    for _ in range(12):
        data2 >>= 1
        if data & mask == 0:
            data2 |= 1 << 11
        mask >>= 1
    data = data2
    code_int = (data & 0xFFC) >> 2
    method1 = (data & 0x2) >> 1
    method2 = data & 0x1
    if method1 == 0 and method2 == 1:
        method = "turnoff"
    elif method1 == 1 and method2 == 0:
        method = "turnon"
    else:
        return None
    if code_int > 1023:
        return None
    code = "".join("1" if code_int & (1 << (9 - i)) else "0" for i in range(10))
    return dict(
        _class="command", protocol="sartano", model="codeswitch",
        code=code, method=method,
    )


def _decode_rf_event(packet: dict) -> dict | None:
    """Resolve house/unit/method from the raw data integer in the packet."""
    protocol = packet.get("protocol", "")
    model = packet.get("model", "")
    data = packet.get("data")

    if not isinstance(data, int):
        values = packet.get("values")
        if values:
            return packet  # sensor event with pre-decoded values
        return None

    if protocol == "arctech":
        if model == "selflearning":
            decoded = _decode_arctech_selflearning(data)
        elif model in ("codeswitch", "bell", "kp100"):
            decoded = _decode_arctech_codeswitch(data)
            if decoded:
                decoded.update(protocol="arctech", model=model)
        else:
            decoded = None
    elif protocol == "waveman":
        decoded = _decode_waveman(data)
    elif protocol == "sartano":
        decoded = _decode_sartano(data)
    else:
        _LOGGER.debug(
            "Net: no decoder for protocol=%s model=%s; skipping event", protocol, model
        )
        return None

    if decoded is None:
        return None

    result = dict(packet)
    for k, v in decoded.items():
        result[k[1:] if k.startswith("_") else k] = v
    return result


# ---------------------------------------------------------------------------
# Convert decoded RF event dict to HA event objects
# ---------------------------------------------------------------------------

_SENSOR_TYPE_MAP: dict[str, int] = {
    "temp": 1,       # TELLSTICK_TEMPERATURE
    "humidity": 2,   # TELLSTICK_HUMIDITY
}


def _event_dict_to_ha_events(ev: dict) -> Iterator[Any]:
    """Yield RawDeviceEvent or SensorEvent objects from a decoded packet dict."""
    event_class = ev.get("class", ev.get("_class", "command"))

    if event_class == "sensor":
        protocol = ev.get("protocol", "")
        model = ev.get("model", "")
        sensor_id = ev.get("id", 0)
        values = ev.get("values") or []
        if isinstance(values, list):
            for entry in values:
                stype_name = entry.get("name", "")
                stype_int = _SENSOR_TYPE_MAP.get(stype_name)
                if stype_int is not None:
                    try:
                        yield SensorEvent(
                            protocol=protocol,
                            model=model,
                            sensor_id=int(sensor_id),
                            data_type=stype_int,
                            value=str(entry.get("value", "")),
                        )
                    except (TypeError, ValueError):
                        pass
        return

    protocol = ev.get("protocol", "")
    model = ev.get("model", "")
    house = ev.get("house", "")
    unit = ev.get("unit", "")
    code = ev.get("code", "")
    method = ev.get("method", "")

    if not method:
        return

    parts = [f"class:{event_class}"]
    if protocol:
        parts.append(f"protocol:{protocol}")
    if model:
        parts.append(f"model:{model}")
    if house != "":
        parts.append(f"house:{house}")
    if unit != "":
        parts.append(f"unit:{unit}")
    elif code:
        parts.append(f"code:{code}")
    parts.append(f"method:{method}")

    yield RawDeviceEvent(raw=";".join(parts) + ";", controller_id=0)


# ---------------------------------------------------------------------------
# Arctech TX encoding  (port of molobrakos/tellsticknet/protocols/arctech.py)
# ---------------------------------------------------------------------------

_SHORT = bytes([24])
_LONG = bytes([127])
_ONE = _SHORT + _LONG + _SHORT + _SHORT
_ZERO = _SHORT + _SHORT + _SHORT + _LONG

# Method int constants matching molobrakos/tellsticknet/const.py
_TURNON = 1
_TURNOFF = 2
_DIM = 16
_LEARN = 32
_METHOD_INT: dict[str, int] = {
    "turnon": _TURNON, "turnoff": _TURNOFF, "dim": _DIM,
    "learn": _LEARN, "up": 128, "down": 256, "stop": 512, "bell": 4,
}


def _arctech_dim_pulse_train(house: int, unit0: int, level: int) -> bytes:
    """Build raw arctech selflearning dim pulse train (unit is 0-indexed)."""
    code = _SHORT + bytes([255])
    for i in range(25, -1, -1):
        code += _ONE if house & (1 << i) else _ZERO
    code += _ZERO                                 # group bit = 0
    code += _SHORT + _SHORT + _SHORT + _SHORT     # dim indicator
    for i in range(3, -1, -1):
        code += _ONE if unit0 & (1 << i) else _ZERO
    hw_level = int(level) // 16
    for i in range(3, -1, -1):
        code += _ONE if hw_level & (1 << i) else _ZERO
    return code + _SHORT


def _encode_arctech_command(
    model: str, house: Any, unit: Any, method_name: str, param: Any = None
) -> dict | bytes | None:
    """Encode an arctech RF command.

    Returns an OrderedDict (native firmware on/off), raw bytes (dim pulse
    train), or None if the combination is not supported.
    """
    method_int = _METHOD_INT.get(method_name)
    if method_int is None:
        return None

    # codeswitch uses alphabetic house codes (A-P); selflearning uses integers.
    # Try integer conversion first; fall back to passing the value as-is (string)
    # so the ZNet firmware can handle it natively (e.g. house="K" for codeswitch).
    try:
        house_val: Any = int(house)
    except (TypeError, ValueError):
        house_val = str(house)

    try:
        unit0 = max(0, int(unit) - 1)   # 1-indexed -> 0-indexed
    except (TypeError, ValueError):
        unit0 = 0

    # Normalise: TURNON on a dimmer model becomes DIM at full brightness
    if method_int == _TURNON and "dimmer" in str(model).lower():
        method_int = _DIM
        param = 255
    if method_int == _DIM and int(param or 0) == 0:
        method_int = _TURNOFF

    if method_int in (_TURNON, _TURNOFF, _LEARN):
        # For selflearning, model must be "selflearning" (not "selflearning-switch").
        # For codeswitch, bell, kp100 pass the model through as received.
        send_model = "selflearning" if model in ("selflearning", "selflearning-switch", "selflearning-dimmer") else model
        return OrderedDict(
            protocol="arctech",
            model=send_model,
            house=house_val,
            unit=unit0,
            method=method_int,
        )
    if method_int == _DIM:
        if not isinstance(house_val, int):
            _LOGGER.warning("Arctech dim: non-integer house %r (codeswitch cannot dim)", house)
            return None
        return _arctech_dim_pulse_train(house_val, unit0, int(param or 128))
    return None


# ---------------------------------------------------------------------------
# Everflourish TX encoding
# The ZNet firmware has ProtocolEverflourish registered in
# Protocol.protocolInstance() (rf433/src/rf433/Protocol.py).  We send a
# native protocol dict — the same pattern that works for arctech — so the
# ZNet firmware invokes its own ProtocolEverflourish.stringForMethod()
# internally, which is the proven code path.
# ---------------------------------------------------------------------------

def _encode_everflourish_command(
    house: Any, unit: Any, method_name: str
) -> dict | None:
    """Return a native protocol dict for an everflourish UDP 'send' command.

    The ZNet firmware (productiontest/Server.py CommandHandler.handleSend):
      protocol.setModel(msg['model'])               ← 'model' key required
      protocol.setParameters({'house': msg['house'],
                               'unit':  msg['unit'] + 1})  ← firmware adds 1
    ProtocolEverflourish.stringForMethod then does intParameter('unit',1,4)-1.
    So we must send unit 0-indexed (same as arctech) — the firmware +1 makes
    it 1-indexed before the protocol subtracts 1 back to 0-indexed.
    """
    method_int = _METHOD_INT.get(method_name)
    if method_int is None:
        return None
    try:
        house_int = max(0, min(16383, int(house)))
    except (TypeError, ValueError):
        _LOGGER.warning("Everflourish: non-integer house %r", house)
        return None
    try:
        unit0 = max(0, min(3, int(unit) - 1))  # 1-indexed → 0-indexed; firmware adds 1
    except (TypeError, ValueError):
        unit0 = 0
    return OrderedDict(
        protocol="everflourish",
        model="selflearning",   # required: firmware calls msg['model'] → KeyError without it
        house=house_int,
        unit=unit0,
        method=method_int,
    )


def _encode_generic_command(
    protocol: str, model: str, house: Any, unit: Any, method_name: str
) -> dict:
    """Build a generic send dict for protocols handled natively by the ZNet."""
    method_int = _METHOD_INT.get(method_name, 0)
    try:
        house_val: Any = int(house)
    except (TypeError, ValueError):
        house_val = str(house)
    try:
        unit_val: Any = int(unit)
    except (TypeError, ValueError):
        unit_val = str(unit)
    return OrderedDict(
        protocol=protocol, model=model,
        house=house_val, unit=unit_val, method=method_int,
    )


# ---------------------------------------------------------------------------
# UDP discovery  (port of molobrakos/tellsticknet/discovery.py)
# ---------------------------------------------------------------------------

def _parse_discovery_packet(data: bytes) -> tuple[str, str, str] | None:
    """Return (mac, product, firmware) or None if the packet is unrecognised."""
    try:
        text = data.decode("ascii").strip()
    except (UnicodeDecodeError, AttributeError):
        return None
    parts = text.split(":")
    if len(parts) not in (4, 5):
        return None
    product = parts[0]
    if not any(product.startswith(p) for p in _SUPPORTED_PRODUCTS):
        return None
    mac = parts[1] if len(parts) > 1 else ""
    firmware = parts[3] if len(parts) > 3 else ""
    if product == "TellStickNet":
        try:
            if int(firmware) < _MIN_TELLSTICKNET_FIRMWARE:
                return None
        except ValueError:
            pass
    return mac, product, firmware


async def discover(timeout: float = 3.0) -> AsyncGenerator[tuple[str, str, str], None]:
    """Discover TellStick Net/ZNet devices via UDP broadcast on port 30303.

    Yields (ip, mac, product) tuples for each device that replies.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            # Bind to all interfaces (ephemeral port) to receive the UDP unicast
            # reply from the ZNet; the ZNet sends its discovery reply to the
            # source address of the broadcast — binding to "" is required here.
            sock.bind(("", 0))
        except OSError as err:
            _LOGGER.debug("Could not set up discovery socket: %s", err)
            return

        loop = asyncio.get_event_loop()
        try:
            await loop.sock_sendto(sock, b"D", ("<broadcast>", NET_DISCOVERY_PORT))
        except OSError as err:
            _LOGGER.debug("Discovery broadcast failed: %s", err)
            return

        seen: set[str] = set()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                data, (ip, _port) = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 1024), timeout=remaining
                )
                if ip in seen:
                    continue
                parsed = _parse_discovery_packet(data)
                if parsed:
                    mac, product, firmware = parsed
                    seen.add(ip)
                    _LOGGER.info(
                        "Discovered %s at %s (MAC: %s, firmware: %s)",
                        product, ip, mac, firmware,
                    )
                    yield ip, mac, product
            except asyncio.TimeoutError:
                break
            except OSError as err:
                _LOGGER.debug("Discovery receive error: %s", err)
                break


# ---------------------------------------------------------------------------
# TellStick Net UDP controller
# ---------------------------------------------------------------------------

@dataclass
class TellStickNetController:
    """Asyncio UDP controller for TellStick Net / TellStick ZNet.

    Exposes the same public interface as TellStickController (client.py) so
    all downstream platform code (switch, light, cover, sensor, button) is
    backend-agnostic.

    Command methods receive a ``device`` parameter that is a dict:
    ``{protocol, model, house, unit}``.  __init__.py stores these dicts in
    ``device_id_map[uid]`` for Net entries instead of integer telldusd IDs.

    Protocol details:
    - Binds local UDP socket to port 42314 (SO_REUSEADDR) to receive events
      broadcast by the ZNet firmware.
    - Sends "reglistener" on connect() and re-registers every 10 minutes.
    - Incoming "7:RawData" packets are decoded with protocol-specific decoders
      and dispatched as RawDeviceEvent / SensorEvent objects.
    - Arctech selflearning on/off uses native firmware dict encoding.
      Dim uses raw pulse-train bytes (S key), matching molobrakos behaviour.
    """

    host: str
    mac: str = ""

    _sock: socket.socket | None = field(default=None, init=False, repr=False)
    _event_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _reregister_task: asyncio.Task | None = field(
        default=None, init=False, repr=False
    )
    _callbacks: list[Callable[[Any], None]] = field(
        default_factory=list, init=False, repr=False
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Bind UDP socket to port 42314 and send initial reglistener."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        try:
            # Bind to all interfaces on port 42314 (SO_REUSEADDR).
            # The ZNet firmware broadcasts RF events to port 42314 on the local
            # network — binding to a single interface would miss them.
            # This matches the molobrakos/tellsticknet reference implementation.
            sock.bind(("", NET_COMMAND_PORT))
        except OSError:
            _LOGGER.warning(
                "Port %d already bound; using ephemeral port for %s",
                NET_COMMAND_PORT, self.host,
            )
            # Fall back to an ephemeral port if 42314 is in use (e.g. a second
            # Net entry is already bound).  The reglistener packet we send will
            # tell the ZNet to direct future events to our ephemeral port.
            sock.bind(("", 0))
        self._sock = sock
        await self._send_raw(encode_packet("reglistener"))

    async def disconnect(self) -> None:
        """Cancel tasks and close the socket."""
        for task in (self._event_task, self._reregister_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._event_task = None
        self._reregister_task = None
        if self._sock:
            self._sock.close()
            self._sock = None

    def start_event_listener(self) -> None:
        """Start the UDP event loop and re-registration heartbeat."""
        self._event_task = asyncio.ensure_future(self._event_loop())
        self._reregister_task = asyncio.ensure_future(self._reregister_loop())

    def add_callback(self, callback: Callable[[Any], None]) -> None:
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Any], None]) -> None:
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # RF commands (same names as TellStickController)
    # ------------------------------------------------------------------

    async def turn_on(self, device: Any) -> int:
        return await self._send_rf(device, "turnon")

    async def turn_off(self, device: Any) -> int:
        return await self._send_rf(device, "turnoff")

    async def dim(self, device: Any, level: int) -> int:
        return await self._send_rf(device, "dim", param=level)

    async def up(self, device: Any) -> int:
        return await self._send_rf(device, "up")

    async def down(self, device: Any) -> int:
        return await self._send_rf(device, "down")

    async def stop(self, device: Any) -> int:
        return await self._send_rf(device, "stop")

    async def learn(self, device: Any) -> int:
        return await self._send_rf(device, "learn")

    async def ping(self) -> bool:
        try:
            await self._send_raw(encode_packet("reglistener"))
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Stubs for Duo-only telldusd registry methods
    # ------------------------------------------------------------------

    async def add_device(self, *_a: Any, **_k: Any) -> int:
        return 0

    async def remove_device(self, _d: Any) -> None:
        pass

    async def list_devices(self) -> list[dict[str, Any]]:
        return []

    async def find_or_add_device(self, *_a: Any, **_k: Any) -> int:
        return 0

    async def get_device_name_model(self, _id: int) -> tuple[str, str]:
        return "", ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send_raw(self, data: bytes) -> None:
        if self._sock is None:
            raise OSError("Socket not connected")
        loop = asyncio.get_event_loop()
        await loop.sock_sendto(self._sock, data, (self.host, NET_COMMAND_PORT))

    async def _send_rf(
        self, device: Any, method_name: str, param: Any = None
    ) -> int:
        if not isinstance(device, dict):
            _LOGGER.warning(
                "Net: expected device dict, got %r (%r)", type(device), device
            )
            return -1

        _LOGGER.debug(
            "Net _send_rf called: method=%s device=%r sock=%s",
            method_name, device, "OK" if self._sock else "NONE",
        )

        protocol = device.get("protocol", "")
        model_full = device.get("model", "")
        model = model_full.split(":")[0] if ":" in model_full else model_full
        house = device.get("house", "0")
        unit = device.get("unit", "0")

        if protocol == "arctech":
            rf_packet = _encode_arctech_command(model, house, unit, method_name, param)
            if rf_packet is None:
                _LOGGER.warning(
                    "Net arctech: unsupported method=%s model=%s", method_name, model
                )
                return -1
            send_kwargs: dict[str, Any] = (
                dict(S=rf_packet) if isinstance(rf_packet, bytes) else dict(rf_packet)
            )
        elif protocol == "everflourish":
            rf_packet = _encode_everflourish_command(house, unit, method_name)
            if rf_packet is None:
                _LOGGER.warning(
                    "Net everflourish: unsupported method=%s", method_name
                )
                return -1
            send_kwargs = dict(rf_packet)
        else:
            send_kwargs = dict(
                _encode_generic_command(protocol, model, house, unit, method_name)
            )

        try:
            await self._send_raw(encode_packet("send", **send_kwargs))
            _LOGGER.debug(
                "Net send: %s %s/%s h=%s u=%s",
                method_name, protocol, model, house, unit,
            )
            return 0
        except OSError as err:
            _LOGGER.error("Net: send to %s failed: %s", self.host, err)
            return -1

    async def _event_loop(self) -> None:
        if self._sock is None:
            return
        loop = asyncio.get_event_loop()
        while True:
            try:
                data, (src_ip, _port) = await asyncio.wait_for(
                    loop.sock_recvfrom(self._sock, 4096), timeout=70.0
                )
                if src_ip != self.host:
                    continue
                self._process_packet(data)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except OSError as err:
                _LOGGER.warning("Net event error for %s: %s", self.host, err)
                break
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Net: packet processing error: %s", err)

    def _process_packet(self, raw: bytes) -> None:
        args = decode_packet(raw)
        if not args:
            return
        event_class = args.get("class", args.get("_class", ""))
        if event_class == "sensor":
            for ev in _event_dict_to_ha_events(args):
                if ev is not None:
                    self._dispatch(ev)
            return
        decoded = _decode_rf_event(args)
        if decoded is None:
            return
        for ev in _event_dict_to_ha_events(decoded):
            if ev is not None:
                _LOGGER.debug("Net RF event: %s", getattr(ev, "raw", ev))
                self._dispatch(ev)

    async def _reregister_loop(self) -> None:
        interval = NET_REGISTRATION_INTERVAL_MINUTES * 60
        while True:
            try:
                await asyncio.sleep(interval)
                await self._send_raw(encode_packet("reglistener"))
                _LOGGER.debug("Net: re-registered at %s", self.host)
            except asyncio.CancelledError:
                break
            except OSError as err:
                _LOGGER.warning("Net: re-register failed %s: %s", self.host, err)

    def _dispatch(self, event: Any) -> None:
        for cb in list(self._callbacks):
            try:
                cb(event)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Net callback error: %s", exc)
