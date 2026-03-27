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
    if isinstance(t, (list, tuple)):
        return b"%c%s%c" % (
            _TAG_LIST,
            b"".join(_encode_any(x) for x in t),
            _TAG_END,
        )
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


def _decode_everflourish(data: int) -> dict | None:
    """Decode everflourish selflearning raw data.

    Port of molobrakos/tellsticknet/protocols/everflourish.py (MIT licence).
    Ref: telldus-core/service/ProtocolEverflourish.cpp
    """
    house = (data & 0xFFFC00) >> 10
    unit = ((data & 0x300) >> 8) + 1
    method_nib = data & 0xF

    if house > 16383 or not (1 <= unit <= 4):
        return None

    if method_nib == 0:
        method = "turnoff"
    elif method_nib == 15:
        method = "turnon"
    elif method_nib == 10:
        method = "learn"
    else:
        return None

    return dict(
        _class="command", protocol="everflourish", model="selflearning",
        house=house, unit=unit, method=method,
    )


# X10 house code lookup (from telldus-core/service/ProtocolX10.cpp).
# Index is house letter offset (A=0..P=15), value is the 4-bit RF code.
_X10_HOUSES = [6, 0xE, 2, 0xA, 1, 9, 5, 0xD, 7, 0xF, 3, 0xB, 0, 8, 4, 0xC]


def _decode_x10(data: int) -> dict | None:
    """Decode X10 codeswitch raw data.

    Port of telldus-core/service/ProtocolX10.cpp ``decodeData``.
    Test vectors from ProtocolX10Test.cpp:

    >>> _decode_x10(0x609F00FF)
    {'_class': 'command', 'protocol': 'x10', 'model': 'codeswitch', 'house': 'A', 'unit': 1, 'method': 'turnon'}
    >>> _decode_x10(0x847B28D7)
    {'_class': 'command', 'protocol': 'x10', 'model': 'codeswitch', 'house': 'E', 'unit': 11, 'method': 'turnoff'}
    """
    # Extract 4-bit raw house code from bits 31-28 (LSB-first order)
    raw_house = 0
    for i in range(4):
        raw_house >>= 1
        if (data >> (31 - i)) & 1:
            raw_house |= 0x8

    # Bit 27 must be 0
    if (data >> 27) & 1:
        return None

    unit = 0
    # Bit 26 → unit bit 3
    if (data >> 26) & 1:
        unit |= 1 << 3

    # Bits 25, 24 must be 0
    if (data >> 25) & 1 or (data >> 24) & 1:
        return None

    # Skip complement bytes — jump to bit 14
    # Bit 14 → unit bit 2
    if (data >> 14) & 1:
        unit |= 1 << 2
    # Bit 13 → method (0 = turnon, 1 = turnoff)
    method_bit = (data >> 13) & 1
    # Bit 12 → unit bit 0
    if (data >> 12) & 1:
        unit |= 1 << 0
    # Bit 11 → unit bit 1
    if (data >> 11) & 1:
        unit |= 1 << 1

    # Reverse-lookup raw_house → letter A-P
    house_idx = -1
    for idx, code in enumerate(_X10_HOUSES):
        if code == raw_house:
            house_idx = idx
            break
    if house_idx < 0:
        return None

    return dict(
        _class="command", protocol="x10", model="codeswitch",
        house=chr(ord("A") + house_idx), unit=unit + 1,
        method="turnoff" if method_bit else "turnon",
    )


def _decode_hasta(data: int, model: str = "selflearning") -> dict | None:
    """Decode hasta motorised-blind raw data (v1 selflearning + v2 selflearningv2).

    Port of telldus-core/service/ProtocolHasta.cpp ``decodeData``.
    Test vectors from ProtocolHastaTest.cpp:

    >>> _decode_hasta(0xC671100, 'selflearning')
    {'_class': 'command', 'protocol': 'hasta', 'model': 'selflearning', 'house': 26380, 'unit': 1, 'method': 'down'}
    >>> _decode_hasta(0xC670100, 'selflearning')
    {'_class': 'command', 'protocol': 'hasta', 'model': 'selflearning', 'house': 26380, 'unit': 1, 'method': 'up'}
    >>> _decode_hasta(0x4B891F01, 'selflearningv2')
    {'_class': 'command', 'protocol': 'hasta', 'model': 'selflearningv2', 'house': 19337, 'unit': 15, 'method': 'down'}
    >>> _decode_hasta(0x4B89CF01, 'selflearningv2')
    {'_class': 'command', 'protocol': 'hasta', 'model': 'selflearningv2', 'house': 19337, 'unit': 15, 'method': 'up'}
    """
    all_data = data >> 8
    unit = all_data & 0xF
    all_data >>= 4
    method_code = all_data & 0xF
    all_data >>= 4
    house = all_data & 0xFFFF

    is_v2 = model.lower().startswith("selflearningv2")

    if not is_v2:
        # v1: byte-swap house
        house = ((house << 8) | (house >> 8)) & 0xFFFF
        if method_code == 0:
            method = "up"
        elif method_code == 1:
            method = "down"
        elif method_code == 5:
            method = "stop"
        elif method_code == 4:
            method = "learn"
        else:
            return None
        model_str = "selflearning"
    else:
        # v2: no byte-swap
        if method_code == 12:
            method = "up"
        elif method_code in (1, 8):
            method = "down"
        elif method_code == 5:
            method = "stop"
        elif method_code == 4:
            method = "learn"
        else:
            return None
        model_str = "selflearningv2"

    if house < 1 or house > 65535 or unit < 1 or unit > 16:
        return None

    return dict(
        _class="command", protocol="hasta", model=model_str,
        house=house, unit=unit, method=method,
    )


# ---------------------------------------------------------------------------
# Sensor protocol decoders  (ported from molobrakos/tellsticknet/protocols/)
# ---------------------------------------------------------------------------

def _decode_fineoffset_sensor(data: int) -> dict | None:
    """Decode fineoffset temperature/humidity sensor raw data.

    Port of molobrakos/tellsticknet/protocols/fineoffset.py (MIT licence).
    Ref: telldus-core/service/ProtocolFineoffset.cpp

    The ZNet sends fineoffset sensor events as:
      class:sensor, protocol:fineoffset, data:0x48801aff05
    The data integer encodes sensor_id, temperature, and humidity.

    >>> vals = _decode_fineoffset_sensor(0x48801aff05)['values']
    >>> float([v for v in vals if v['name'] == 'temp'][0]['value'])
    2.6
    """
    hex_str = "%010x" % int(data)
    hex_str = hex_str[:-2]  # strip checksum byte

    humidity = int(hex_str[-2:], 16)
    hex_str = hex_str[:-2]

    value = int(hex_str[-3:], 16)
    temp = (value & 0x7FF) / 10
    if (value >> 11) & 1:
        temp = -temp
    temp = round(temp, 1)

    hex_str = hex_str[:-3]
    sensor_id = int(hex_str, 16) & 0xFF

    if humidity <= 100:
        return dict(
            sensorId=sensor_id,
            model="temperaturehumidity",
            values=[
                {"name": "temp", "value": str(temp)},
                {"name": "humidity", "value": str(humidity)},
            ],
        )
    return dict(
        sensorId=sensor_id,
        model="temperature",
        values=[{"name": "temp", "value": str(temp)}],
    )


def _decode_mandolyn_sensor(data: int) -> dict | None:
    """Decode mandolyn/summerbird temperature/humidity sensor raw data.

    Port of molobrakos/tellsticknet/protocols/mandolyn.py (MIT licence).
    Ref: telldus-core/service/ProtocolMandolyn.cpp

    >>> vals = _decode_mandolyn_sensor(0x134039c3)['values']
    >>> float([v for v in vals if v['name'] == 'temp'][0]['value'])
    7.8
    """
    value = int(data) >> 1
    temp = ((value & 0x7FFF) - 6400) / 128
    temp = round(temp, 1)

    value >>= 15
    humidity = value & 0x7F

    value >>= 7
    value >>= 3
    channel = (value & 0x3) + 1

    value >>= 2
    house = value & 0xF

    sensor_id = house * 10 + channel

    result: dict = dict(
        sensorId=sensor_id,
        model="temperaturehumidity",
        values=[
            {"name": "temp", "value": str(temp)},
            {"name": "humidity", "value": str(humidity)},
        ],
    )
    return result


# ---------------------------------------------------------------------------
# Oregon Scientific sensor sub-model decoders
# Port of telldus-core/service/ProtocolOregon.cpp (GPL).
# ZNet model field is the hex model code as a decimal integer:
#   0xEA4C=59980, 0x1A2D=6701, 0xF824=63524, 0x1984=6532,
#   0x1994=6548, 0x2914=10516, 0xC844=51268, 0xEC40=60480
# ---------------------------------------------------------------------------

# Oregon model hex → decimal mapping
_OREGON_EA4C = 0xEA4C  # 59980 — temperature
_OREGON_1A2D = 0x1A2D  # 6701  — temperature + humidity
_OREGON_F824 = 0xF824  # 63524 — temperature + humidity
_OREGON_1984 = 0x1984  # 6532  — wind
_OREGON_1994 = 0x1994  # 6548  — wind (variant)
_OREGON_2914 = 0x2914  # 10516 — rain
_OREGON_C844 = 0xC844  # 51268 — pool thermometer
_OREGON_EC40 = 0xEC40  # 60480 — pool thermometer (variant)


