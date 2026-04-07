from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

logger = logging.getLogger(__name__)

ACK = b"A"


class SimpleSendCommand(Enum):
    LIFT = "L"
    LOWER = "l"
    HOLD_ON = "H"
    HOLD_OFF = "h"


class ReceiveCommandCode(Enum):
    START = "S"
    DONE = "D"
    ZEROED = "Z"
    STOP = "s"
    ERROR = "E"
    INVALID_COMMAND = "N"


START_COMMAND = ReceiveCommandCode.START
DONE_COMMAND = ReceiveCommandCode.DONE
ERROR_COMMAND = ReceiveCommandCode.ERROR
INVALID_COMMAND = ReceiveCommandCode.INVALID_COMMAND
RECEIVE_COMMANDS = set(ReceiveCommandCode)


@dataclass(frozen=True)
class MoveCommand:
    x: int
    y: int
    rotation: int


SendCommand: TypeAlias = SimpleSendCommand | MoveCommand


@dataclass(frozen=True)
class ReceivedCommand:
    code: ReceiveCommandCode


class UartHandler:
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout_seconds: float = 1.0,
        byteorder: str = "<",
        ack_timeout_seconds: float = 2.0,
        done_timeout_seconds: float = 30.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self.byteorder = byteorder
        self.ack_timeout_seconds = ack_timeout_seconds
        self.done_timeout_seconds = done_timeout_seconds

    def open_serial(self):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial is required for UART communication") from exc

        return serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout_seconds,
        )

    def require_uint16(self, value: int, field_name: str) -> int:
        if not 0 <= value <= 0xFFFF:
            raise ValueError(f"{field_name} must be in range 0..65535")
        return value

    def encode_move_payload(self, command: MoveCommand) -> bytes:
        x = self.require_uint16(command.x, "x")
        y = self.require_uint16(command.y, "y")
        rotation = self.require_uint16(command.rotation, "rotation")
        return b"M" + struct.pack(f"{self.byteorder}HHH", x, y, rotation)

    def encode_simple_command(self, command: SimpleSendCommand) -> bytes:
        return command.value.encode("ascii")

    def read_byte(self, connection) -> bytes:
        raw = connection.read(1)
        if not raw:
            raise TimeoutError("Timed out waiting for UART byte")
        return raw

    def decode_byte(self, raw: bytes) -> ReceiveCommandCode:
        try:
            decoded = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"Received non-ASCII UART byte {raw!r}") from exc
        try:
            return ReceiveCommandCode(decoded)
        except ValueError as exc:
            raise RuntimeError(f"Unknown UART command received: {decoded!r}") from exc

    def wait_for_ack(self, connection) -> None:
        deadline = time.monotonic() + self.ack_timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Timed out waiting for ACK")

            try:
                raw = self.read_byte(connection)
            except TimeoutError:
                continue

            if raw == ACK:
                return

            code = self.decode_byte(raw)
            if code is ERROR_COMMAND:
                raise RuntimeError("Microcontroller reported error while waiting for ACK")
            if code is INVALID_COMMAND:
                raise RuntimeError("Microcontroller reported invalid command while waiting for ACK")

            raise RuntimeError(f"Expected ACK {ACK!r}, received {raw!r}")

    def wait_for_event(
        self,
        connection,
        expected_events: set[ReceiveCommandCode],
        timeout_seconds: float,
    ) -> ReceiveCommandCode:
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Timed out waiting for one of {sorted(expected_events)}"
                )

            try:
                raw = self.read_byte(connection)
            except TimeoutError:
                continue

            if raw == ACK:
                continue

            try:
                code = self.decode_byte(raw)
            except RuntimeError:
                logger.warning(
                    "Ignoring invalid UART byte while waiting for event: %r",
                    raw,
                )
                continue

            if code is ERROR_COMMAND:
                raise RuntimeError("Microcontroller reported error")

            if code in expected_events:
                return code

            if code in RECEIVE_COMMANDS:
                logger.debug(
                    "Ignoring UART event %s while waiting for %s",
                    code,
                    sorted(expected_events),
                )
                continue

            raise RuntimeError(f"Unknown UART command received: {code.value!r}")

    def send_payload_with_handshake(self, connection, payload: bytes) -> None:
        logger.debug("Sending UART payload bytes: %s", payload)
        connection.write(payload)
        connection.flush()
        self.wait_for_ack(connection)
        self.wait_for_event(
            connection,
            {DONE_COMMAND},
            timeout_seconds=self.done_timeout_seconds,
        )

    def send_simple_command(self, connection, command: SimpleSendCommand) -> None:
        self.send_payload_with_handshake(
            connection,
            self.encode_simple_command(command),
        )

    def send_move(self, connection, command: MoveCommand) -> None:
        self.send_payload_with_handshake(
            connection,
            # ToDo: use correct payload encoding once Microcontroller Supports it
            "M".encode("ascii"),
            # self.encode_move_payload(command),
        )
