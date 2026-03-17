"""Asyncio TCP client for the telldusd daemon (via socat bridges).

telldusd uses a text-based socket protocol (NOT binary framing):
  - Strings are encoded as: ``<byte_length>:<utf8_text>`` (e.g. ``7:arctech``)
  - Integers are encoded as: ``i<decimal_digits>s``       (e.g. ``i42s``)

**Command socket** (port 50800):
  Each command requires its own TCP connection because telldusd creates a
  one-shot handler per UNIX-socket connection (reads one message, responds,
  closes).  socat with ``fork`` maps each TCP connection to a fresh UNIX
  connection, so we open a new TCP connection for every command.
  Command responses are terminated by ``\\n``.

**Event socket** (port 50801):
  A single persistent TCP connection.  telldusd pushes events to all
  connected clients.  Event messages use the same text encoding but are
  **not** newline-terminated; they are self-delimiting because each token
  starts with either a digit (string) or ``i`` (integer).

Source of truth: ``telldus-core/common/Message.cpp`` for encoding,
``telldus-core/service/ClientCommunicationHandler.cpp`` for commands,
``telldus-core/service/EventUpdateManager.cpp`` for events.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text-based protocol encoding
# ---------------------------------------------------------------------------

def _encode_string(value: str) -> str:
    """Encode a string argument for the telldusd text protocol."""
    encoded = value.encode("utf-8")
    return f"{len(encoded)}:{value}"


def _encode_int(value: int) -> str:
    """Encode an integer argument for the telldusd text protocol."""
    return f"i{value}s"


def _build_command(function: str, args: list[str]) -> bytes:
    """Build a complete command message as bytes ready to send."""
    msg = _encode_string(function)
    for arg in args:
        msg += arg
    return msg.encode("utf-8")


# ---------------------------------------------------------------------------
# Text-based protocol decoding (async stream readers)
# ---------------------------------------------------------------------------

async def _read_token(reader: asyncio.StreamReader) -> tuple[str, Any]:
    """Read one self-delimiting token from an asyncio stream.

    Returns ``('int', int_value)`` or ``('str', str_value)``.
    Raises ``asyncio.IncompleteReadError`` if the stream closes mid-token.
    """
    first = await reader.readexactly(1)
    ch = chr(first[0])

    if ch == "i":
        # Integer: i<digits>s
        digits = bytearray()
        while True:
            b = await reader.readexactly(1)
            if b == b"s":
                break
            digits.extend(b)
        return ("int", int(digits.decode("ascii")))

    if ch.isdigit():
        # String: <length>:<text>
        length_str = ch
        while True:
            b = await reader.readexactly(1)
            if b == b":":
                break
            length_str += chr(b[0])
        length = int(length_str)
        if length == 0:
            return ("str", "")
        text = await reader.readexactly(length)
        return ("str", text.decode("utf-8", errors="replace"))

    raise ValueError(f"Unexpected byte in telldusd protocol: {ch!r}")


def _parse_int_response(data: str) -> int:
    """Parse an integer response string like ``i42s``."""
    data = data.strip()
    if data.startswith("i") and data.endswith("s"):
        return int(data[1:-1])
    raise ValueError(f"Not an integer response: {data!r}")


def _parse_string_response(data: str) -> str | None:
    """Parse a string response like ``7:arctech``."""
    data = data.strip()
    if not data or not data[0].isdigit():
        return None
    if ":" not in data:
        return None
    idx = data.index(":")
    length = int(data[:idx])
    return data[idx + 1 : idx + 1 + length]


# ---------------------------------------------------------------------------
# Sensor data-type → unit mapping
# ---------------------------------------------------------------------------

SENSOR_UNIT: dict[int, str] = {
    1: "°C",   # TELLSTICK_TEMPERATURE
    2: "%",    # TELLSTICK_HUMIDITY
}


# ---------------------------------------------------------------------------
# Data classes for events
# ---------------------------------------------------------------------------

@dataclass
class RawDeviceEvent:
    """A raw RF event received by the TellStick hardware."""

    raw: str  # e.g. "class:command;protocol:arctech;house:A;unit:1;method:turnon;"
    controller_id: int

    @property
    def params(self) -> dict[str, str]:
        """Parse the key:value pairs from the raw string."""
        result: dict[str, str] = {}
        for part in self.raw.split(";"):
            if ":" in part:
                k, _, v = part.partition(":")
                result[k.strip()] = v.strip()
        return result

    @property
    def device_id(self) -> str:
        """Build a stable, unique device identifier from RF parameters."""
        p = self.params
        parts = [
            p.get("protocol", ""),
            p.get("model", ""),
            p.get("house", ""),
            p.get("unit", p.get("code", "")),
        ]
        return "_".join(filter(None, parts))


@dataclass
class DeviceEvent:
    """A state-change event for a named device."""

    device_id: int
    method: int
    value: str | None


@dataclass
class SensorEvent:
    """A sensor reading event."""

    sensor_id: int
    protocol: str | None
    model: str | None
    data_type: int
    value: str | None


# ---------------------------------------------------------------------------
# TellStick TCP client
# ---------------------------------------------------------------------------

@dataclass
class TellStickController:
    """Manages connections to telldusd command and event sockets."""

    host: str
    command_port: int
    event_port: int

    _event_reader: asyncio.StreamReader | None = field(default=None, init=False, repr=False)
    _event_writer: asyncio.StreamWriter | None = field(default=None, init=False, repr=False)
    _event_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _callbacks: list[Callable[[Any], None]] = field(default_factory=list, init=False, repr=False)

    async def connect(self) -> None:
        """Open the event socket (commands use one-shot connections)."""
        self._event_reader, self._event_writer = await asyncio.open_connection(
            self.host, self.event_port
        )

    async def disconnect(self) -> None:
        """Close all connections."""
        if self._event_task:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
        if self._event_writer:
            self._event_writer.close()
            try:
                await self._event_writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    def start_event_listener(self) -> None:
        """Start listening for events in the background."""
        self._event_task = asyncio.ensure_future(self._event_loop())

    def add_callback(self, callback: Callable[[Any], None]) -> None:
        """Register a callback for incoming events."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Any], None]) -> None:
        """Unregister a callback."""
        self._callbacks.remove(callback)

    # ------------------------------------------------------------------
    # Commands (port 50800) – one TCP connection per command
    # ------------------------------------------------------------------

    async def turn_on(self, device_id: int) -> int:
        """Send tdTurnOn command. Returns 0 on success."""
        return await self._call_int(
            "tdTurnOn", [_encode_int(device_id)]
        )

    async def learn(self, device_id: int) -> int:
        """Send tdLearn command (self-learning teach signal). Returns 0 on success."""
        return await self._call_int(
            "tdLearn", [_encode_int(device_id)]
        )

    async def turn_off(self, device_id: int) -> int:
        """Send tdTurnOff command. Returns 0 on success."""
        return await self._call_int(
            "tdTurnOff", [_encode_int(device_id)]
        )

    async def dim(self, device_id: int, level: int) -> int:
        """Send tdDim command (level 0-255). Returns 0 on success."""
        return await self._call_int(
            "tdDim", [_encode_int(device_id), _encode_int(level)]
        )

    async def up(self, device_id: int) -> int:
        """Send tdUp command (blinds open/up). Returns 0 on success.

        Mirrors the turn_on/turn_off pattern — one TCP connection per command.
        Used by cover entities (hasta, brateck protocols).
        """
        return await self._call_int(
            "tdUp", [_encode_int(device_id)]
        )

    async def down(self, device_id: int) -> int:
        """Send tdDown command (blinds close/down). Returns 0 on success."""
        return await self._call_int(
            "tdDown", [_encode_int(device_id)]
        )

    async def stop(self, device_id: int) -> int:
        """Send tdStop command (blinds stop). Returns 0 on success."""
        return await self._call_int(
            "tdStop", [_encode_int(device_id)]
        )

    async def ping(self) -> bool:
        """Try to get the device count to confirm the connection is alive."""
        try:
            await self._call_int("tdGetNumberOfDevices", [])
            return True
        except Exception:  # noqa: BLE001
            return False

    async def add_device(
        self,
        name: str,
        protocol: str,
        model: str,
        parameters: dict[str, str],
    ) -> int:
        """Register a new device with telldusd and return its ID."""
        device_id = await self._call_int("tdAddDevice", [])
        if device_id <= 0:
            raise RuntimeError(f"tdAddDevice returned error code {device_id}")
        await self._call_int(
            "tdSetName", [_encode_int(device_id), _encode_string(name)]
        )
        await self._call_int(
            "tdSetProtocol", [_encode_int(device_id), _encode_string(protocol)]
        )
        # Strip vendor suffix (e.g. "selflearning-switch:luxorparts" →
        # "selflearning-switch") — telldusd only knows the base model name.
        # Also map RF event model names to telldusd model names: RF events
        # report "selflearning" but ProtocolNexa::methods() only recognises
        # "selflearning-switch" and "selflearning-dimmer".
        td_model = model.split(":")[0] if model else ""
        _RF_TO_TELLDUSD = {"selflearning": "selflearning-switch"}
        td_model = _RF_TO_TELLDUSD.get(td_model, td_model)
        if td_model:
            await self._call_int(
                "tdSetModel", [_encode_int(device_id), _encode_string(td_model)]
            )
        for param_name, param_value in parameters.items():
            await self._call_int(
                "tdSetDeviceParameter",
                [
                    _encode_int(device_id),
                    _encode_string(param_name),
                    _encode_string(param_value),
                ],
            )
        return device_id

    async def remove_device(self, device_id: int) -> None:
        """Remove a device from telldusd."""
        await self._call_int("tdRemoveDevice", [_encode_int(device_id)])

    async def list_devices(self) -> list[dict[str, Any]]:
        """Return all devices registered in telldusd as a list of dicts."""
        count = await self._call_int("tdGetNumberOfDevices", [])
        devices: list[dict[str, Any]] = []
        for i in range(count):
            try:
                device_id = await self._call_int(
                    "tdGetDeviceId", [_encode_int(i)]
                )
                if device_id < 0:
                    continue
                protocol = (
                    await self._call_str(
                        "tdGetProtocol", [_encode_int(device_id)]
                    )
                    or ""
                )
                house = (
                    await self._call_str(
                        "tdGetDeviceParameter",
                        [
                            _encode_int(device_id),
                            _encode_string("house"),
                            _encode_string(""),
                        ],
                    )
                    or ""
                )
                unit = (
                    await self._call_str(
                        "tdGetDeviceParameter",
                        [
                            _encode_int(device_id),
                            _encode_string("unit"),
                            _encode_string(""),
                        ],
                    )
                    or ""
                )
                devices.append(
                    {
                        "id": device_id,
                        "protocol": protocol.lower(),
                        "house": house,
                        "unit": unit,
                    }
                )
            except Exception:  # noqa: BLE001
                continue
        return devices

    async def get_device_name_model(self, device_id: int) -> tuple[str, str]:
        """Return (name, model) for a telldusd device ID.

        Used only by the app-config import path — not called during normal
        operation so it does not affect the existing startup or command flows.
        Returns empty strings on any error.
        """
        try:
            name = await self._call_str("tdGetName", [_encode_int(device_id)]) or ""
            model = await self._call_str("tdGetModel", [_encode_int(device_id)]) or ""
        except Exception:  # noqa: BLE001
            return "", ""
        return name, model

    async def find_or_add_device(
        self,
        name: str,
        protocol: str,
        model: str,
        house: str,
        unit: str,
    ) -> int:
        """Find an existing telldusd device by protocol/house/unit or create it."""
        for dev in await self.list_devices():
            if (
                dev["protocol"] == protocol.lower()
                and dev["house"] == house
                and dev["unit"] == unit
            ):
                return dev["id"]
        return await self.add_device(
            name, protocol, model, {"house": house, "unit": unit}
        )

    async def _call_int(self, function: str, args: list[str]) -> int:
        """Send a command via a one-shot TCP connection, return int result."""
        response = await self._send_command(function, args)
        return _parse_int_response(response)

    async def _call_str(self, function: str, args: list[str]) -> str | None:
        """Send a command via a one-shot TCP connection, return string result."""
        response = await self._send_command(function, args)
        return _parse_string_response(response)

    async def _send_command(self, function: str, args: list[str]) -> str:
        """Open a fresh TCP connection, send command, read response, close."""
        reader, writer = await asyncio.open_connection(
            self.host, self.command_port
        )
        try:
            cmd_bytes = _build_command(function, args)
            writer.write(cmd_bytes)
            await writer.drain()
            # Command responses are newline-terminated
            raw = await asyncio.wait_for(reader.readline(), timeout=10.0)
            return raw.decode("utf-8", errors="replace").rstrip("\n")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Events (port 50801) – persistent connection
    # ------------------------------------------------------------------

    async def _event_loop(self) -> None:
        """Continuously read and dispatch events from the event socket."""
        if self._event_reader is None:
            return
        while True:
            try:
                event = await self._read_event()
                if event is not None:
                    self._dispatch(event)
            except asyncio.IncompleteReadError:
                _LOGGER.warning("TellStick event socket closed")
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Error reading TellStick event: %s", exc)

    async def _read_event(self) -> DeviceEvent | RawDeviceEvent | SensorEvent | None:
        """Read one complete event from the event stream."""
        reader = self._event_reader
        if reader is None:
            return None

        # First token is always the event type name (a string)
        token_type, event_name = await _read_token(reader)
        if token_type != "str":
            return None

        if event_name == "TDRawDeviceEvent":
            _, raw = await _read_token(reader)        # string
            _, controller_id = await _read_token(reader)  # int
            return RawDeviceEvent(raw=raw or "", controller_id=controller_id)

        if event_name == "TDDeviceEvent":
            _, device_id = await _read_token(reader)    # int
            _, method = await _read_token(reader)       # int
            _, value = await _read_token(reader)        # string
            return DeviceEvent(device_id=device_id, method=method, value=value)

        if event_name == "TDSensorEvent":
            _, protocol = await _read_token(reader)     # string
            _, model = await _read_token(reader)        # string
            _, sensor_id = await _read_token(reader)    # int
            _, data_type = await _read_token(reader)    # int
            _, value = await _read_token(reader)        # string
            _, _timestamp = await _read_token(reader)   # int (unused)
            return SensorEvent(
                sensor_id=sensor_id,
                protocol=protocol,
                model=model,
                data_type=data_type,
                value=value,
            )

        if event_name in ("TDDeviceChangeEvent", "TDControllerEvent"):
            # Consume the tokens so the stream stays aligned, but we don't
            # expose these event types yet.
            if event_name == "TDDeviceChangeEvent":
                for _ in range(3):  # int + int + int
                    await _read_token(reader)
            else:  # TDControllerEvent
                for _ in range(4):  # int + int + int + string
                    await _read_token(reader)
            return None

        _LOGGER.debug("Unknown telldusd event type: %s", event_name)
        return None

    def _dispatch(self, event: Any) -> None:
        """Notify all registered callbacks."""
        for cb in list(self._callbacks):
            try:
                cb(event)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Error in TellStick event callback: %s", exc)
