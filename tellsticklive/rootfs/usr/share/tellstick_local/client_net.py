"""Asyncio UDP client for TellStick Net and TellStick ZNet hardware.

TellStick Net / ZNet communicate locally over UDP port 42314.  This module
provides a ``TellStickNetController`` that exposes **the same interface** as
``TellStickController`` in ``client.py``, so the rest of the integration
(``__init__.py``, platform files, config flows) does not need to know which
hardware type is in use.

Key differences from the TCP / telldusd path:
 - UDP on port 42314 (not TCP on 50800/50801).
 - Commands are encoded with the Net/ZNet hex-length wire protocol
   (see ``net_protocol.py``), not the telldusd decimal-length protocol.
 - No persistent device registry on the hardware — we maintain one in memory.
 - ``add_device`` / ``find_or_add_device`` / ``remove_device`` work entirely
   in-memory; no round-trip to the hardware is needed.
 - ``list_devices`` returns ``[]`` (no persistent list on Net/ZNet).
 - ``learn`` sends the RF pairing signal via UDP.

Registration:
 The Net/ZNet firmware begins pushing RF events to our machine only after we
 send a ``reglistener`` packet.  We re-send it every 10 minutes so the
 firmware does not time-out our registration.  Binding to port 42314 locally
 lets the firmware know our ephemeral source port, and ensures we receive its
 events on the same port.

Sources (Apache-2.0, used with attribution):
  https://github.com/molobrakos/tellsticknet
"""
from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from .client import DeviceEvent, RawDeviceEvent, SensorEvent
from .net_protocol import (
    build_packet,
    decode_packet,
    decoded_to_events,
    encode_command,
)

_LOGGER = logging.getLogger(__name__)

# UDP port the TellStick Net/ZNet firmware listens on (and sends from).
_FIRMWARE_PORT = 42314

# Re-register every 10 minutes (firmware drops listeners that stop pinging).
_REREGISTER_INTERVAL_SECS = 600

# TellStick method constants – mirrors const.py to avoid circular imports.
_TURNON = 1
_TURNOFF = 2
_DIM = 16
_LEARN = 32
_UP = 128
_DOWN = 256
_STOP = 512


