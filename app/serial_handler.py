"""Async serial communication handler with reconnection logic."""

import asyncio
import os
from datetime import UTC, datetime
from enum import Enum

import serial
import serial.tools.list_ports
import structlog
from serial import SerialException

log = structlog.get_logger()


class ConnectionState(str, Enum):
    """Serial connection state."""

    UNAVAILABLE = "unavailable"  # Port doesn't exist or can't be opened
    OFF = "off"  # Port accessible but device powered off
    ON = "on"  # Device connected and powered on


class SerialHandler:
    """Async serial handler with automatic reconnection."""

    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        timeout: float = 2.0,
        heartbeat_interval: int = 30,
        reconnect_backoff_max: int = 30,
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self.reconnect_backoff_max = reconnect_backoff_max

        self._serial: serial.Serial | None = None
        self._lock = asyncio.Lock()
        self._state = ConnectionState.UNAVAILABLE
        self._last_heartbeat: datetime | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False
        self._reconnect_delay = 1.0
        self._initialized = False

        # Cached device state
        self._cached_power_state: bool | None = None

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def last_heartbeat(self) -> datetime | None:
        """Last successful heartbeat timestamp."""
        return self._last_heartbeat

    @property
    def is_connected(self) -> bool:
        """Whether the serial port is connected."""
        return self._serial is not None and self._serial.is_open

    @property
    def is_initialized(self) -> bool:
        """Whether the handler has completed initial setup."""
        return self._initialized

    async def start(self) -> None:
        """Start the serial handler."""
        self._running = True
        log.info("serial_handler_starting", port=self.port, baud_rate=self.baud_rate)

        # Try initial connection
        await self._try_connect()
        self._initialized = True

        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        log.info("serial_handler_started", state=self._state)

    async def stop(self) -> None:
        """Stop the serial handler."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        await self._disconnect()
        log.info("serial_handler_stopped")

    async def _try_connect(self) -> bool:
        """Attempt to connect to the serial port."""
        # Check if port exists
        if not os.path.exists(self.port):
            log.debug("serial_port_not_found", port=self.port)
            self._state = ConnectionState.UNAVAILABLE
            return False

        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )

            # Clear any stale data
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

            log.info("serial_connected", port=self.port)

            # Check power state to determine if device is on or off
            await self._check_power_state()

            # Reset reconnect delay on successful connection
            self._reconnect_delay = 1.0

            return True

        except SerialException as e:
            log.warning("serial_connection_failed", port=self.port, error=str(e))
            self._state = ConnectionState.UNAVAILABLE
            return False

    async def _disconnect(self) -> None:
        """Disconnect from the serial port."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception as e:
                log.warning("serial_close_error", error=str(e))

        self._serial = None
        self._state = ConnectionState.UNAVAILABLE
        self._cached_power_state = None
        log.info("serial_disconnected")

    async def _check_power_state(self) -> None:
        """Check the device power state and update connection state."""
        try:
            response = await self._send_command_internal("r power!")
            if response:
                if "power on" in response.lower():
                    self._state = ConnectionState.ON
                    self._cached_power_state = True
                elif "power off" in response.lower():
                    self._state = ConnectionState.OFF
                    self._cached_power_state = False
                else:
                    # Got a response but couldn't parse power state
                    self._state = ConnectionState.ON
                    self._cached_power_state = None
                self._last_heartbeat = datetime.now(UTC)
            else:
                self._state = ConnectionState.UNAVAILABLE
        except Exception as e:
            log.warning("power_state_check_failed", error=str(e))
            self._state = ConnectionState.UNAVAILABLE

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat to verify device connectivity."""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                if not self._running:
                    break

                if self.is_connected:
                    # Send heartbeat
                    await self._check_power_state()

                    if self._state == ConnectionState.UNAVAILABLE:
                        log.warning("heartbeat_failed_disconnecting")
                        await self._disconnect()
                        self._schedule_reconnect()
                else:
                    # Try to reconnect
                    await self._try_reconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("heartbeat_error", error=str(e))

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        if self._reconnect_task and not self._reconnect_task.done():
            return

        self._reconnect_task = asyncio.create_task(self._try_reconnect())

    async def _try_reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        while self._running and not self.is_connected:
            log.info(
                "attempting_reconnect",
                port=self.port,
                delay=self._reconnect_delay,
            )

            if await self._try_connect():
                log.info("reconnection_successful", port=self.port)
                return

            # Exponential backoff
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self.reconnect_backoff_max)

    async def _send_command_internal(self, command: str) -> str | None:
        """Send command without lock (internal use only)."""
        if not self._serial or not self._serial.is_open:
            return None

        try:
            # Ensure command ends with newline for consistency
            if not command.endswith("\r\n"):
                command = command.rstrip("\r\n") + "\r\n"

            # Send command
            self._serial.write(command.encode("ascii"))
            self._serial.flush()

            # Read response (may be multiple lines)
            await asyncio.sleep(0.1)  # Give device time to respond

            response_lines = []
            while self._serial.in_waiting > 0:
                line = self._serial.readline().decode("ascii", errors="ignore").strip()
                if line:
                    response_lines.append(line)
                await asyncio.sleep(0.05)

            response = "\n".join(response_lines)
            return response if response else None

        except SerialException as e:
            log.error("serial_write_error", error=str(e))
            return None
        except Exception as e:
            log.error("command_error", error=str(e))
            return None

    async def send_command(self, command: str) -> tuple[bool, str | None, str | None]:
        """
        Send a command to the device.

        Returns:
            Tuple of (success, response, error_message)
        """
        async with self._lock:
            if not self.is_connected:
                return False, None, "device_unavailable"

            log.debug("sending_command", command=command.strip())

            response = await self._send_command_internal(command)

            if response is None:
                # Connection might have been lost
                await self._disconnect()
                self._schedule_reconnect()
                return False, None, "device_communication_error"

            log.debug("received_response", response=response)
            return True, response, None

    async def get_device_info(self) -> dict:
        """Get device information."""
        info = {
            "connection": self._state.value,
            "port": self.port,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
        }

        if self.is_connected and self._state != ConnectionState.UNAVAILABLE:
            # Get device type
            success, response, _ = await self.send_command("r type!")
            if success and response:
                info["device_type"] = response.strip()

            # Get firmware version
            success, response, _ = await self.send_command("r fw version!")
            if success and response:
                info["firmware"] = response.strip()

        return info