def _decode_oregon_EA4C(data: int) -> dict | None:
    """Decode Oregon EA4C temperature sensor.

    >>> r = _decode_oregon_EA4C(0x004F300245EA4C20)
    >>> r is not None and float([v for v in r['values'] if v['name'] == 'temp'][0]['value']) > -50
    True
    """
    value = data

    checksum = 0xE + 0xA + 0x4 + 0xC
    checksum -= (value & 0xF) * 0x10
    checksum -= 0xA
    checksum &= 0xFF
    value >>= 8

    checksumw = (value >> 4) & 0xF
    neg = bool(value & (1 << 3))
    hundred = value & 3
    checksum = (checksum + (value & 0xF)) & 0xFF
    value >>= 8

    temp2 = value & 0xF
    temp1 = (value >> 4) & 0xF
    checksum = (checksum + temp2 + temp1) & 0xFF
    value >>= 8

    temp3 = (value >> 4) & 0xF
    checksum = (checksum + (value & 0xF) + temp3) & 0xFF
    value >>= 8

    checksum = (checksum + ((value >> 4) & 0xF) + (value & 0xF)) & 0xFF
    address = value & 0xFF
    value >>= 8

    checksum = (checksum + ((value >> 4) & 0xF) + (value & 0xF)) & 0xFF

    if (checksum & 0xF) != checksumw:
        return None

    temperature = ((hundred * 1000) + (temp1 * 100) + (temp2 * 10) + temp3) / 10.0
    if neg:
        temperature = -temperature
    temperature = round(temperature, 1)

    return dict(
        sensorId=address,
        model="EA4C",
        values=[{"name": "temp", "value": str(temperature)}],
    )


def _decode_oregon_1A2D(data: int) -> dict | None:
    """Decode Oregon 1A2D temperature + humidity sensor.

    Port of telldus-core ProtocolOregon::decode1A2D.
    Reference: molobrakos/tellsticknet/protocols/oregon.py (MIT licence).

    >>> r = _decode_oregon_1A2D(0x201F242450443BDD)
    >>> float([v for v in r['values'] if v['name'] == 'temp'][0]['value'])
    24.2
    >>> int([v for v in r['values'] if v['name'] == 'humidity'][0]['value'])
    45
    """
    value = data
    # Skip checksum2 byte
    value >>= 8
    checksum1 = value & 0xFF
    value >>= 8

    checksum = (((value >> 4) & 0xF) + (value & 0xF)) & 0xFF
    hum1 = value & 0xF
    value >>= 8

    checksum = (checksum + ((value >> 4) & 0xF) + (value & 0xF)) & 0xFF
    neg = bool(value & (1 << 3))
    hum2 = (value >> 4) & 0xF
    value >>= 8

    checksum = (checksum + ((value >> 4) & 0xF) + (value & 0xF)) & 0xFF
    temp2 = value & 0xF
    temp1 = (value >> 4) & 0xF
    value >>= 8

    checksum = (checksum + ((value >> 4) & 0xF) + (value & 0xF)) & 0xFF
    temp3 = (value >> 4) & 0xF
    value >>= 8

    checksum = (checksum + ((value >> 4) & 0xF) + (value & 0xF)) & 0xFF
    address = value & 0xFF
    value >>= 8

    checksum = (checksum + ((value >> 4) & 0xF) + (value & 0xF)) & 0xFF
    checksum = (checksum + 0x1 + 0xA + 0x2 + 0xD - 0xA) & 0xFF

    if checksum != checksum1:
        return None

    temperature = ((temp1 * 100) + (temp2 * 10) + temp3) / 10.0
    if neg:
        temperature = -temperature
    temperature = round(temperature, 1)
    humidity = int((hum1 * 10) + hum2)

    return dict(
        sensorId=address,
        model="1A2D",
        values=[
            {"name": "temp", "value": str(temperature)},
            {"name": "humidity", "value": str(humidity)},
        ],
    )


def _decode_oregon_F824(data: int) -> dict | None:
    """Decode Oregon F824 temperature + humidity sensor.

    Port of telldus-core ProtocolOregon::decodeF824.
    """
    value = data

    value >>= 4  # skip crc nibble
    msg_chk1 = value & 0xF
    value >>= 4
    msg_chk2 = value & 0xF
    value >>= 4
    unknown = value & 0xF
    value >>= 4
    hum1 = value & 0xF
    value >>= 4
    hum2 = value & 0xF
    value >>= 4
    neg = value & 0xF
    value >>= 4
    temp1 = value & 0xF
    value >>= 4
    temp2 = value & 0xF
    value >>= 4
    temp3 = value & 0xF
    value >>= 4
    battery = value & 0xF
    value >>= 4
    rollingcode = ((value >> 4) & 0xF) + (value & 0xF)
    checksum = ((value >> 4) & 0xF) + (value & 0xF)
    value >>= 8
    channel = value & 0xF
    checksum += (
        unknown + hum1 + hum2 + neg + temp1 + temp2 + temp3
        + battery + channel + 0xF + 0x8 + 0x2 + 0x4
    )

    if ((checksum >> 4) & 0xF) != msg_chk1 or (checksum & 0xF) != msg_chk2:
        return None

    temperature = ((temp1 * 100) + (temp2 * 10) + temp3) / 10.0
    if neg:
        temperature = -temperature
    temperature = round(temperature, 1)
    humidity = int((hum1 * 10) + hum2)

    return dict(
        sensorId=rollingcode,
        model="F824",
        values=[
            {"name": "temp", "value": str(temperature)},
            {"name": "humidity", "value": str(humidity)},
        ],
    )


def _decode_oregon_1984(data: int, model_code: int) -> dict | None:
    """Decode Oregon 1984/1994 wind sensor.

    Port of telldus-core ProtocolOregon::decode1984.
    """
    value = data

    value >>= 4  # skip crc nibble
    msg_chk1 = value & 0xF
    value >>= 4
    msg_chk2 = value & 0xF
    value >>= 4
    avg1 = value & 0xF
    value >>= 4
    avg2 = value & 0xF
    value >>= 4
    avg3 = value & 0xF
    value >>= 4
    gust1 = value & 0xF
    value >>= 4
    gust2 = value & 0xF
    value >>= 4
    gust3 = value & 0xF
    value >>= 4
    unknown1 = value & 0xF
    value >>= 4
    unknown2 = value & 0xF
    value >>= 4
    direction = value & 0xF
    value >>= 4
    battery = value & 0xF
    value >>= 4
    rollingcode = ((value >> 4) & 0xF) + (value & 0xF)
    checksum = ((value >> 4) & 0xF) + (value & 0xF)
    value >>= 8
    channel = value & 0xF
    checksum += (
        unknown1 + unknown2 + avg1 + avg2 + avg3
        + gust1 + gust2 + gust3 + direction + battery + channel
    )

    if model_code == _OREGON_1984:
        checksum += 0x1 + 0x9 + 0x8 + 0x4
    else:
        checksum += 0x1 + 0x9 + 0x9 + 0x4

    if ((checksum >> 4) & 0xF) != msg_chk1 or (checksum & 0xF) != msg_chk2:
        return None

    avg = ((avg1 * 100) + (avg2 * 10) + avg3) / 10.0
    gust = ((gust1 * 100) + (gust2 * 10) + gust3) / 10.0
    direction_deg = round(22.5 * direction, 1)

    return dict(
        sensorId=rollingcode,
        model="1984",
        values=[
            {"name": "wdir", "value": str(direction_deg)},
            {"name": "wavg", "value": str(round(avg, 1))},
            {"name": "wgust", "value": str(round(gust, 1))},
        ],
    )


def _decode_oregon_2914(data: int) -> dict | None:
    """Decode Oregon 2914 rain sensor.

    Port of telldus-core ProtocolOregon::decode2914.
    """
    value = data

    msg_chk1 = value & 0xF
    value >>= 4
    msg_chk2 = value & 0xF
    value >>= 4
    tot1 = value & 0xF
    value >>= 4
    tot2 = value & 0xF
    value >>= 4
    tot3 = value & 0xF
    value >>= 4
    tot4 = value & 0xF
    value >>= 4
    tot5 = value & 0xF
    value >>= 4
    tot6 = value & 0xF
    value >>= 4
    rate1 = value & 0xF
    value >>= 4
    rate2 = value & 0xF
    value >>= 4
    rate3 = value & 0xF
    value >>= 4
    rate4 = value & 0xF
    value >>= 4
    battery = value & 0xF
    value >>= 4
    rollingcode = ((value >> 4) & 0xF) + (value & 0xF)
    checksum = ((value >> 4) & 0xF) + (value & 0xF)
    value >>= 8
    channel = value & 0xF
    checksum += (
        tot1 + tot2 + tot3 + tot4 + tot5 + tot6
        + rate1 + rate2 + rate3 + rate4
        + battery + channel + 0x2 + 0x9 + 0x1 + 0x4
    )

    if ((checksum >> 4) & 0xF) != msg_chk1 or (checksum & 0xF) != msg_chk2:
        return None

    total = (
        (tot1 * 100000) + (tot2 * 10000) + (tot3 * 1000)
        + (tot4 * 100) + (tot5 * 10) + tot6
    ) / 1000.0 * 25.4
    rate = ((rate1 * 1000) + (rate2 * 100) + (rate3 * 10) + rate4) / 100.0 * 25.4

    return dict(
        sensorId=rollingcode,
        model="2914",
        values=[
            {"name": "rtot", "value": str(round(total, 1))},
            {"name": "rrate", "value": str(round(rate, 1))},
        ],
    )