class _NetUDPProtocol(asyncio.DatagramProtocol):
    """asyncio datagram protocol that feeds packets to TellStickNetController."""

    def __init__(self, controller: TellStickNetController) -> None:
        self._controller = controller
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            decoded = decode_packet(data)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Error decoding Net/ZNet datagram from %s: %s", addr, exc)
            return
        if decoded is None:
            return
        try:
            events = decoded_to_events(decoded)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Error converting Net/ZNet packet to events: %s", exc)
            return
        for event in events:
            self._controller._dispatch(event)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.warning("TellStick Net/ZNet UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        _LOGGER.debug("TellStick Net/ZNet UDP connection lost: %s", exc)


class TellStickNetController:
    """Controller for TellStick Net and TellStick ZNet hardware.

    Implements the same public interface as ``TellStickController`` so the
    rest of the integration can use either interchangeably.
    """

    def __init__(self, host: str) -> None:
        self._host = host
        self._transport: asyncio.DatagramTransport | None = None
        self._udp_protocol: _NetUDPProtocol | None = None
        self._callbacks: list[Any] = []
        self._reregister_task: asyncio.Task | None = None

        # In-memory device registry: fake_id → device parameters
        # Re-populated on every connect() from async_setup_entry.
        self._device_registry: dict[int, dict[str, Any]] = {}
        self._next_device_id: int = 1

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Bind to the local UDP port and send the initial reglistener."""
        loop = asyncio.get_event_loop()
        try:
            self._transport, self._udp_protocol = (
                await loop.create_datagram_endpoint(
                    lambda: _NetUDPProtocol(self),
                    local_addr=("", _FIRMWARE_PORT),
                    family=socket.AF_INET,
                    allow_broadcast=False,
                )
            )
        except OSError as exc:
            # Port 42314 may already be bound by another process.  Re-raise
            # as OSError so async_setup_entry can report it to HA.
            raise OSError(
                f"Cannot bind UDP port {_FIRMWARE_PORT} for TellStick Net/ZNet: {exc}"
            ) from exc
        await self._send_reglistener()

    async def disconnect(self) -> None:
        """Cancel background tasks and close the UDP socket."""
        if self._reregister_task:
            self._reregister_task.cancel()
            try:
                await self._reregister_task
            except asyncio.CancelledError:
                pass
            self._reregister_task = None
        if self._transport:
            self._transport.close()
            self._transport = None

    def start_event_listener(self) -> None:
        """Start the periodic re-registration loop.

        Call this after ``connect()`` to keep the firmware registration alive.
        """
        self._reregister_task = asyncio.ensure_future(
            self._reregister_loop()
        )

    async def _reregister_loop(self) -> None:
        while True:
            await asyncio.sleep(_REREGISTER_INTERVAL_SECS)
            try:
                await self._send_reglistener()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "TellStick Net/ZNet: re-registration failed: %s", exc
                )

    async def _send_reglistener(self) -> None:
        """Send a reglistener packet to the firmware."""
        if not self._transport:
            return
        pkt = build_packet("reglistener")
        self._transport.sendto(pkt, (self._host, _FIRMWARE_PORT))
        _LOGGER.debug("Sent reglistener to %s:%d", self._host, _FIRMWARE_PORT)

    def _send_raw(self, data: bytes) -> None:
        """Send raw bytes to the firmware (fire-and-forget)."""
        if not self._transport:
            _LOGGER.warning(
                "TellStick Net/ZNet: cannot send — not connected"
            )
            return
        self._transport.sendto(data, (self._host, _FIRMWARE_PORT))

    async def ping(self) -> bool:
        """Return True if the transport is open (basic liveness check)."""
        return self._transport is not None

    # ------------------------------------------------------------------
    # Callback dispatch (mirrors TellStickController)
    # ------------------------------------------------------------------

    def add_callback(self, callback: Any) -> None:
        """Register a callback for incoming RF events."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Any) -> None:
        """Remove a previously registered callback."""
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def _dispatch(self, event: RawDeviceEvent | SensorEvent | DeviceEvent) -> None:
        """Dispatch a decoded RF event to all registered callbacks."""
        for cb in list(self._callbacks):
            try:
                cb(event)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error(
                    "Error in TellStick Net/ZNet event callback: %s", exc
                )

    # ------------------------------------------------------------------
    # In-memory device registry
    # Mirrors the telldusd device registry in client.py but lives only in
    # RAM.  IDs are re-assigned on every HA restart (that is fine — the
    # mapping is rebuilt from entry.options[CONF_DEVICES] in
    # async_setup_entry).
    # ------------------------------------------------------------------

    async def add_device(
        self,
        name: str,
        protocol: str,
        model: str,
        params: dict[str, Any],
    ) -> int:
        """Register a device in the in-memory registry and return its ID.

        Equivalent to telldusd's tdAddDevice / tdSetProtocol / tdSetModel /
        tdSetDeviceParameter sequence.
        """
        dev_id = self._next_device_id
        self._next_device_id += 1
        self._device_registry[dev_id] = {
            "name": name,
            "protocol": protocol.lower(),
            # Strip vendor suffix so encode_command sees the bare model.
            "model": model.split(":")[0] if ":" in model else model,
            "params": dict(params),
        }
        _LOGGER.debug(
            "Net/ZNet: registered device id=%d name=%r protocol=%r model=%r params=%s",
            dev_id, name, protocol, model, params,
        )
        return dev_id

    async def find_or_add_device(
        self,
        name: str,
        protocol: str,
        model: str,
        house: str,
        unit: str,
    ) -> int:
        """Find an existing device by protocol/house/unit or add it.

        Mirrors ``TellStickController.find_or_add_device``.
        """
        proto_lc = protocol.lower()
        base_model = model.split(":")[0].lower() if ":" in model else model.lower()
        for dev_id, dev in self._device_registry.items():
            if (
                dev["protocol"] == proto_lc
                and dev.get("params", {}).get("house") == house
                and dev.get("params", {}).get("unit") == unit
            ):
                return dev_id
        params: dict[str, str] = {}
        if house:
            params["house"] = house
        if unit:
            params["unit"] = unit
        return await self.add_device(name, protocol, base_model, params)

    async def remove_device(self, device_id: int) -> None:
        """Remove a device from the in-memory registry (no-op for unknown IDs)."""
        self._device_registry.pop(device_id, None)

    async def list_devices(self) -> list[dict[str, Any]]:
        """Return an empty list — Net/ZNet has no persistent device list."""
        return []

    async def get_device_name_model(
        self, device_id: int
    ) -> tuple[str, str]:
        """Return (name, model) for a known device ID."""
        dev = self._device_registry.get(device_id, {})
        return dev.get("name", ""), dev.get("model", "")

    # ------------------------------------------------------------------
    # Commands (mirrors TellStickController)
    # ------------------------------------------------------------------

    def _send_command(
        self, device_id: int, method: int, param: int = 0
    ) -> int:
        """Encode and send a command to the firmware.  Returns 0 on success, -1 on failure."""
        dev = self._device_registry.get(device_id)
        if dev is None:
            _LOGGER.warning(
                "Net/ZNet: send_command: unknown device id=%d (method=%d)",
                device_id, method,
            )
            return -1
        pkt = encode_command(
            dev["protocol"],
            dev["model"],
            dev.get("params", {}),
            method,
            param,
        )
        if pkt is None:
            _LOGGER.warning(
                "Net/ZNet: no encoder for protocol=%r model=%r method=%d",
                dev["protocol"], dev["model"], method,
            )
            return -1
        self._send_raw(pkt)
        return 0

    async def turn_on(self, device_id: int) -> int:
        """Turn a device on."""
        return self._send_command(device_id, _TURNON)

    async def turn_off(self, device_id: int) -> int:
        """Turn a device off."""
        return self._send_command(device_id, _TURNOFF)

    async def dim(self, device_id: int, level: int) -> int:
        """Dim a device to the given level (0-255)."""
        return self._send_command(device_id, _DIM, level)

    async def up(self, device_id: int) -> int:
        """Send UP command (covers/blinds)."""
        return self._send_command(device_id, _UP)

    async def down(self, device_id: int) -> int:
        """Send DOWN command (covers/blinds)."""
        return self._send_command(device_id, _DOWN)

    async def stop(self, device_id: int) -> int:
        """Send STOP command (covers/blinds)."""
        return self._send_command(device_id, _STOP)

    async def learn(self, device_id: int) -> int:
        """Send a learn/pairing signal for a self-learning device.

        This is the RF signal that puts a self-learning receiver into paired
        state — i.e. the equivalent of pressing a remote button while the
        receiver is in learn mode.

        For arctech selflearning the firmware sends a TURNON; receivers in
        learn mode store the house/unit code from it.  The caller (config
        flow ``async_step_confirm`` and ``async_step_teach_device``) is
        responsible for instructing the user to put the receiver in learn
        mode first.
        """
        return self._send_command(device_id, _LEARN)
