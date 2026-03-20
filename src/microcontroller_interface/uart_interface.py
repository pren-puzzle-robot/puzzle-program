from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass

from .interface import MicrocontrollerInterface

logger = logging.getLogger(__name__)

ACK = b"A"
SEND_COMMANDS = {"M", "L", "l", "H", "h"}
RECEIVE_COMMANDS = {"S", "D", "Z", "s", "E"}
START_COMMAND = "S"
DONE_COMMAND = "D"
ERROR_COMMAND = "E"


@dataclass(frozen=True)
class ReceivedCommand:
    code: str


class UartMicrocontrollerInterface(MicrocontrollerInterface):
    """Sample UART transport for simple command-based microcontroller control."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout_seconds: float = 1.0,
        byteorder: str = "<",
        ack_timeout_seconds: float = 2.0,
        done_timeout_seconds: float = 30.0,
        wait_for_start: bool = True
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self.byteorder = byteorder
        self.ack_timeout_seconds = ack_timeout_seconds
        self.done_timeout_seconds = done_timeout_seconds
        self.wait_for_start = wait_for_start

    def _open_serial(self):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required for UartMicrocontrollerInterface"
            ) from exc

        return serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout_seconds,
        )

    def _require_uint16(self, value: int, field_name: str) -> int:
        if not 0 <= value <= 0xFFFF:
            raise ValueError(f"{field_name} must be in range 0..65535")
        return value

    def send_move(self, x: int, y: int, rotation: int) -> None:
        x = self._require_uint16(x, "x")
        y = self._require_uint16(y, "y")
        rotation = self._require_uint16(rotation, "rotation")
        payload = b"M" + struct.pack(f"{self.byteorder}HHH", x, y, rotation)
        logger.info(
            "Sending move command x=%d y=%d rotation=%d and waiting for done",
            x,
            y,
            rotation,
        )
        with self._open_serial() as connection:
            self._send_bytes_with_handshake(connection, payload)

    def send_command(self, command: str) -> None:
        if command not in SEND_COMMANDS - {"M"}:
            raise ValueError(f"Unsupported send command: {command!r}")

        logger.info("Sending UART command %s and waiting for done", command)
        with self._open_serial() as connection:
            self._send_bytes_with_handshake(connection, command.encode("ascii"))

    def _read_byte(self, connection) -> bytes:
        raw = connection.read(1)
        if not raw:
            raise TimeoutError("Timed out waiting for UART byte")
        return raw

    def _wait_for_ack(self, connection) -> None:
        deadline = time.monotonic() + self.ack_timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Timed out waiting for ACK")

            try:
                raw = self._read_byte(connection)
            except TimeoutError:
                continue

            if raw == ACK:
                return

            try:
                code = raw.decode("ascii")
            except UnicodeDecodeError as exc:
                raise RuntimeError(f"Expected ACK {ACK!r}, received non-ASCII byte {raw!r}") from exc

            if code == ERROR_COMMAND:
                raise RuntimeError("Microcontroller reported error while waiting for ACK")

            raise RuntimeError(f"Expected ACK {ACK!r}, received {raw!r}")

    def _wait_for_event(self, connection, expected_events: set[str], timeout_seconds: float) -> str:
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Timed out waiting for one of {sorted(expected_events)}"
                )

            try:
                raw = self._read_byte(connection)
            except TimeoutError:
                continue

            if raw == ACK:
                continue

            try:
                code = raw.decode("ascii")
            except UnicodeDecodeError:
                logger.warning("Ignoring invalid UART byte while waiting for event: %r", raw)
                continue

            if code == ERROR_COMMAND:
                raise RuntimeError("Microcontroller reported error")

            if code in expected_events:
                return code

            if code in RECEIVE_COMMANDS:
                logger.debug("Ignoring UART event %s while waiting for %s", code, sorted(expected_events))
                continue

            raise RuntimeError(f"Unknown UART command received: {code!r}")

    def wait_for_start_command(self) -> None:
        if not self.wait_for_start:
            logger.info("Skipping wait for start command due to configuration")
            return
        logger.info("Waiting for start command '%s' on %s", START_COMMAND, self.port)
        with self._open_serial() as connection:
            self._wait_for_event(connection, {START_COMMAND}, timeout_seconds=float("inf"))
        logger.info("Received start command '%s'", START_COMMAND)

    def _send_bytes_with_handshake(self, connection, payload: bytes) -> None:
        logger.debug("Sending UART payload bytes: %s", payload)
        connection.write(payload)
        connection.flush()
        self._wait_for_ack(connection)
        self._wait_for_event(connection, {DONE_COMMAND}, timeout_seconds=self.done_timeout_seconds)

    def send_path(self, machine_points: list[dict[str, object]]) -> str:
        """
        Sample transport of placement data as discrete UART commands.

        Assumption:
        - `M` encodes target end position and rotation as three uint16 values.
        - `L`, `l`, `H`, `h` are available via `send_command(...)` for external use.
        """
        logger.info(
            "Sending %d machine placements over UART as discrete commands",
            len(machine_points),
        )
        logger.debug("UART placement payload: %s", machine_points)

        with self._open_serial() as connection:
            for placement in machine_points:
                end_x = int(round(float(placement["end"][0])))
                end_y = int(round(float(placement["end"][1])))
                rotation = int(round(float(placement["rotation"])))
                end_x = self._require_uint16(end_x, "x")
                end_y = self._require_uint16(end_y, "y")
                rotation = self._require_uint16(rotation, "rotation")
                payload = b"M" + struct.pack(f"{self.byteorder}HHH", end_x, end_y, rotation)
                logger.info(
                    "Sending move command x=%d y=%d rotation=%d and waiting for done",
                    end_x,
                    end_y,
                    rotation,
                )
                self._send_bytes_with_handshake(connection, payload)

        result = f"sent_{len(machine_points)}_move_commands_over_uart"
        logger.info("UART send completed with result=%s", result)
        return result

    def receive_command(self) -> ReceivedCommand:
        logger.debug("Waiting for UART command on %s", self.port)
        with self._open_serial() as connection:
            code = self._wait_for_event(
                connection,
                expected_events=set(RECEIVE_COMMANDS) - {ERROR_COMMAND},
                timeout_seconds=self.done_timeout_seconds,
            )

        logger.info("Received UART command %s", code)
        return ReceivedCommand(code=code)
