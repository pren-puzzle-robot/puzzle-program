from __future__ import annotations

import logging

from puzzle_models import MachinePlacement

from .interface import MicrocontrollerInterface
logger = logging.getLogger(__name__)
from .uart_handler import (
    MoveCommand,
    ReceivedCommand,
    ReceiveCommandCode,
    SimpleSendCommand,
    START_COMMAND,
    UartHandler,
)


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
        self._handler = UartHandler(
            port=port,
            baudrate=baudrate,
            timeout_seconds=timeout_seconds,
            byteorder=byteorder,
            ack_timeout_seconds=ack_timeout_seconds,
            done_timeout_seconds=done_timeout_seconds,
        )
        self.wait_for_start = wait_for_start

    def send_move(self, x: int, y: int, rotation: int) -> None:
        command = MoveCommand(x=x, y=y, rotation=rotation)
        logger.info(
            "Sending move command x=%d y=%d rotation=%d and waiting for done",
            command.x,
            command.y,
            command.rotation,
        )
        with self._handler.open_serial() as connection:
            self._handler.send_move(connection, command)

    def send_command(self, command: SimpleSendCommand) -> None:
        logger.info("Sending UART command %s and waiting for done", command.value)
        with self._handler.open_serial() as connection:
            self._handler.send_simple_command(connection, command)

    def wait_for_start_command(self) -> None:
        if not self.wait_for_start:
            logger.info("Skipping wait for start command due to configuration")
            return
        logger.info(
            "Waiting for start command '%s' on %s",
            START_COMMAND.value,
            self._handler.port,
        )
        with self._handler.open_serial() as connection:
            self._handler.wait_for_event(
                connection,
                {START_COMMAND},
                timeout_seconds=float("inf"),
            )
        logger.info("Received start command '%s'", START_COMMAND.value)

    def send_path(self, machine_points: list[MachinePlacement]) -> str:
        logger.info(
            "Sending %d machine placements over UART as pick-and-place sequences",
            len(machine_points),
        )
        logger.debug("UART placement payload: %s", machine_points)

        with self._handler.open_serial() as connection:
            for placement in machine_points:
                start_move = MoveCommand(
                    x=int(round(float(placement.start[0]))),
                    y=int(round(float(placement.start[1]))),
                    rotation=0,
                )
                end_move = MoveCommand(
                    x=int(round(float(placement.end[0]))),
                    y=int(round(float(placement.end[1]))),
                    rotation=int(round(float(placement.rotation))),
                )

                logger.info(
                    "Picking piece %s: move to start (%d, %d), pick, move to destination (%d, %d), place with rotation %d",
                    placement.piece_id,
                    start_move.x,
                    start_move.y,
                    end_move.x,
                    end_move.y,
                    end_move.rotation,
                )

                self._handler.send_move(connection, start_move)
                self._handler.send_simple_command(connection, SimpleSendCommand.LOWER)
                self._handler.send_simple_command(connection, SimpleSendCommand.HOLD_ON)
                self._handler.send_simple_command(connection, SimpleSendCommand.LIFT)

                self._handler.send_move(connection, end_move)
                self._handler.send_simple_command(connection, SimpleSendCommand.LOWER)
                self._handler.send_simple_command(connection, SimpleSendCommand.HOLD_OFF)
                self._handler.send_simple_command(connection, SimpleSendCommand.LIFT)

        result = f"sent_{len(machine_points)}_pick_and_place_sequences_over_uart"
        logger.info("UART send completed with result=%s", result)
        return result

    def receive_command(self) -> ReceivedCommand:
        logger.debug("Waiting for UART command on %s", self._handler.port)
        with self._handler.open_serial() as connection:
            code = self._handler.wait_for_event(
                connection,
                expected_events={
                    ReceiveCommandCode.START,
                    ReceiveCommandCode.DONE,
                    ReceiveCommandCode.ZEROED,
                    ReceiveCommandCode.STOP,
                },
                timeout_seconds=self._handler.done_timeout_seconds,
            )

        logger.info("Received UART command %s", code.value)
        return ReceivedCommand(code=code)
