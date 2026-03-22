"""TellStick Net/ZNet firmware protocol codec.

This module handles the UDP wire protocol used by TellStick Net and TellStick
ZNet (firmware versions 17+) when communicating *locally*, without the Telldus
Live cloud service.

Wire protocol
-------------
The on-wire encoding is **not** the same as the telldusd text protocol used by
``client.py``.  Key differences:

* String lengths are encoded in **hexadecimal** (e.g. ``A:hellothere`` for a
  10-character string), whereas telldusd uses decimal.
* Integer values are encoded in **hexadecimal** as well (``i2as`` = 42 decimal).
* The overall framing tags (``h``/``i``/``l``/``s``) are the same.

Sources (Apache-2.0 licensed, used with attribution):
  https://github.com/molobrakos/tellsticknet
  https://developer.telldus.com/doxygen/html/TellStickNet.html

RF decoders
-----------
The firmware identifies the RF protocol (e.g. "arctech") and sends raw bit data.
We extract house/unit/method from the bit pattern using the same decoder logic
as telldus-core.  Decoders included:

* arctech – selflearning (nexa), codeswitch (nexa/waveman), sartano
* fineoffset  – Nexa LMST-606/WDS-100 thermometers
* oregon      – Oregon Scientific weather sensors (model 6701)
* mandolyn    – Mandolyn/Summerbird IVT thermometers
* everflourish – GAO selflearning switches

Command encoding
----------------
For arctech selflearning on/off the firmware has native support; we send a
structured dict.  For dim we fall back to raw pulse encoding.  Other protocols
are not yet implemented (most Net/ZNet users use arctech selflearning).
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

from .client import RawDeviceEvent, SensorEvent

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wire protocol: hex-length strings, hex integers
# ---------------------------------------------------------------------------

_TAG_INT = ord("i")
_TAG_DICT = ord("h")
_TAG_LIST = ord("l")
_TAG_END = ord("s")
_TAG_SEP = ord(":")

# Net/ZNet firmware repeats each RF transmission this many times with this
# inter-packet delay (milliseconds).
_CMD_REPEAT_RF_TIMES = 4
_CMD_REPEAT_RF_DELAY = 10


def _enc_bytes(s: bytes) -> bytes:
    return b"%X:%s" % (len(s), s)


def _enc_str(s: str) -> bytes:
    return _enc_bytes(s.encode("ascii", errors="replace"))


def _enc_int(d: int) -> bytes:
    # Hex integer; handle negative values
    if d < 0:
        return b"i-%xs" % (-d,)
    return b"i%xs" % (d,)


def _enc_dict(d: dict) -> bytes:
    inner = b"".join(_enc_any(k) + _enc_any(v) for k, v in d.items())
    return b"h" + inner + b"s"


def _enc_any(v: Any) -> bytes:
    if isinstance(v, bool):
        return _enc_int(int(v))
    if isinstance(v, int):
        return _enc_int(v)
    if isinstance(v, bytes):
        return _enc_bytes(v)
    if isinstance(v, str):
        return _enc_str(v)
    if isinstance(v, dict):
        return _enc_dict(v)
    if isinstance(v, (list, tuple)):
        inner = b"".join(_enc_any(x) for x in v)
        return b"l" + inner + b"s"
    raise NotImplementedError(f"Cannot encode type {type(v)!r}")


def build_packet(command: str, **args: Any) -> bytes:
    """Build a command packet ready to send via UDP to the Net/ZNet firmware."""
    result = _enc_str(command)
    if args:
        result += _enc_dict(args)
    if command == "send":
        result += _enc_str("P") + _enc_int(_CMD_REPEAT_RF_DELAY)
        result += _enc_str("R") + _enc_int(_CMD_REPEAT_RF_TIMES)
    return result


def _dec_str(packet: bytes) -> tuple[str, bytes]:
    sep = packet.find(_TAG_SEP)
    if sep <= 0:
        raise ValueError(f"Expected hex-length prefix, got {packet[:4]!r}")
    length = int(packet[:sep], 16)
    start = sep + 1
    end = start + length
    if end > len(packet):
        raise ValueError("Packet too short for declared string length")
    return packet[start:end].decode("ascii", errors="replace"), packet[end:]


def _dec_int(packet: bytes) -> tuple[int, bytes]:
    if packet[0] != _TAG_INT:
        raise ValueError(f"Expected 'i', got {chr(packet[0])!r}")
    end = packet.find(_TAG_END, 1)
    if end < 0:
        raise ValueError("Integer not terminated by 's'")
    raw = packet[1:end]
    if raw == b"-0":
        return 0, packet[end + 1:]
    negative = raw.startswith(b"-")
    hex_part = raw[1:] if negative else raw
    value = int(hex_part, 16)
    return (-value if negative else value), packet[end + 1:]


def _dec_dict(packet: bytes) -> tuple[dict, bytes]:
    rest = packet[1:]  # skip 'h'
    result: dict = {}
    while rest and rest[0] != _TAG_END:
        k, rest = _dec_any(rest)
        v, rest = _dec_any(rest)
        result[k] = v
    return result, rest[1:]  # skip 's'


def _dec_list(packet: bytes) -> tuple[list, bytes]:
    rest = packet[1:]  # skip 'l'
    items: list = []
    while rest and rest[0] != _TAG_END:
        item, rest = _dec_any(rest)
        items.append(item)
    return items, rest[1:]  # skip 's'


def _dec_any(packet: bytes) -> tuple[Any, bytes]:
    if not packet:
        raise ValueError("Empty packet")
    tag = packet[0]
    if tag == _TAG_INT:
        return _dec_int(packet)
    if tag == _TAG_DICT:
        return _dec_dict(packet)
    if tag == _TAG_LIST:
        return _dec_list(packet)
    # Assume hex-length string
    return _dec_str(packet)


def decode_packet(raw: bytes | str) -> dict | None:
    """Decode a raw UDP datagram from the TellStick Net/ZNet firmware.

    Returns a normalised RF event dict or ``None`` on failure or unsupported
    command type.  The returned dict always has a ``"class"`` key
    (``"command"`` or ``"sensor"``).
    """
    if isinstance(raw, str):
        raw = raw.encode("ascii", errors="replace")
    try:
        command, rest = _dec_any(raw)
        args, _ = _dec_any(rest)
    except (ValueError, IndexError, UnicodeDecodeError) as exc:
        _LOGGER.debug("Could not decode Net/ZNet packet %r: %s", raw[:40], exc)
        return None

    if command != "RawData":
        _LOGGER.debug("Unknown Net/ZNet command %r, ignoring", command)
        return None

    if not isinstance(args, dict):
        return None

    protocol = str(args.get("protocol", ""))
    model = args.get("model", "")
    data = args.get("data", 0)
    cls = str(args.get("class", "command"))

    # Newer firmware format: pre-decoded "values" list
    # e.g. {protocol, id, values: [{scale, type, value}], model, class: sensor}
    values = args.get("values")
    if values and isinstance(values, list):
        return {
            "class": "sensor",
            "protocol": protocol,
            "model": str(model),
            "sensorId": int(args.get("id", 0)),
            "values": values,
        }

    try:
        decoded = _decode_rf(protocol, str(model), data, cls)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug(
            "RF decode failed for protocol=%r model=%r: %s", protocol, model, exc
        )
        return None

    if decoded is None:
        return None

    # Normalise the _class convention from protocol decoders
    if "_class" in decoded:
        decoded["class"] = decoded.pop("_class")

    # Convert data dict → list-of-{name, value} (internal format)
    raw_data = decoded.get("data")
    if isinstance(raw_data, dict):
        decoded["data"] = [{"name": k, "value": v} for k, v in raw_data.items()]

    return decoded


# ---------------------------------------------------------------------------
# RF protocol decoders
# Sources: telldus-core ProtocolNexa.cpp, ProtocolWaveman.cpp,
#          ProtocolSartano.cpp, ProtocolFineoffset.cpp, ProtocolOregon.cpp,
#          ProtocolMandolyn.cpp, ProtocolEverflourish.cpp
# ---------------------------------------------------------------------------

def _decode_rf(protocol: str, model: str, data: Any, cls: str) -> dict | None:
    """Dispatch to the correct RF decoder for the given protocol."""
    base: dict = {"protocol": protocol, "model": model, "data": data, "class": cls}
    if protocol == "arctech":
        return _decode_arctech(base)
    if protocol == "fineoffset":
        return _decode_fineoffset(base)
    if protocol == "oregon":
        return _decode_oregon(base)
    if protocol == "mandolyn":
        return _decode_mandolyn(base)
    if protocol == "everflourish":
        return _decode_everflourish(base)
    _LOGGER.debug("No Net/ZNet decoder for protocol %r", protocol)
    return None


def _decode_arctech(packet: dict) -> dict | None:
    """Try each arctech sub-decoder in order (selflearning, codeswitch, waveman, sartano)."""
    return (
        _decode_nexa_selflearning(packet)
        or _decode_nexa_codeswitch(packet)
        or _decode_waveman(packet)
        or _decode_sartano(packet)
    )


def _decode_nexa_selflearning(packet: dict) -> dict | None:
    """Decode arctech / selflearning."""
    if str(packet.get("model", "")) != "selflearning":
        return None
    data = int(packet["data"])
    house = (data & 0xFFFFFFC0) >> 6
    group = (data & 0x20) >> 5
    method_bit = (data & 0x10) >> 4
    unit = (data & 0xF) + 1
    if not (1 <= house <= 67108863) or not (1 <= unit <= 16):
        return None
    return dict(
        packet,
        _class="command",
        house=house,
        unit=unit,
        group=group,
        method="turnon" if method_bit == 1 else "turnoff",
    )


# Module-level state for arctech codeswitch turn-off debounce (mirrors
# telldus-core ProtocolNexa.cpp static variable).
_codeswitch_last_was_off: bool = False


def _decode_nexa_codeswitch(packet: dict) -> dict | None:
    """Decode arctech / codeswitch."""
    global _codeswitch_last_was_off
    if str(packet.get("model", "")) != "codeswitch":
        return None
    data = int(packet["data"])
    method_nibble = (data & 0xF00) >> 8
    unit = ((data & 0xF0) >> 4) + 1
    house_nibble = data & 0xF
    if house_nibble > 16 or not (1 <= unit <= 16):
        return None
    house = chr(house_nibble + ord("A"))
    if method_nibble != 6 and _codeswitch_last_was_off:
        _codeswitch_last_was_off = False
        return None
    if method_nibble == 6:
        _codeswitch_last_was_off = True
    base = dict(packet, _class="command", protocol="arctech", model="codeswitch", house=house)
    if method_nibble == 6:
        return {**base, "unit": unit, "method": "turnoff"}
    if method_nibble == 14:
        return {**base, "unit": unit, "method": "turnon"}
    if method_nibble == 15:
        return {**base, "method": "bell"}
    return None


_waveman_last_was_off: bool = False


def _decode_waveman(packet: dict) -> dict | None:
    """Decode waveman / codeswitch (old arctech family)."""
    global _waveman_last_was_off
    data = int(packet["data"])
    method_nibble = (data & 0xF00) >> 8
    unit = ((data & 0xF0) >> 4) + 1
    house_nibble = data & 0xF
    if house_nibble > 16 or not (1 <= unit <= 16):
        return None
    house = chr(house_nibble + ord("A"))
    if method_nibble != 6 and _waveman_last_was_off:
        _waveman_last_was_off = False
        return None
    if method_nibble == 6:
        _waveman_last_was_off = True
    base = dict(packet, _class="command", protocol="waveman", model="codeswitch", house=house)
    if method_nibble == 0:
        return {**base, "unit": unit, "method": "turnoff"}
    if method_nibble == 14:
        return {**base, "unit": unit, "method": "turnon"}
    return None


def _decode_sartano(packet: dict) -> dict | None:
    """Decode sartano / codeswitch."""
    data = int(packet["data"])
    # Bit-reverse the 12-bit field
    data2 = 0
    mask = 1 << 11
    for _ in range(12):
        data2 >>= 1
        if data & mask == 0:
            data2 |= 1 << 11
        mask >>= 1
    data = data2
    code_int = (data & 0xFFC) >> 2
    m1 = (data & 0x2) >> 1
    m2 = data & 0x1
    if m1 == 0 and m2 == 1:
        method = "turnoff"
    elif m1 == 1 and m2 == 0:
        method = "turnon"
    else:
        return None
    if code_int > 1023:
        return None
    code_str = "".join(
        "1" if (code_int & (1 << (9 - i))) else "0" for i in range(10)
    )
    return dict(
        packet,
        _class="command",
        protocol="sartano",
        model="codeswitch",
        code=code_str,
        method=method,
    )


def _decode_fineoffset(packet: dict) -> dict | None:
    """Decode fineoffset temperature/humidity (Nexa LMST-606/WDS-100 etc.)."""
    raw_hex = "%010x" % int(packet["data"])
    raw_hex = raw_hex[:-2]
    humidity = int(raw_hex[-2:], 16)
    raw_hex = raw_hex[:-2]
    tmp = int(raw_hex[-3:], 16)
    temp = (tmp & 0x7FF) / 10.0
    if tmp >> 11 & 1:
        temp = -temp
    raw_hex = raw_hex[:-3]
    sensor_id = int(raw_hex, 16) & 0xFF
    if humidity <= 100:
        return dict(
            packet,
            _class="sensor",
            model="temperaturehumidity",
            sensorId=sensor_id,
            data={"humidity": humidity, "temp": temp},
        )
    return dict(
        packet,
        _class="sensor",
        model="temperature",
        sensorId=sensor_id,
        data={"temp": temp},
    )


def _decode_oregon(packet: dict) -> dict | None:
    """Decode Oregon Scientific weather sensor.  Only model 6701 supported."""
    model = packet.get("model")
    if model != 6701:
        _LOGGER.debug("Oregon model %r not supported (only 6701)", model)
        return None
    data = int(packet["data"])
    v = data >> 8
    checksum1 = v & 0xFF
    v >>= 8
    chk = ((v >> 4) & 0xF) + (v & 0xF)
    hum1 = v & 0xF
    v >>= 8
    chk += ((v >> 4) & 0xF) + (v & 0xF)
    neg = v & (1 << 3)
    hum2 = (v >> 4) & 0xF
    v >>= 8
    chk += ((v >> 4) & 0xF) + (v & 0xF)
    temp2 = v & 0xF
    temp1 = (v >> 4) & 0xF
    v >>= 8
    chk += ((v >> 4) & 0xF) + (v & 0xF)
    temp3 = (v >> 4) & 0xF
    v >>= 8
    chk += ((v >> 4) & 0xF) + (v & 0xF)
    address = v & 0xFF
    v >>= 8
    chk += ((v >> 4) & 0xF) + (v & 0xF)
    chk += 0x1 + 0xA + 0x2 + 0xD - 0xA
    if chk != checksum1:
        _LOGGER.debug("Oregon checksum mismatch %d != %d", chk, checksum1)
        return None
    temperature = ((temp1 * 100) + (temp2 * 10) + temp3) / 10.0
    if neg:
        temperature = -temperature
    humidity = hum1 * 10.0 + hum2
    return dict(
        packet,
        _class="sensor",
        model="temperaturehumidity",
        sensorId=address,
        data={"temp": temperature, "humidity": humidity},
    )


def _decode_mandolyn(packet: dict) -> dict | None:
    """Decode mandolyn / summerbird IVT temperature+humidity sensor."""
    data = int(packet["data"])
    v = data >> 1
    temp = round(((v & 0x7FFF) - 6400) / 128.0, 1)
    v >>= 15
    humidity = v & 0x7F
    v >>= 7
    v >>= 3
    channel = (v & 0x3) + 1
    v >>= 2
    house = v & 0xF
    return dict(
        packet,
        _class="sensor",
        model="temperaturehumidity",
        sensorId=house * 10 + channel,
        data={"temp": temp, "humidity": humidity},
    )


def _decode_everflourish(packet: dict) -> dict | None:
    """Decode everflourish selflearning switch (GAO brand)."""
    data = int(packet["data"])
    house = (data >> 6) & 0x3FFF
    method_bit = (data >> 5) & 0x1
    unit = (data & 0xF) + 1
    if not (1 <= house <= 16383):
        return None
    return dict(
        packet,
        _class="command",
        protocol="everflourish",
        model="selflearning",
        house=house,
        unit=unit,
        method="turnon" if method_bit else "turnoff",
    )


# ---------------------------------------------------------------------------
# Conversion: decoded packet dict → our event dataclasses
# ---------------------------------------------------------------------------

# Sensor data name (from fineoffset/oregon/mandolyn decode) → telldusd data-type int
_DATA_NAME_TO_TYPE: dict[str, int] = {
    "temp": 1,       # TELLSTICK_TEMPERATURE
    "humidity": 2,   # TELLSTICK_HUMIDITY
    "rrate": 4,      # TELLSTICK_RAINRATE
    "rtot": 8,       # TELLSTICK_RAINTOTAL
    "wdir": 16,      # TELLSTICK_WINDDIRECTION
    "wavg": 32,      # TELLSTICK_WINDAVERAGE
    "wgust": 64,     # TELLSTICK_WINDGUST
}

# Newer firmware "type" integer → telldusd data-type int
_FIRMWARE_TYPE_TO_TYPE: dict[int, int] = {
    1: 1,   # temperature
    2: 2,   # humidity
    4: 4,   # rain rate
    8: 8,   # rain total
    16: 16, # wind direction
    32: 32, # wind avg
    64: 64, # wind gust
}


def decoded_to_events(
    decoded: dict,
) -> list[RawDeviceEvent | SensorEvent]:
    """Convert a decoded RF packet dict to a list of our event objects.

    A single decoded packet may produce multiple ``SensorEvent`` objects (one
    per data type, e.g. temperature + humidity).  Command packets always
    produce exactly one ``RawDeviceEvent``.
    """
    cls = decoded.get("class", "command")
    protocol = decoded.get("protocol", "")
    model = str(decoded.get("model", ""))

    if cls == "sensor":
        return _sensor_events(decoded, protocol, model)

    # Command event → build the semicolon-separated raw string that our
    # integration's __init__._handle_raw_event already knows how to parse.
    house = decoded.get("house", "")
    unit = decoded.get("unit", decoded.get("code", ""))
    method = decoded.get("method", "")
    parts: list[str] = [
        "class:command",
        f"protocol:{protocol}",
        f"model:{model}",
    ]
    if house != "":
        parts.append(f"house:{house}")
    if unit != "":
        parts.append(f"unit:{unit}")
    if method:
        parts.append(f"method:{method}")
    raw = ";".join(parts) + ";"
    return [RawDeviceEvent(raw=raw, controller_id=0)]


def _sensor_events(
    decoded: dict, protocol: str, model: str
) -> list[SensorEvent]:
    """Extract SensorEvent objects from a decoded sensor packet."""
    sensor_id = int(decoded.get("sensorId", 0))
    events: list[SensorEvent] = []

    # Newer firmware "values" list format
    values = decoded.get("values")
    if values and isinstance(values, list):
        for entry in values:
            fw_type = int(entry.get("type", 0))
            data_type = _FIRMWARE_TYPE_TO_TYPE.get(fw_type, fw_type)
            value = str(entry.get("value", ""))
            if data_type and value:
                events.append(
                    SensorEvent(
                        sensor_id=sensor_id,
                        protocol=protocol,
                        model=model,
                        data_type=data_type,
                        value=value,
                    )
                )
        return events

    # Older data dict / list format
    data = decoded.get("data", [])
    if isinstance(data, dict):
        data = [{"name": k, "value": v} for k, v in data.items()]

    for item in data:
        name = str(item.get("name", ""))
        value = str(item.get("value", ""))
        data_type = _DATA_NAME_TO_TYPE.get(name)
        if data_type and value:
            events.append(
                SensorEvent(
                    sensor_id=sensor_id,
                    protocol=protocol,
                    model=model,
                    data_type=data_type,
                    value=value,
                )
            )
    return events


# ---------------------------------------------------------------------------
# Command encoding: build UDP packets for the Net/ZNet firmware
# ---------------------------------------------------------------------------

# TellStick method constants (matches const.py)
_TURNON = 1
_TURNOFF = 2
_DIM = 16
_LEARN = 32
_UP = 128
_DOWN = 256
_STOP = 512

# Arctech selflearning raw pulse values (from ProtocolNexa.cpp / arctech.py)
_SHORT = bytes([24])
_LONG = bytes([127])
_ONE = _SHORT + _LONG + _SHORT + _SHORT
_ZERO = _SHORT + _SHORT + _SHORT + _LONG


def _arctech_selflearning_pulses(
    house: int, unit_0: int, method: int, level: int = 0
) -> bytes:
    """Encode an arctech selflearning RF pulse sequence.

    Args:
        house:   26-bit house code (1 – 67108863).
        unit_0:  0-based unit number (unit-1).
        method:  TURNON / TURNOFF / DIM constant.
        level:   Dim level 0-255 (only used when method == DIM).
    """
    code = _SHORT + bytes([255])  # start bit
    for i in range(25, -1, -1):  # 26-bit house
        code += _ONE if (house & (1 << i)) else _ZERO
    code += _ZERO  # group bit = 0
    if method == _DIM:
        code += _SHORT + _SHORT + _SHORT + _SHORT
    elif method == _TURNOFF:
        code += _ZERO
    else:  # TURNON / LEARN / BELL
        code += _ONE
    for i in range(3, -1, -1):  # 4-bit unit
        code += _ONE if (unit_0 & (1 << i)) else _ZERO
    if method == _DIM:
        lvl = int(level) // 16
        for i in range(3, -1, -1):
            code += _ONE if (lvl & (1 << i)) else _ZERO
    return code + _SHORT


def encode_command(
    protocol: str,
    model: str,
    params: dict[str, str],
    method: int,
    param: int = 0,
) -> bytes | None:
    """Build a UDP command packet for the Net/ZNet firmware.

    Returns ``None`` when the protocol/method combination is not supported.

    Args:
        protocol: telldusd protocol name (e.g. ``"arctech"``).
        model:    model string, vendor suffix stripped by caller if needed.
        params:   device parameters (``{"house": "...", "unit": "..."}``,
                  ``{"code": "..."}``, etc.).
        method:   TellStick method constant (TURNON, TURNOFF, DIM …).
        param:    extra parameter (dim level 0-255, etc.).
    """
    proto = protocol.lower()
    base_model = model.split(":")[0].lower() if ":" in model else model.lower()

    # --- arctech selflearning (most common) ---
    if proto == "arctech" and base_model in (
        "selflearning",
        "selflearning-switch",
        "selflearning-dimmer",
    ):
        try:
            house_int = int(params.get("house", "1"))
            unit_int = int(params.get("unit", "1"))
        except (ValueError, TypeError):
            _LOGGER.warning("arctech: could not parse house/unit from %s", params)
            return None
        unit_0 = unit_int - 1

        if method in (_TURNON, _TURNOFF):
            # Native firmware arctech selflearning on/off
            args = OrderedDict(
                protocol="arctech",
                model="selflearning",
                house=house_int,
                unit=unit_0,
                method=method,
            )
            return build_packet("send", **args)

        if method == _DIM:
            pulses = _arctech_selflearning_pulses(house_int, unit_0, _DIM, param)
            return build_packet("send", S=pulses)

        if method == _LEARN:
            # Self-learning pairing: send a TURNON (receivers learn from it)
            args = OrderedDict(
                protocol="arctech",
                model="selflearning",
                house=house_int,
                unit=unit_0,
                method=_TURNON,
            )
            return build_packet("send", **args)

    # --- arctech codeswitch (Nexa old, Chacon old, …) ---
    # House = letter A-P, unit = 1-16.  No native firmware encode for
    # codeswitch; use raw pulse encoding.
    if proto == "arctech" and base_model == "codeswitch":
        _LOGGER.debug(
            "arctech/codeswitch raw pulse encode not yet implemented for Net/ZNet"
        )
        return None

    # --- sartano / fuhaote (code switch) ---
    if proto in ("sartano", "fuhaote"):
        _LOGGER.debug(
            "Protocol %r raw pulse encode not yet implemented for Net/ZNet",
            proto,
        )
        return None

    _LOGGER.debug(
        "encode_command: no encoder for protocol=%r model=%r method=%d",
        proto,
        base_model,
        method,
    )
    return None