def _decode_oregon_C844(data: int, model_code: int) -> dict | None:
    """Decode Oregon C844/EC40 pool thermometer.

    Port of telldus-core ProtocolOregon::decodeC844.
    """
    value = data

    msg_chk1 = value & 0xF
    value >>= 4
    msg_chk2 = value & 0xF
    value >>= 4
    neg = value & 0xF
    value >>= 4
    temp1 = value & 0xF
    value >>= 4
    temp2 = value & 0xF
    value >>= 4
    temp3 = value & 0xF
    value >>= 4
    battery = value & 0xF
    value >>= 4
    rollingcode = ((value >> 4) & 0xF) + (value & 0xF)
    checksum = ((value >> 4) & 0xF) + (value & 0xF)
    value >>= 8
    channel = value & 0xF
    checksum += neg + temp1 + temp2 + temp3 + battery + channel

    if model_code == _OREGON_C844:
        checksum += 0xC + 0x8 + 0x4 + 0x4
    else:
        checksum += 0xE + 0xC + 0x4 + 0x0

    if ((checksum >> 4) & 0xF) != msg_chk1 or (checksum & 0xF) != msg_chk2:
        return None

    temperature = ((temp1 * 100) + (temp2 * 10) + temp3) / 10.0
    if neg:
        temperature = -temperature
    temperature = round(temperature, 1)

    return dict(
        sensorId=rollingcode,
        model="C844",
        values=[{"name": "temp", "value": str(temperature)}],
    )


def _decode_oregon_sensor(data: int, model: int | str) -> dict | None:
    """Decode Oregon Scientific sensor raw data.

    Port of telldus-core/service/ProtocolOregon.cpp (GPL).
    ZNet sends model as integer (hex code in decimal, e.g. 0x1A2D = 6701)
    or as hex string (e.g. "0x1A2D").

    Supported sub-models:
      EA4C (59980) — temperature
      1A2D (6701)  — temperature + humidity
      F824 (63524) — temperature + humidity
      1984 (6532)  — wind
      1994 (6548)  — wind (variant)
      2914 (10516) — rain
      C844 (51268) — pool thermometer
      EC40 (60480) — pool thermometer (variant)

    >>> r = _decode_oregon_sensor(0x201F242450443BDD, 6701)
    >>> float([v for v in r['values'] if v['name'] == 'temp'][0]['value'])
    24.2
    >>> int([v for v in r['values'] if v['name'] == 'humidity'][0]['value'])
    45
    """
    # Normalise model to integer
    if isinstance(model, str):
        try:
            model_code = int(model, 0)  # handles "0x1A2D" and "6701"
        except (ValueError, TypeError):
            return None
    else:
        model_code = int(model)

    if model_code == _OREGON_EA4C:
        return _decode_oregon_EA4C(data)
    if model_code == _OREGON_1A2D:
        return _decode_oregon_1A2D(data)
    if model_code == _OREGON_F824:
        return _decode_oregon_F824(data)
    if model_code in (_OREGON_1984, _OREGON_1994):
        return _decode_oregon_1984(data, model_code)
    if model_code == _OREGON_2914:
        return _decode_oregon_2914(data)
    if model_code in (_OREGON_C844, _OREGON_EC40):
        return _decode_oregon_C844(data, model_code)

    _LOGGER.debug(
        "Oregon: unsupported model 0x%X (%d); raw data=0x%X",
        model_code, model_code, data,
    )
    return None


