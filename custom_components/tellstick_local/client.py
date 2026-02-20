"""Asyncio TCP client for the telldusd daemon (via socat bridges)."""
from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .const import (
    TELLDUSD_DEVICE_EVENT,
    TELLDUSD_RAW_DEVICE_EVENT,
    TELLDUSD_SENSOR_EVENT,
    TELLSTICK_TEMPERATURE,
    TELLSTICK_HUMIDITY,
)

_LOGGER = logging.getLogger(__name__)

# Sensor data-type → unit mapping
SENSOR_UNIT: dict[int, str] = {
    TELLSTICK_TEMPERATURE: "°C",
    TELLSTICK_HUMIDITY: "%",
}


# ---------------------------------------------------------------------------
# Low-level message encoding / decoding (big-endian, UTF-8 strings)
# Format used by telldus-core's socket protocol:
#   string  → uint32 BE byte-length + UTF-8 bytes  (0xFFFFFFFF = null)
#   int32   → 4 bytes BE signed
# Each message is prefixed by a uint32 BE total size.
# ---------------------------------------------------------------------------

def _encode_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def _encode_int32(value: int) -> bytes:
    return struct.pack(">i", value)


def _decode_int32(data: bytes, pos: int) -> tuple[int, int]:
    (val,) = struct.unpack_from(">i", data, pos)
    return val, pos + 4


def _decode_string(data: bytes, pos: int) -> tuple[str | None, int]:
    (length,) = struct.unpack_from(">I", data, pos)
    pos += 4
    if length == 0xFFFFFFFF:
        return None, pos
    text = data[pos : pos + length].decode("utf-8", errors="replace")
    return text, pos + length


