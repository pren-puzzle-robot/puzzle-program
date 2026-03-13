from __future__ import annotations

import logging
import struct
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ACK = b"A"
SEND_COMMANDS = {"M", "L", "l", "H", "h"}
RECEIVE_COMMANDS = {"S", "D", "Z", "s", "E"}


@dataclass(frozen=True)
class ReceivedCommand:
    code: str


class UartMicrocontrollerInterface:
    """Sample UART transport for simple command-based microcontroller control."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout_seconds: float = 1.0,
        byteorder: str = "<",
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self.byteorder = byteorder

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

    def _send_bytes(self, payload: bytes) -> None:
        logger.debug("Sending UART payload bytes: %s", payload)
        with self._open_serial() as connection:
            connection.write(payload)
            connection.flush()
            ack = connection.read(1)

        if ack != ACK:
            raise RuntimeError(f"Expected ACK {ACK!r}, received {ack!r}")

    def send_move(self, x: int, y: int, rotation: int) -> None:
        x = self._require_uint16(x, "x")
        y = self._require_uint16(y, "y")
        rotation = self._require_uint16(rotation, "rotation")
        payload = b"M" + struct.pack(f"{self.byteorder}HHH", x, y, rotation)
        logger.info("Sending move command x=%d y=%d rotation=%d", x, y, rotation)
        self._send_bytes(payload)

    def send_command(self, command: str) -> None:
        if command not in SEND_COMMANDS - {"M"}:
            raise ValueError(f"Unsupported send command: {command!r}")

        logger.info("Sending UART command %s", command)
        self._send_bytes(command.encode("ascii"))

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

        for placement in machine_points:
            end_x = int(round(float(placement["end"][0])))
            end_y = int(round(float(placement["end"][1])))
            rotation = int(round(float(placement["rotation"])))
            self.send_move(end_x, end_y, rotation)

        result = f"sent_{len(machine_points)}_move_commands_over_uart"
        logger.info("UART send completed with result=%s", result)
        return result

    def receive_command(self) -> ReceivedCommand:
        logger.debug("Waiting for UART command on %s", self.port)
        with self._open_serial() as connection:
            raw = connection.read(1)

        if not raw:
            raise RuntimeError("Timed out waiting for UART command")

        code = raw.decode("ascii")
        if code not in RECEIVE_COMMANDS:
            raise RuntimeError(f"Unknown UART command received: {code!r}")

        logger.info("Received UART command %s", code)
        return ReceivedCommand(code=code)