def _decode_sensor_event(packet: dict) -> dict | None:
    """Decode a sensor event's raw data integer into sensor values.

    The ZNet firmware sends sensor events as:
      class:sensor, protocol:fineoffset, data:0x41B03B4DAA
    The raw ``data`` integer must be decoded by protocol-specific decoders.
    If the packet already contains a ``values`` list (e.g. from a future
    firmware version), it is returned as-is.
    """
    # Already decoded (e.g. newer firmware or test fixture)
    values = packet.get("values")
    if values:
        return packet

    data = packet.get("data")
    if not isinstance(data, int):
        _LOGGER.debug("Net sensor: no data integer in packet %s", packet)
        return None

    protocol = packet.get("protocol", "")

    if protocol == "fineoffset":
        decoded = _decode_fineoffset_sensor(data)
    elif protocol == "mandolyn":
        decoded = _decode_mandolyn_sensor(data)
    elif protocol == "oregon":
        decoded = _decode_oregon_sensor(data, packet.get("model", ""))
    else:
        _LOGGER.debug(
            "Net sensor: no decoder for protocol=%s; raw data=0x%X",
            protocol, data,
        )
        return None

    if decoded is None:
        return None

    # Merge decoded fields into the original packet
    result = dict(packet)
    result.update(decoded)
    # Ensure the sensor id is present as "id" (for _event_dict_to_ha_events)
    if "sensorId" in decoded:
        result["id"] = decoded["sensorId"]
    return result


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
    elif protocol == "everflourish":
        decoded = _decode_everflourish(data)
    elif protocol == "x10":
        decoded = _decode_x10(data)
    elif protocol == "hasta":
        decoded = _decode_hasta(data, model)
    else:
        _LOGGER.debug(
            "Net: no decoder for protocol=%s model=%s data=0x%X; skipping event",
            protocol, model, data,
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
    "rrate": 4,      # TELLSTICK_RAINRATE
    "rtot": 8,       # TELLSTICK_RAINTOTAL
    "wdir": 16,      # TELLSTICK_WINDDIRECTION
    "wavg": 32,      # TELLSTICK_WINDAVERAGE
    "wgust": 64,     # TELLSTICK_WINDGUST
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
                # Our own decoders produce: {"name": "temp", "value": "15.6"}
                # ZNet firmware pre-decoded values use: {"type": 1, "value": "15.6"}
                stype_int: int | None = None
                stype_name = entry.get("name", "")
                if stype_name:
                    stype_int = _SENSOR_TYPE_MAP.get(stype_name)
                if stype_int is None:
                    raw_type = entry.get("type")
                    if isinstance(raw_type, int) and raw_type in _SENSOR_TYPE_MAP.values():
                        stype_int = raw_type
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

    Returns an OrderedDict (native firmware dict for on/off/learn), raw bytes
    (dim pulse train), or None if the combination is not supported.
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
#
# The local UDP "send" command is handled differently by each firmware:
#
# - TellStick Net v1 (C firmware, tellsticknet.c): only handles
#   arctech/selflearning natively.  ALL other protocols silently dropped.
#
# - TellStick Net v2 / ZNet (Python firmware, tellstick-server): routes
#   through the full protocol stack, BUT handleSend() has bugs (unit+1
#   offset, limited parameter passthrough, no R/P prefixes).
#
# Raw pulse-train bytes via the "S" key work on ALL versions and bypass
# all firmware dispatch bugs.  Encoding ported from tellstick-server
# ProtocolEverflourish.stringForMethod():
#   https://github.com/telldus/tellstick-server/blob/master/rf433/src/rf433/ProtocolEverflourish.py
#
# See docs/ZNET_PROTOCOL_PORTING_GUIDE.md for full details.
# ---------------------------------------------------------------------------

_EF_SHORT = bytes([60])    # short pulse timing value (= 600 µs @ 10 µs/unit)
_EF_LONG = bytes([114])    # long pulse timing value  (= 1140 µs @ 10 µs/unit)
_EF_ZERO = _EF_SHORT + _EF_SHORT + _EF_SHORT + _EF_LONG    # bit "0"
_EF_ONE = _EF_SHORT + _EF_LONG + _EF_SHORT + _EF_SHORT     # bit "1"

# RF action codes (NOT the same as _METHOD_INT values)
_EF_ACTION_ON = 15
_EF_ACTION_OFF = 0
_EF_ACTION_LEARN = 10


def _everflourish_checksum(x: int) -> int:
    """Calculate everflourish checksum (Frank Stevenson algorithm).

    Ported from telldus-core ProtocolEverflourish::calculateChecksum() and
    tellstick-server ProtocolEverflourish.calculateChecksum().
    """
    bits = [
        0xF, 0xA, 0x7, 0xE,
        0xF, 0xD, 0x9, 0x1,
        0x1, 0x2, 0x4, 0x8,
        0x3, 0x6, 0xC, 0xB,
    ]
    bit = 1
    res = 0x5

    if (x & 0x3) == 3:
        lo = x & 0x00FF
        hi = x & 0xFF00
        lo += 4
        if lo > 0x100:
            lo = 0x12
        x = lo | hi

    for i in range(16):
        if x & bit:
            res = res ^ bits[i]
        bit = bit << 1
    return res


def _everflourish_pulse_train(house: int, unit1: int, action: int) -> bytes:
    """Build raw everflourish pulse-train bytes.

    Ported from tellstick-server ProtocolEverflourish.stringForMethod().
    The unit parameter is 1-indexed (1–4).

    Signal format:
      [preamble: 8×short] [deviceCode: 16 bits] [checksum: 4 bits]
      [action: 4 bits] [terminator: 4×short]
    """
    return _everflourish_pulse_train_ex(
        house, unit1, action,
        short=60, long=114, invert_bits=False, preamble_prefix=b"",
    )


def _everflourish_pulse_train_ex(
    house: int, unit1: int, action: int,
    *, short: int = 60, long: int = 114,
    invert_bits: bool = False,
    preamble_prefix: bytes = b"",
) -> bytes:
    """Build raw everflourish pulse-train bytes with configurable timing.

    Parameters
    ----------
    short, long : int
        Pulse timing byte values (default 60/114 from tellstick-server).
    invert_bits : bool
        If True, swap the bit-0 and bit-1 pulse patterns.
    preamble_prefix : bytes
        Extra bytes prepended before the 8×short preamble (e.g. ``b'\\xff'``
        sync marker like arctech uses).
    """
    s = bytes([short])
    l = bytes([long])  # noqa: E741 (intentionally lowercase L like telldus source)
    zero = s + s + s + l    # bit "0": sssl
    one = s + l + s + s     # bit "1": slss
    if invert_bits:
        zero, one = one, zero
    bits = [zero, one]

    device_code = (house << 2) | (unit1 - 1)
    checksum = _everflourish_checksum(device_code)

    # Preamble: optional prefix + 8 × short pulse
    code = preamble_prefix + s * 8

    # Device code: 16 bits, MSB first
    for i in range(15, -1, -1):
        code += bits[(device_code >> i) & 0x01]

    # Checksum: 4 bits, MSB first
    for i in range(3, -1, -1):
        code += bits[(checksum >> i) & 0x01]

    # Action: 4 bits, MSB first
    for i in range(3, -1, -1):
        code += bits[(action >> i) & 0x01]

    # Terminator: 4 × short pulse
    code += s * 4

    return code


def _encode_everflourish_command(
    house: Any, unit: Any, method_name: str
) -> bytes | None:
    """Return raw pulse-train bytes for an everflourish UDP 'send' command.

    The TellStick Net/ZNet firmware only accepts raw pulse-train bytes via
    the ``S`` key for non-arctech protocols.  Native protocol dicts are
    silently dropped by the firmware.

    Encoding ported from tellstick-server ProtocolEverflourish.stringForMethod().

    >>> _encode_everflourish_command(100, 1, "turnon") is not None
    True
    >>> _encode_everflourish_command(100, 1, "turnoff") is not None
    True
    >>> _encode_everflourish_command(100, 1, "learn") is not None
    True
    >>> _encode_everflourish_command(100, 1, "dim") is None
    True
    >>> len(_encode_everflourish_command(0, 1, "turnon"))
    108
    """
    action_map = {
        "turnon": _EF_ACTION_ON,
        "turnoff": _EF_ACTION_OFF,
        "learn": _EF_ACTION_LEARN,
    }
    action = action_map.get(method_name)
    if action is None:
        return None
    try:
        house_int = max(0, min(16383, int(house)))
    except (TypeError, ValueError):
        _LOGGER.warning("Everflourish: non-integer house %r", house)
        return None
    try:
        unit1 = max(1, min(4, int(unit)))
    except (TypeError, ValueError):
        unit1 = 1
    return _everflourish_pulse_train(house_int, unit1, action)


def _everflourish_pulse_train_ex_preamble(
    house: int, unit1: int, action: int,
    *, preamble_count: int = 8,
    short: int = 60, long: int = 114,
) -> bytes:
    """Build raw everflourish pulse-train bytes with custom preamble length.

    Same as ``_everflourish_pulse_train_ex`` but allows overriding the
    preamble length (number of short pulses).  Standard is 8.
    """
    s = bytes([short])
    l = bytes([long])  # noqa: E741
    zero = s + s + s + l
    one = s + l + s + s
    bits = [zero, one]

    device_code = (house << 2) | (unit1 - 1)
    checksum = _everflourish_checksum(device_code)

    # Preamble: preamble_count × short pulse
    code = s * preamble_count

    # Device code: 16 bits, MSB first
    for i in range(15, -1, -1):
        code += bits[(device_code >> i) & 0x01]

    # Checksum: 4 bits, MSB first
    for i in range(3, -1, -1):
        code += bits[(checksum >> i) & 0x01]

    # Action: 4 bits, MSB first
    for i in range(3, -1, -1):
        code += bits[(action >> i) & 0x01]

    # Terminator: 4 × short pulse
    code += s * 4

    return code


def _encode_everflourish_variant(
    house: Any, unit: Any, method_name: str, model_full: str,
) -> dict[str, Any] | None:
    """Build send_kwargs for an everflourish raw variant.

    Extracts the variant suffix (``ef_v1`` … ``ef_v20``, ``ef_r01`` … ``ef_r140``,
    ``ef_n01`` … ``ef_n123``) from *model_full* and returns the appropriate dict
    to pass to ``encode_packet("send", ...)``.
    Returns ``None`` if the method is unsupported.

    See ``docs/EVERFLOURISH_RESEARCH.md`` for variant descriptions.
    """
    # Build raw pulse bytes (used by S-only and hybrid variants)
    rf_packet = _encode_everflourish_command(house, unit, method_name)
    if rf_packet is None:
        return None

    # Extract variant suffix  (e.g. "selflearning-switch:ef_v3" → "ef_v3")
    variant = ""
    if ":" in model_full:
        variant = model_full.split(":", 1)[1]

    # Resolve numeric house/unit for native dicts
    method_int = _METHOD_INT.get(method_name, 0)
    # Resolve action code for _everflourish_pulse_train_ex (timing variants)
    _ef_action_map = {"turnon": _EF_ACTION_ON, "turnoff": _EF_ACTION_OFF, "learn": _EF_ACTION_LEARN}
    action = _ef_action_map.get(method_name, _EF_ACTION_ON)
    try:
        house_int: Any = int(house)
    except (TypeError, ValueError):
        house_int = 0
    try:
        unit_int = int(unit)
    except (TypeError, ValueError):
        unit_int = 1

    # Clamped values for raw pulse builder
    try:
        house_clamped = max(0, min(16383, int(house)))
    except (TypeError, ValueError):
        house_clamped = 0
    try:
        unit_clamped = max(1, min(4, int(unit)))
    except (TypeError, ValueError):
        unit_clamped = 1

    # ==================================================================
    # LEGACY variants ef_v1..ef_v20 (backward compat)
    # ==================================================================

    # -- Group A: S-only (no protocol key) ----------------------------------
    if variant in ("", "ef_v1"):
        return dict(S=rf_packet)

    if variant == "ef_v2":
        return dict(S=rf_packet, R=4)

    if variant == "ef_v3":
        return dict(S=rf_packet, R=10, P=5)

    if variant == "ef_v4":
        return dict(S=rf_packet + rf_packet)

    # -- Group B: Native dict (firmware encodes internally) -----------------
    if variant == "ef_v5":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )

    if variant == "ef_v6":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int - 1, method=method_int,
        )

    if variant == "ef_v7":
        return OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int, method=method_int,
        )

    if variant == "ef_v8":
        return OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int - 1, method=method_int,
        )

    # -- Group C: Hybrid (native dict + our S bytes) -----------------------
    if variant == "ef_v9":
        d: dict[str, Any] = OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )
        d["S"] = rf_packet
        return d

    if variant == "ef_v10":
        d = OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int - 1, method=method_int,
        )
        d["S"] = rf_packet
        return d

    if variant == "ef_v11":
        d = OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )
        d["S"] = rf_packet
        d["R"] = 4
        d["P"] = 5
        return d

    if variant == "ef_v12":
        return OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int - 2, method=method_int,
        )

    # -- Group D: Timing variations (S-only) --------------------------------
    if variant == "ef_v13":
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=30, long=57,
        )
        return dict(S=pkt)

    if variant == "ef_v14":
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=120, long=228,
        )
        return dict(S=pkt)

    if variant == "ef_v15":
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, invert_bits=True,
        )
        return dict(S=pkt)

    if variant == "ef_v16":
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            preamble_prefix=bytes([60, 1, 1, 60]),
        )
        return dict(S=pkt)

    # -- Group E: Repeat/terminator (S-only) --------------------------------
    if variant == "ef_v17":
        return dict(S=rf_packet, R=5)

    if variant == "ef_v18":
        return dict(S=rf_packet + b"+")

    if variant == "ef_v19":
        return dict(S=rf_packet + b"+", R=5, P=37)

    # -- Group F: Hybrid with repeat ----------------------------------------
    if variant == "ef_v20":
        d = OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int - 1, method=method_int,
        )
        d["S"] = rf_packet
        d["R"] = 5
        return d

    # ==================================================================
    # NEW RAW variants ef_r01..ef_r52 (S-only pulse-train bytes)
    # ==================================================================

    # --- Group RS: Standard timing (60/114), varying repeat count ---
    _rs_repeats = {
        "ef_r01": 1, "ef_r02": 2, "ef_r03": 3, "ef_r04": 4,
        "ef_r05": 5, "ef_r06": 6, "ef_r07": 7, "ef_r08": 8,
        "ef_r09": 9, "ef_r10": 10, "ef_r11": 15, "ef_r12": 20,
    }
    if variant in _rs_repeats:
        return dict(S=rf_packet, R=_rs_repeats[variant])

    # --- Group RT: Timing sweep (all R=5) ---
    _rt_timings: dict[str, tuple[int, int]] = {
        "ef_r13": (30, 57), "ef_r14": (40, 76), "ef_r15": (50, 95),
        "ef_r16": (70, 133), "ef_r17": (80, 152), "ef_r18": (90, 171),
    }
    if variant in _rt_timings:
        s_val, l_val = _rt_timings[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=s_val, long=l_val,
        )
        return dict(S=pkt, R=5)

    # --- Group RP: Preamble length sweep (all R=5) ---
    # We rebuild the pulse train with a custom preamble length
    _rp_lengths: dict[str, int] = {
        "ef_r19": 0, "ef_r20": 2, "ef_r21": 4, "ef_r22": 6,
        "ef_r23": 10, "ef_r24": 12, "ef_r25": 16,
    }
    if variant in _rp_lengths:
        pre_len = _rp_lengths[variant]
        # Build with standard timing but override preamble by manually
        # constructing the pulse train with the desired preamble length.
        pkt = _everflourish_pulse_train_ex_preamble(
            house_clamped, unit_clamped, action, preamble_count=pre_len,
        )
        return dict(S=pkt, R=5)

    # --- Group RD: Double/triple signal copies ---
    _rd_copies: dict[str, tuple[int, int]] = {
        "ef_r26": (2, 1), "ef_r27": (2, 3), "ef_r28": (2, 5),
        "ef_r29": (3, 1), "ef_r30": (3, 3), "ef_r31": (3, 5),
    }
    if variant in _rd_copies:
        copies, r_val = _rd_copies[variant]
        return dict(S=rf_packet * copies, R=r_val)

    # --- Group RF: Frame/terminator combos ---
    _rf_combos: dict[str, tuple[int, bool, int]] = {
        # (R, has_plus_terminator, P)
        "ef_r32": (1, False, 0), "ef_r33": (1, True, 0),
        "ef_r34": (3, False, 0), "ef_r35": (3, True, 0),
        "ef_r36": (3, True, 5), "ef_r37": (5, False, 0),
        "ef_r38": (5, True, 5), "ef_r39": (5, True, 37),
        "ef_r40": (5, False, 37),
    }
    if variant in _rf_combos:
        r_val, has_plus, p_val = _rf_combos[variant]
        s_data = (rf_packet + b"+") if has_plus else rf_packet
        result: dict[str, Any] = dict(S=s_data, R=r_val)
        if p_val:
            result["P"] = p_val
        return result

    # --- Group RI: Inverted bit encoding ---
    _ri_repeats: dict[str, int] = {
        "ef_r41": 1, "ef_r42": 3, "ef_r43": 5,
    }
    if variant in _ri_repeats:
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, invert_bits=True,
        )
        return dict(S=pkt, R=_ri_repeats[variant])

    # --- Group RB: Bit order variations ---
    if variant == "ef_r44":
        # MSB standard (same as normal, explicit for comparison)
        return dict(S=rf_packet, R=5)

    if variant == "ef_r45":
        # LSB reversed — reverse the entire pulse byte sequence
        return dict(S=bytes(reversed(rf_packet)), R=5)

    if variant == "ef_r46":
        # LSB reversed + inverted bits
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, invert_bits=True,
        )
        return dict(S=bytes(reversed(pkt)), R=5)

    # --- Group RX: Cross timing combos (all R=5) ---
    _rx_timings: dict[str, tuple[int, int]] = {
        "ef_r47": (30, 114), "ef_r48": (60, 57),
        "ef_r49": (50, 114), "ef_r50": (60, 95),
        "ef_r51": (40, 133), "ef_r52": (80, 114),
    }
    if variant in _rx_timings:
        s_val, l_val = _rx_timings[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=s_val, long=l_val,
        )
        return dict(S=pkt, R=5)

    # --- Group RRC: RCSwitch protocol timing emulation (ef_r53..ef_r64) ---
    # From RCSwitch.cpp: pulse_length × bit_ratio → short/long bytes
    _rrc_timings: dict[str, tuple[int, int, bool]] = {
        # (short_byte, long_byte, invert_bits)
        "ef_r53": (35, 105, False),   # P1: 350µs base, 1:3 ratio
        "ef_r54": (65, 130, False),   # P2: 650µs base, 1:2 ratio
        "ef_r55": (10, 110, False),   # P3: 100µs base, 4:11 ≈ 1:10
        "ef_r56": (38, 114, False),   # P4: 380µs base, 1:3 ratio
        "ef_r57": (50, 100, False),   # P5: 500µs base, 1:2 ratio
        "ef_r58": (45, 90, True),     # P6: 450µs base, inverted
        "ef_r59": (15, 90, False),    # P7: 150µs base, 1:6 ratio
        "ef_r60": (37, 111, True),    # P10: 365µs, inverted
        "ef_r61": (27, 54, True),     # P11: 270µs, inverted
        "ef_r62": (32, 64, True),     # P12: 320µs, inverted
        "ef_r63": (35, 105, True),    # P1: inverted
        "ef_r64": (38, 114, True),    # P4: inverted
    }
    if variant in _rrc_timings:
        s_val, l_val, inv = _rrc_timings[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=s_val, long=l_val, invert_bits=inv,
        )
        return dict(S=pkt, R=5)

    # --- Group RCP: Castoplug PIC firmware timing (ef_r65..ef_r68) ---
    _rcp_timings: dict[str, tuple[int, int, bool]] = {
        "ef_r65": (40, 101, False),   # 400µs/1010µs
        "ef_r66": (40, 94, False),    # 400µs/940µs
        "ef_r67": (40, 101, True),    # inverted
        "ef_r68": (34, 101, False),   # 340µs/1010µs
    }
    if variant in _rcp_timings:
        s_val, l_val, inv = _rcp_timings[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=s_val, long=l_val, invert_bits=inv,
        )
        return dict(S=pkt, R=5)

    # --- Group RFM: rfcmd forum timing (ef_r69..ef_r72) ---
    _rfm_combos: dict[str, tuple[int, bool]] = {
        "ef_r69": (5, False), "ef_r70": (3, False),
        "ef_r71": (10, False), "ef_r72": (5, True),
    }
    if variant in _rfm_combos:
        r_val, inv = _rfm_combos[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=23, long=69, invert_bits=inv,
        )
        return dict(S=pkt, R=r_val)

    # --- Group RRL: rtl_433 receiver window timing (ef_r73..ef_r76) ---
    _rrl_timings: dict[str, tuple[int, int, int]] = {
        "ef_r73": (100, 200, 5), "ef_r74": (100, 200, 3),
        "ef_r75": (50, 100, 5), "ef_r76": (75, 150, 5),
    }
    if variant in _rrl_timings:
        s_val, l_val, r_val = _rrl_timings[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=s_val, long=l_val,
        )
        return dict(S=pkt, R=r_val)

    # --- Group RDT: Duo format with T-table prefix (ef_r77..ef_r82) ---
    # Duo uses: T table bytes + sync byte prefix before standard pulse train
    _rdt_timings: dict[str, tuple[int, int, int]] = {
        # (short, long, R)
        "ef_r77": (60, 114, 5), "ef_r78": (60, 114, 3),
        "ef_r79": (60, 114, 10),
        "ef_r80": (23, 69, 5),     # rfcmd timing
        "ef_r81": (35, 105, 5),    # RCSwitch P1
        "ef_r82": (40, 101, 5),    # castoplug timing
    }
    if variant in _rdt_timings:
        s_val, l_val, r_val = _rdt_timings[variant]
        # Duo T-table prefix: T + [long, short, 1, 1] + sync(105)
        t_prefix = bytes([ord("T"), l_val, s_val, 1, 1, 105])
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=s_val, long=l_val, preamble_prefix=t_prefix,
        )
        return dict(S=pkt + b"+", R=r_val)

    # --- Group RRT: Ratio sweep, short=60, vary long (ef_r83..ef_r90) ---
    _rrt_timings: dict[str, tuple[int, bool]] = {
        "ef_r83": (90, False), "ef_r84": (120, False),
        "ef_r85": (150, False), "ef_r86": (180, False),
        "ef_r87": (90, True), "ef_r88": (120, True),
        "ef_r89": (150, True), "ef_r90": (180, True),
    }
    if variant in _rrt_timings:
        l_val, inv = _rrt_timings[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=60, long=l_val, invert_bits=inv,
        )
        return dict(S=pkt, R=5)

    # --- Group RAL: Absolute level sweep, ratio≈1.9 (ef_r91..ef_r98) ---
    _ral_timings: dict[str, tuple[int, int]] = {
        "ef_r91": (20, 38), "ef_r92": (25, 48),
        "ef_r93": (35, 67), "ef_r94": (45, 86),
        "ef_r95": (100, 190), "ef_r96": (120, 228),
        "ef_r97": (150, 255), "ef_r98": (75, 143),
    }
    if variant in _ral_timings:
        s_val, l_val = _ral_timings[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=s_val, long=l_val,
        )
        return dict(S=pkt, R=5)

    # --- Group RSY: Sync pulse prefix (ef_r99..ef_r103) ---
    if variant == "ef_r99":
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            preamble_prefix=bytes([255]),
        )
        return dict(S=pkt, R=5)
    if variant == "ef_r100":
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            preamble_prefix=bytes([200]),
        )
        return dict(S=pkt, R=5)
    if variant == "ef_r101":
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            preamble_prefix=bytes([127]),
        )
        return dict(S=pkt, R=5)
    if variant == "ef_r102":
        pkt = _everflourish_pulse_train_ex_preamble(
            house_clamped, unit_clamped, action, preamble_count=4,
        )
        return dict(S=bytes([200]) + pkt, R=5)
    if variant == "ef_r103":
        pkt = _everflourish_pulse_train_ex_preamble(
            house_clamped, unit_clamped, action, preamble_count=0,
        )
        return dict(S=bytes([200]) + pkt, R=5)

    # --- Group RPP: Pause sweep (ef_r104..ef_r110) ---
    _rpp_pauses: dict[str, int] = {
        "ef_r104": 0, "ef_r105": 10, "ef_r106": 20,
        "ef_r107": 37, "ef_r108": 50, "ef_r109": 75, "ef_r110": 100,
    }
    if variant in _rpp_pauses:
        p_val = _rpp_pauses[variant]
        result2: dict[str, Any] = dict(S=rf_packet, R=5)
        if p_val:
            result2["P"] = p_val
        return result2

    # --- Group RFZ: Flipper Zero / Princeton TE=324µs (ef_r111..ef_r116) ---
    # Source: Zero-Sploit/FlipperZero-Subghz-DB EverFlourish/3_ON.sub
    # Protocol: Princeton, TE=324µs → short=32, long=97
    _rfz_combos: dict[str, tuple[int, bool, bool, int]] = {
        # (R, inverted, doubled, extra)
        "ef_r111": (5, False, False, 0), "ef_r112": (3, False, False, 0),
        "ef_r113": (10, False, False, 0), "ef_r114": (5, True, False, 0),
        "ef_r115": (5, False, False, 1),  # +term
        "ef_r116": (5, False, True, 0),   # doubled
    }
    if variant in _rfz_combos:
        r_val, inv, dbl, extra = _rfz_combos[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=32, long=97, invert_bits=inv,
        )
        s_data = (pkt * 2) if dbl else pkt
        if extra == 1:
            s_data = s_data + b"+"
        return dict(S=s_data, R=r_val)

    # --- Group RGR: GNU Radio measured timing (ef_r117..ef_r120) ---
    # Source: alexbirkett/ever-flourish-remote-control-plug USRP N210 capture
    # Long=975µs carrier, short=344µs → short=34, long=98
    _rgr_combos: dict[str, tuple[int, bool, bool]] = {
        "ef_r117": (5, False, False), "ef_r118": (3, False, False),
        "ef_r119": (5, True, False), "ef_r120": (5, False, True),  # +term
    }
    if variant in _rgr_combos:
        r_val, inv, term = _rgr_combos[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=34, long=98, invert_bits=inv,
        )
        s_data = (pkt + b"+") if term else pkt
        return dict(S=s_data, R=r_val)

    # --- Group RES: ESPHome community timing (ef_r121..ef_r124) ---
    # Source: ESPHome community reports, short≈350-400µs, long≈1800µs
    _res_combos: dict[str, tuple[int, int, int, bool]] = {
        "ef_r121": (35, 180, 5, False), "ef_r122": (40, 180, 5, False),
        "ef_r123": (35, 180, 3, False), "ef_r124": (35, 180, 5, True),
    }
    if variant in _res_combos:
        s_val, l_val, r_val, inv = _res_combos[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=s_val, long=l_val, invert_bits=inv,
        )
        return dict(S=pkt, R=r_val)

    # --- Group RCA: Castoplug asymmetric OOK (ef_r125..ef_r127) ---
    # Source: graememorgan/switches-firmware castoplug.c
    # bit0: HIGH 400µs LOW 940µs → zero=(40,94), bit1: HIGH 1005µs LOW 340µs → one=(101,34)
    # This uses *actual* asymmetric OOK, not our standard quartet encoding.
    # We approximate by using short=40 for the "carrier on" and long=94 for "carrier off".
    _rca_repeats: dict[str, int] = {"ef_r125": 5, "ef_r126": 3, "ef_r127": 10}
    if variant in _rca_repeats:
        # Build asymmetric pulse train manually (bit0=short+long, bit1=long+short)
        s = bytes([40])    # 400µs
        l = bytes([94])    # 940µs
        one = bytes([101]) + bytes([34])   # 1005µs carrier + 340µs off
        zero = s + l                       # 400µs carrier + 940µs off
        bits_map = [zero, one]
        device_code = (house_clamped << 2) | (unit_clamped - 1)
        cksum = _everflourish_checksum(device_code)
        code = s * 8  # preamble
        for i in range(15, -1, -1):
            code += bits_map[(device_code >> i) & 0x01]
        for i in range(3, -1, -1):
            code += bits_map[(cksum >> i) & 0x01]
        for i in range(3, -1, -1):
            code += bits_map[(action >> i) & 0x01]
        code += s * 4  # terminator
        return dict(S=code, R=_rca_repeats[variant])

    # --- Group RPR: Princeton TE sweep (ef_r128..ef_r133) ---
    # Flipper uses Princeton encoding — sweep TE base values
    _rpr_te: dict[str, int] = {
        "ef_r128": 25, "ef_r129": 30, "ef_r130": 35,
        "ef_r131": 40, "ef_r132": 45, "ef_r133": 50,
    }
    if variant in _rpr_te:
        te = _rpr_te[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=te, long=te * 3,
        )
        return dict(S=pkt, R=5)

    # --- Group RCO: Cross-source combos (ef_r134..ef_r140) ---
    if variant == "ef_r134":
        # Flipper timing + Duo repeat settings
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=32, long=97,
        )
        return dict(S=pkt, R=5, P=37)
    if variant == "ef_r135":
        # GNU Radio timing + no preamble
        pkt = _everflourish_pulse_train_ex_preamble(
            house_clamped, unit_clamped, action,
            preamble_count=0, short=34, long=98,
        )
        return dict(S=pkt, R=5)
    if variant == "ef_r136":
        # rfcmd short + Flipper 3× ratio
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=23, long=69,
        )
        return dict(S=pkt, R=5)
    if variant == "ef_r137":
        # Flipper timing + Duo T-table prefix
        t_prefix = bytes([ord("T"), 97, 32, 1, 1, 105])
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=32, long=97, preamble_prefix=t_prefix,
        )
        return dict(S=pkt + b"+", R=5)
    if variant == "ef_r138":
        # GNU Radio timing doubled
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=34, long=98,
        )
        return dict(S=pkt * 2, R=3)
    if variant == "ef_r139":
        # ESPHome timing + sync prefix
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            short=35, long=180, preamble_prefix=bytes([200]),
        )
        return dict(S=pkt, R=5)
    if variant == "ef_r140":
        # Castoplug timing + preamble=4
        pkt = _everflourish_pulse_train_ex_preamble(
            house_clamped, unit_clamped, action,
            preamble_count=4, short=40, long=94,
        )
        return dict(S=pkt, R=5)

    # ==================================================================
    # NEW NATIVE variants ef_n01..ef_n53 (firmware protocol dicts)
    # ==================================================================

    # --- Group NM: Model name variations (unit offset 0) ---
    _nm_models: dict[str, str] = {
        "ef_n01": "selflearning-switch", "ef_n02": "selflearning",
        "ef_n03": "selflearning-dimmer", "ef_n04": "switch",
        "ef_n05": "everflourish", "ef_n06": "codeswitch", "ef_n07": "bell",
    }
    if variant in _nm_models:
        return OrderedDict(
            protocol="everflourish", model=_nm_models[variant],
            house=house_int, unit=unit_int, method=method_int,
        )

    # --- Group NU: Unit offsets (model=selflearning-switch) ---
    _nu_offsets: dict[str, int] = {
        "ef_n08": -3, "ef_n09": -2, "ef_n10": -1, "ef_n11": 0,
        "ef_n12": 1, "ef_n13": 2, "ef_n14": 3,
    }
    if variant in _nu_offsets:
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int + _nu_offsets[variant],
            method=method_int,
        )

    # --- Group NU2: Unit offsets (model=selflearning) ---
    _nu2_offsets: dict[str, int] = {
        "ef_n15": -3, "ef_n16": -2, "ef_n17": -1, "ef_n18": 0,
        "ef_n19": 1, "ef_n20": 2, "ef_n21": 3,
    }
    if variant in _nu2_offsets:
        return OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int + _nu2_offsets[variant],
            method=method_int,
        )

    # --- Group NH: House offsets (model=selflearning-switch, unit+0) ---
    _nh_offsets: dict[str, int] = {
        "ef_n22": -2, "ef_n23": -1, "ef_n24": 0,
        "ef_n25": 1, "ef_n26": 2,
    }
    if variant in _nh_offsets:
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int + _nh_offsets[variant], unit=unit_int,
            method=method_int,
        )

    # --- Group NS: Native + S bytes hybrid ---
    _ns_combos: dict[str, tuple[str, int]] = {
        # (model, unit_offset)
        "ef_n27": ("selflearning-switch", 0), "ef_n28": ("selflearning-switch", -1),
        "ef_n29": ("selflearning", 0), "ef_n30": ("selflearning", -1),
        "ef_n31": ("selflearning-dimmer", 0), "ef_n32": ("selflearning-dimmer", -1),
        "ef_n33": ("switch", 0), "ef_n34": ("codeswitch", 0),
    }
    if variant in _ns_combos:
        mdl, u_off = _ns_combos[variant]
        d = OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=unit_int + u_off, method=method_int,
        )
        d["S"] = rf_packet
        return d

    # --- Group NR: Native + R/P repeat values ---
    _nr_combos: dict[str, tuple[int, int | None]] = {
        # (R, P or None)
        "ef_n35": (1, None), "ef_n36": (3, None),
        "ef_n37": (5, None), "ef_n38": (10, None),
        "ef_n39": (1, 5), "ef_n40": (3, 5),
        "ef_n41": (5, 5), "ef_n42": (10, 5),
    }
    if variant in _nr_combos:
        r_val, p_val = _nr_combos[variant]
        d = OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )
        d["R"] = r_val
        if p_val is not None:
            d["P"] = p_val
        return d

    # --- Group NC: Combo (native + S + R) ---
    _nc_combos: dict[str, tuple[str, int, int]] = {
        # (model, unit_offset, R)
        "ef_n43": ("selflearning-switch", 0, 3),
        "ef_n44": ("selflearning-switch", -1, 5),
        "ef_n45": ("selflearning", 0, 5),
        "ef_n46": ("selflearning", -1, 5),
        "ef_n47": ("selflearning-dimmer", 0, 5),
        "ef_n48": ("switch", 0, 3),
    }
    if variant in _nc_combos:
        mdl, u_off, r_val = _nc_combos[variant]
        d = OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=unit_int + u_off, method=method_int,
        )
        d["S"] = rf_packet
        d["R"] = r_val
        return d

    # --- Group NX: Edge cases ---
    if variant == "ef_n49":
        # Method as string 'turnon' instead of int
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_name,
        )

    if variant == "ef_n50":
        # Method=1 (TELLSTICK_TURNON)
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=1,
        )

    if variant == "ef_n51":
        # Method=2 (TELLSTICK_TURNOFF)
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=2,
        )

    if variant == "ef_n52":
        # Method=16 (TELLSTICK_LEARN)
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=16,
        )

    if variant == "ef_n53":
        # Method=0x80 + original int (test high-bit flag)
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=0x80 | method_int,
        )

    # ==================================================================
    # NEW NATIVE variants ef_n54..ef_n108
    # ==================================================================

    # --- Group NRP: Native + RCSwitch/alt timing S bytes (ef_n54..ef_n65) ---
    _nrp_timings: dict[str, tuple[str, int, int, int]] = {
        # (model, unit_offset, short, long)
        "ef_n54": ("selflearning-switch", 0, 35, 105),
        "ef_n55": ("selflearning-switch", 0, 65, 130),
        "ef_n56": ("selflearning-switch", 0, 38, 114),
        "ef_n57": ("selflearning-switch", 0, 50, 100),
        "ef_n58": ("selflearning", -1, 35, 105),
        "ef_n59": ("selflearning", -1, 65, 130),
        "ef_n60": ("selflearning", -1, 38, 114),
        "ef_n61": ("selflearning", -1, 50, 100),
        "ef_n62": ("selflearning-switch", 0, 40, 101),
        "ef_n63": ("selflearning-switch", 0, 23, 69),
        "ef_n64": ("selflearning-switch", 0, 100, 200),
        "ef_n65": ("selflearning-switch", 0, 60, 120),
    }
    if variant in _nrp_timings:
        mdl, u_off, s_val, l_val = _nrp_timings[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=s_val, long=l_val,
        )
        d = OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=unit_int + u_off, method=method_int,
        )
        d["S"] = pkt
        return d

    # --- Group NPC: Protocol name/case variations (ef_n66..ef_n71) ---
    if variant == "ef_n66":
        return OrderedDict(
            protocol="Everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )
    if variant == "ef_n67":
        return OrderedDict(
            protocol="EVERFLOURISH", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )
    if variant == "ef_n68":
        return OrderedDict(
            protocol="everflourish", model="",
            house=house_int, unit=unit_int, method=method_int,
        )
    if variant == "ef_n69":
        d2: dict[str, Any] = OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int, method=method_int,
        )
        d2["code"] = 0
        return d2
    if variant == "ef_n70":
        d2 = OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int, method=method_int,
        )
        d2["system"] = 0
        return d2
    if variant == "ef_n71":
        d2 = OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int, method=method_int,
        )
        d2["fade"] = 0
        return d2

    # --- Group NUE: Extended unit offsets (ef_n72..ef_n79) ---
    _nue_combos: dict[str, tuple[str, Any]] = {
        "ef_n72": ("selflearning-switch", unit_int - 5),
        "ef_n73": ("selflearning-switch", unit_int - 4),
        "ef_n74": ("selflearning-switch", unit_int + 4),
        "ef_n75": ("selflearning-switch", unit_int + 5),
        "ef_n76": ("selflearning-switch", 0),
        "ef_n77": ("selflearning-switch", 255),
        "ef_n78": ("selflearning", 0),
        "ef_n79": ("selflearning", 255),
    }
    if variant in _nue_combos:
        mdl, u_val = _nue_combos[variant]
        return OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=u_val, method=method_int,
        )

    # --- Group NHE: Extended house offsets (ef_n80..ef_n85) ---
    _nhe_combos: dict[str, Any] = {
        "ef_n80": house_int - 5, "ef_n81": house_int - 3,
        "ef_n82": house_int + 3, "ef_n83": house_int + 5,
        "ef_n84": 0, "ef_n85": 16383,
    }
    if variant in _nhe_combos:
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=_nhe_combos[variant], unit=unit_int, method=method_int,
        )

    # --- Group NSR: Native + S + varying R/P (ef_n86..ef_n93) ---
    _nsr_combos: dict[str, tuple[str, int, int, int | None]] = {
        # (model, unit_offset, R, P_or_None)
        "ef_n86": ("selflearning-switch", 0, 1, None),
        "ef_n87": ("selflearning-switch", 0, 3, 5),
        "ef_n88": ("selflearning-switch", 0, 5, 37),
        "ef_n89": ("selflearning-switch", 0, 10, 50),
        "ef_n90": ("selflearning-switch", 0, 15, None),
        "ef_n91": ("selflearning-switch", 0, 20, None),
        "ef_n92": ("selflearning", 0, 5, 100),
        "ef_n93": ("selflearning", 0, 10, 150),
    }
    if variant in _nsr_combos:
        mdl, u_off, r_val, p_val = _nsr_combos[variant]
        d = OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=unit_int + u_off, method=method_int,
        )
        d["S"] = rf_packet
        d["R"] = r_val
        if p_val is not None:
            d["P"] = p_val
        return d

    # --- Group NDU: Native + Duo format S bytes (ef_n94..ef_n97) ---
    _ndu_combos: dict[str, tuple[str, int, int | None]] = {
        # (model, unit_offset, R_or_None)
        "ef_n94": ("selflearning-switch", 0, None),
        "ef_n95": ("selflearning-switch", 0, 5),
        "ef_n96": ("selflearning-switch", -1, None),
        "ef_n97": ("selflearning", 0, None),
    }
    if variant in _ndu_combos:
        mdl, u_off, r_val = _ndu_combos[variant]
        # Duo T-table prefix
        t_prefix = bytes([ord("T"), 114, 60, 1, 1, 105])
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action,
            preamble_prefix=t_prefix,
        )
        d = OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=unit_int + u_off, method=method_int,
        )
        d["S"] = pkt + b"+"
        if r_val is not None:
            d["R"] = r_val
        return d

    # --- Group NMC: Method + model combos (ef_n98..ef_n103) ---
    if variant == "ef_n98":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=15,
        )
    if variant == "ef_n99":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=0,
        )
    if variant == "ef_n100":
        return OrderedDict(
            protocol="everflourish", model="selflearning",
            house=house_int, unit=unit_int, method=10,
        )
    if variant == "ef_n101":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method="on",
        )
    if variant == "ef_n102":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method="off",
        )
    if variant == "ef_n103":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method="learn",
        )

    # --- Group NDD: Dict ordering/type variations (ef_n104..ef_n108) ---
    if variant == "ef_n104":
        # Regular dict instead of OrderedDict
        return dict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )
    if variant == "ef_n105":
        # S key first in dict order
        d3: dict[str, Any] = OrderedDict()
        d3["S"] = rf_packet
        d3["protocol"] = "everflourish"
        d3["model"] = "selflearning-switch"
        d3["house"] = house_int
        d3["unit"] = unit_int
        d3["method"] = method_int
        return d3
    if variant == "ef_n106":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=str(house_int), unit=unit_int, method=method_int,
        )
    if variant == "ef_n107":
        return OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=str(unit_int), method=method_int,
        )
    if variant == "ef_n108":
        return OrderedDict(
            protocol="everflourish", model="selflearning",
            house=str(house_int), unit=str(unit_int), method=method_int,
        )

    # ==================================================================
    # Research-based NATIVE variants ef_n109..ef_n123
    # ==================================================================

    # --- Group NFZ: Native + Flipper Zero Princeton TE=324µs S bytes ---
    # Source: FlipperZero-Subghz-DB EverFlourish capture
    _nfz_combos: dict[str, tuple[str, int, int | None]] = {
        # (model, unit_offset, R_or_None)
        "ef_n109": ("selflearning-switch", 0, None),
        "ef_n110": ("selflearning-switch", -1, None),
        "ef_n111": ("selflearning", 0, None),
        "ef_n112": ("selflearning-switch", 0, 5),
    }
    if variant in _nfz_combos:
        mdl, u_off, r_val = _nfz_combos[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=32, long=97,
        )
        d = OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=unit_int + u_off, method=method_int,
        )
        d["S"] = pkt
        if r_val is not None:
            d["R"] = r_val
        return d

    # --- Group NGR: Native + GNU Radio 344/975µs S bytes ---
    # Source: alexbirkett/ever-flourish-remote-control-plug USRP capture
    _ngr_combos: dict[str, tuple[str, int, int | None]] = {
        "ef_n113": ("selflearning-switch", 0, None),
        "ef_n114": ("selflearning-switch", -1, None),
        "ef_n115": ("selflearning-switch", 0, 5),
    }
    if variant in _ngr_combos:
        mdl, u_off, r_val = _ngr_combos[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=34, long=98,
        )
        d = OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=unit_int + u_off, method=method_int,
        )
        d["S"] = pkt
        if r_val is not None:
            d["R"] = r_val
        return d

    # --- Group NES: Native + ESPHome 350/1800µs S bytes ---
    _nes_combos: dict[str, tuple[str, int]] = {
        "ef_n116": ("selflearning-switch", 0),
        "ef_n117": ("selflearning-switch", -1),
    }
    if variant in _nes_combos:
        mdl, u_off = _nes_combos[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=35, long=180,
        )
        d = OrderedDict(
            protocol="everflourish", model=mdl,
            house=house_int, unit=unit_int + u_off, method=method_int,
        )
        d["S"] = pkt
        return d

    # --- Group NCA: Native + Castoplug asymmetric OOK S bytes ---
    _nca_combos: dict[str, int | None] = {"ef_n118": None, "ef_n119": 5}
    if variant in _nca_combos:
        r_val = _nca_combos[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=40, long=94,
        )
        d = OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )
        d["S"] = pkt
        if r_val is not None:
            d["R"] = r_val
        return d

    # --- Group NPT: Native + Princeton TE sweep S bytes ---
    _npt_te: dict[str, int] = {
        "ef_n120": 25, "ef_n121": 35, "ef_n122": 45, "ef_n123": 50,
    }
    if variant in _npt_te:
        te = _npt_te[variant]
        pkt = _everflourish_pulse_train_ex(
            house_clamped, unit_clamped, action, short=te, long=te * 3,
        )
        d = OrderedDict(
            protocol="everflourish", model="selflearning-switch",
            house=house_int, unit=unit_int, method=method_int,
        )
        d["S"] = pkt
        return d

    # Unknown variant: fall back to S-only
    _LOGGER.warning("Everflourish: unknown variant %r, using S-only", variant)
    return dict(S=rf_packet)