def _frame(payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + payload


async def _read_frame(reader: asyncio.StreamReader) -> bytes:
    """Read one length-prefixed frame from the stream."""
    size_bytes = await reader.readexactly(4)
    (size,) = struct.unpack(">I", size_bytes)
    return await reader.readexactly(size)


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

    _cmd_reader: asyncio.StreamReader | None = field(default=None, init=False, repr=False)
    _cmd_writer: asyncio.StreamWriter | None = field(default=None, init=False, repr=False)
    _event_reader: asyncio.StreamReader | None = field(default=None, init=False, repr=False)
    _event_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _callbacks: list[Callable[[Any], None]] = field(default_factory=list, init=False, repr=False)

    async def connect(self) -> None:
        """Open both command and event sockets."""
        self._cmd_reader, self._cmd_writer = await asyncio.open_connection(
            self.host, self.command_port
        )
        event_reader, _ = await asyncio.open_connection(self.host, self.event_port)
        self._event_reader = event_reader

    async def disconnect(self) -> None:
        """Close all connections."""
        if self._event_task:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
        if self._cmd_writer:
            self._cmd_writer.close()
            try:
                await self._cmd_writer.wait_closed()
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
    # Commands (port 50800)
    # ------------------------------------------------------------------

    async def turn_on(self, device_id: int) -> int:
        """Send tdTurnOn command. Returns 0 on success."""
        return await self._call("tdTurnOn", [_encode_int32(device_id)])

    async def turn_off(self, device_id: int) -> int:
        """Send tdTurnOff command. Returns 0 on success."""
        return await self._call("tdTurnOff", [_encode_int32(device_id)])

    async def dim(self, device_id: int, level: int) -> int:
        """Send tdDim command (level 0-255). Returns 0 on success."""
        return await self._call(
            "tdDim", [_encode_int32(device_id), _encode_int32(level)]
        )

    async def ping(self) -> bool:
        """Try to get the device count to confirm the connection is alive."""
        try:
            await self._call("tdGetNumberOfDevices", [])
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
        device_id = await self._call("tdAddDevice", [])
        if device_id <= 0:
            raise RuntimeError(f"tdAddDevice returned error code {device_id}")
        await self._call("tdSetName", [_encode_int32(device_id), _encode_string(name)])
        await self._call(
            "tdSetProtocol", [_encode_int32(device_id), _encode_string(protocol)]
        )
        if model:
            await self._call(
                "tdSetModel", [_encode_int32(device_id), _encode_string(model)]
            )
        for param_name, param_value in parameters.items():
            await self._call(
                "tdSetDeviceParameter",
                [
                    _encode_int32(device_id),
                    _encode_string(param_name),
                    _encode_string(param_value),
                ],
            )
        return device_id

    async def remove_device(self, device_id: int) -> None:
        """Remove a device from telldusd."""
        await self._call("tdRemoveDevice", [_encode_int32(device_id)])

    async def list_devices(self) -> list[dict[str, Any]]:
        """Return all devices registered in telldusd as a list of dicts."""
        count = await self._call("tdGetNumberOfDevices", [])
        devices: list[dict[str, Any]] = []
        for i in range(count):
            try:
                device_id = await self._call("tdGetDeviceId", [_encode_int32(i)])
                if device_id < 0:
                    continue
                protocol = (
                    await self._call_str("tdGetProtocol", [_encode_int32(device_id)])
                    or ""
                )
                house = (
                    await self._call_str(
                        "tdGetDeviceParameter",
                        [
                            _encode_int32(device_id),
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
                            _encode_int32(device_id),
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

    async def find_or_add_device(
        self,
        name: str,
        protocol: str,
        model: str,
        house: str,
        unit: str,
    ) -> int:
        """Find an existing telldusd device by protocol/house/unit or create it.

        This avoids creating duplicates when the integration reconnects to a running
        telldusd instance that already has the device registered.
        """
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

    async def _call(self, function: str, params: list[bytes]) -> int:
        """Send a command and return the int32 result."""
        if self._cmd_writer is None or self._cmd_reader is None:
            raise RuntimeError("Not connected")
        payload = _encode_string(function)
        for p in params:
            payload += p
        self._cmd_writer.write(_frame(payload))
        await self._cmd_writer.drain()
        response = await _read_frame(self._cmd_reader)
        if len(response) >= 4:
            (result,) = struct.unpack_from(">i", response, 0)
            return result
        return 0

    async def _call_str(self, function: str, params: list[bytes]) -> str | None:
        """Send a command and return the string result."""
        if self._cmd_writer is None or self._cmd_reader is None:
            raise RuntimeError("Not connected")
        payload = _encode_string(function)
        for p in params:
            payload += p
        self._cmd_writer.write(_frame(payload))
        await self._cmd_writer.drain()
        response = await _read_frame(self._cmd_reader)
        if len(response) >= 4:
            value, _ = _decode_string(response, 0)
            return value
        return None

    # ------------------------------------------------------------------
    # Events (port 50801)
    # ------------------------------------------------------------------

    async def _event_loop(self) -> None:
        """Continuously read and dispatch events from the event socket."""
        if self._event_reader is None:
            return
        while True:
            try:
                data = await _read_frame(self._event_reader)
                self._dispatch_event(data)
            except asyncio.IncompleteReadError:
                _LOGGER.warning("TellStick event socket closed")
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Error reading TellStick event: %s", exc)

    def _dispatch_event(self, data: bytes) -> None:
        """Parse a single event frame and notify callbacks."""
        try:
            event = self._parse_event(data)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Could not parse TellStick event: %s", exc)
            return
        if event is None:
            return
        for cb in list(self._callbacks):
            try:
                cb(event)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Error in TellStick event callback: %s", exc)

    @staticmethod
    def _parse_event(data: bytes) -> DeviceEvent | RawDeviceEvent | SensorEvent | None:
        """Parse an event from telldusd binary format."""
        if len(data) < 4:
            return None
        event_type, pos = _decode_int32(data, 0)

        if event_type == TELLDUSD_DEVICE_EVENT:
            device_id, pos = _decode_int32(data, pos)
            method, pos = _decode_int32(data, pos)
            value, pos = _decode_string(data, pos)
            return DeviceEvent(device_id=device_id, method=method, value=value)

        if event_type == TELLDUSD_RAW_DEVICE_EVENT:
            raw, pos = _decode_string(data, pos)
            controller_id, pos = _decode_int32(data, pos)
            return RawDeviceEvent(raw=raw or "", controller_id=controller_id)

        if event_type == TELLDUSD_SENSOR_EVENT:
            sensor_id, pos = _decode_int32(data, pos)
            protocol, pos = _decode_string(data, pos)
            model, pos = _decode_string(data, pos)
            data_type, pos = _decode_int32(data, pos)
            value, pos = _decode_string(data, pos)
            return SensorEvent(
                sensor_id=sensor_id,
                protocol=protocol,
                model=model,
                data_type=data_type,
                value=value,
            )

        return None