def _encode_generic_command(
    protocol: str, model: str, house: Any, unit: Any, method_name: str,
    *, compensate_unit: bool = True,
) -> dict:
    """Build a generic send dict for protocols handled natively by the ZNet.

    The ZNet v2/ZNet firmware's handleSend() has a unit+1 offset bug::

        protocol.setParameters({'house': msg['house'], 'unit': msg['unit'] + 1})

    This means the firmware adds 1 to the unit we send before passing it to
    the protocol encoder's ``intParameter('unit', ...)``.  When
    *compensate_unit* is True (the default) we subtract 1 from the unit value
    so the protocol encoder receives the correct value.  Set to False to send
    the unit value as-is (useful for testing whether the bug actually applies
    to a given protocol).

    **Limitation:** handleSend() only passes ``house`` and ``unit`` to
    ``setParameters()``.  Protocols that need ``code``, ``system``, ``units``,
    ``fade``, or other parameters will not receive them — those protocols
    require raw pulse-train encoders instead.

    Source: decompiled from ``tellstick-znet-lite-v2-1.3.2.bin`` firmware,
    ``productiontest/Server.py :: CommandHandler.handleSend()``.
    """
    method_int = _METHOD_INT.get(method_name, 0)
    try:
        house_val: Any = int(house)
    except (TypeError, ValueError):
        house_val = str(house)
    try:
        unit_int = int(unit)
        # Compensate for ZNet firmware unit+1 bug when requested.
        unit_val: Any = unit_int - 1 if compensate_unit else unit_int
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

        loop = asyncio.get_running_loop()
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
    _raw_packet_callbacks: list[Callable[[dict], None]] = field(
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
            _LOGGER.info("Net: bound to port %d for %s", NET_COMMAND_PORT, self.host)
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
        _LOGGER.info("Net: sent reglistener to %s:%d", self.host, NET_COMMAND_PORT)

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

    async def reconnect(self) -> None:
        """Re-send reglistener without rebinding the socket.

        Call this after HA has fully started to recover from a lost initial
        registration (e.g. ZNet not reachable during early HAOS boot).
        """
        if self._sock is None:
            return
        try:
            await self._send_raw(encode_packet("reglistener"))
            _LOGGER.info(
                "Net: re-sent reglistener to %s (post-start registration)", self.host
            )
        except OSError as err:
            _LOGGER.warning(
                "Net: post-start registration failed for %s: %s", self.host, err
            )

    def add_callback(self, callback: Callable[[Any], None]) -> None:
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Any], None]) -> None:
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def add_raw_packet_callback(self, callback: Callable[[dict], None]) -> None:
        """Register a callback that receives EVERY decoded packet dict.

        Unlike ``add_callback`` (which only fires for recognised protocol
        events), this fires for every ``7:RawData`` packet received from the
        ZNet — even when the protocol has no decoder.  Useful for debugging.
        """
        self._raw_packet_callbacks.append(callback)

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
        loop = asyncio.get_running_loop()
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
        encoding = device.get("encoding", "")

        if encoding == "native":
            # Explicit native path: always use the firmware's protocol stack.
            # Compensates for the ZNet unit+1 bug.  Works for all protocols
            # but only passes house/unit — code/system/fade are lost.
            send_kwargs: dict[str, Any] = dict(
                _encode_generic_command(protocol, model, house, unit, method_name)
            )
        elif encoding == "native_nofix":
            # Native path WITHOUT unit+1 compensation.  Sends the unit value
            # as-is so the user can test whether the bug actually applies.
            send_kwargs = dict(
                _encode_generic_command(
                    protocol, model, house, unit, method_name,
                    compensate_unit=False,
                )
            )
        elif protocol == "arctech":
            # Arctech-specific encoder (pre-split behaviour, proven stable).
            # Returns native OrderedDict for on/off/learn (with proper model
            # normalisation, letter house codes, 0-indexed unit) and raw
            # pulse-train bytes for dim.
            rf_packet = _encode_arctech_command(model, house, unit, method_name, param)
            if rf_packet is None:
                _LOGGER.warning(
                    "Net arctech: unsupported method=%s model=%s", method_name, model
                )
                return -1
            send_kwargs = (
                dict(S=rf_packet) if isinstance(rf_packet, bytes) else dict(rf_packet)
            )
        elif protocol == "everflourish":
            # Everflourish variant dispatch.  The model suffix (e.g. ":ef_v5")
            # selects the encoding variant.  See _encode_everflourish_variant().
            ef_result = _encode_everflourish_variant(
                house, unit, method_name, model_full,
            )
            if ef_result is None:
                _LOGGER.warning(
                    "Net everflourish: unsupported method=%s", method_name
                )
                return -1
            send_kwargs = ef_result
        else:
            # No protocol-specific encoder: fall through to native firmware
            # path.  Compensates for ZNet unit+1 bug but only passes
            # house/unit — protocols needing code/system/fade may fail.
            # See docs/ZNET_PROTOCOL_PORTING_GUIDE.md for the porting pattern.
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
        loop = asyncio.get_running_loop()
        _LOGGER.info(
            "Net: event listener started for %s (socket bound to port %s)",
            self.host,
            self._sock.getsockname()[1] if self._sock else "?",
        )
        packet_count = 0
        while True:
            try:
                data, (src_ip, _port) = await asyncio.wait_for(
                    loop.sock_recvfrom(self._sock, 4096), timeout=70.0
                )
                if src_ip != self.host:
                    _LOGGER.debug(
                        "Net: ignoring packet from %s (expected %s)", src_ip, self.host
                    )
                    continue
                packet_count += 1
                if packet_count <= 3:
                    _LOGGER.info(
                        "Net: received packet #%d from %s (%d bytes)",
                        packet_count, src_ip, len(data),
                    )
                self._process_packet(data)
            except asyncio.TimeoutError:
                _LOGGER.debug("Net: no packets from %s in 70s (waiting…)", self.host)
                continue
            except asyncio.CancelledError:
                break
            except OSError as err:
                if self._sock is None:
                    # Socket was closed intentionally by disconnect() — stop.
                    break
                # Transient network error (e.g. interface briefly down after
                # HAOS restart).  Retry after a short delay instead of dying
                # permanently, so events resume once the network recovers.
                _LOGGER.warning(
                    "Net event error for %s: %s — retrying in 5s", self.host, err
                )
                await asyncio.sleep(5)
                continue
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Net: packet processing error: %s", err)

    def _process_packet(self, raw: bytes) -> None:
        args = decode_packet(raw)
        if not args:
            _LOGGER.debug("Net: unrecognised packet from %s: %r", self.host, raw[:60])
            return
        event_class = args.get("class", args.get("_class", ""))
        _LOGGER.debug(
            "Net packet: class=%s protocol=%s model=%s data=%s",
            event_class,
            args.get("protocol", "?"),
            args.get("model", "?"),
            hex(args["data"]) if isinstance(args.get("data"), int) else args.get("data", "?"),
        )

        # Fire raw packet callbacks for EVERY decoded packet — even ones
        # with no protocol decoder.  This lets __init__.py fire HA bus events
        # so users can see ALL ZNet traffic in Developer Tools → Events.
        self._dispatch_raw_packet(args)

        if event_class == "sensor":
            # Decode the raw data integer into sensor values
            decoded = _decode_sensor_event(args)
            if decoded is None:
                return
            for ev in _event_dict_to_ha_events(decoded):
                if ev is not None:
                    _LOGGER.debug("Net sensor event: %s", ev)
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

    def _dispatch_raw_packet(self, packet: dict) -> None:
        """Notify raw packet callbacks with the decoded packet dict."""
        for cb in list(self._raw_packet_callbacks):
            try:
                cb(packet)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Net raw packet callback error: %s", exc)
