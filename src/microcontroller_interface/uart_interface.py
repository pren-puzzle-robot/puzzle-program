from __future__ import annotations

import logging
from collections import deque
import queue
import threading
import time

from puzzle_models import MachinePlacement

from .interface import MicrocontrollerInterface
from .uart_handler import (
    ACK,
    DONE_COMMAND,
    ERROR_COMMAND,
    INVALID_COMMAND,
    MoveCommand,
    ReceivedCommand,
    ReceiveCommandCode,
    SimpleSendCommand,
    START_COMMAND,
    UartHandler,
)

logger = logging.getLogger(__name__)


class _UartSession:
    """Owns the persistent UART connection and continuous background listener."""

    def __init__(self, handler: UartHandler) -> None:
        self._handler = handler
        self._connection = None
        self._connection_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._ack_event = threading.Event()
        self._command_queue: queue.Queue[ReceiveCommandCode] = queue.Queue()
        self._pending_commands: deque[ReceiveCommandCode] = deque()
        self._pending_lock = threading.Lock()
        self._listener_ready = threading.Event()
        self._listener_stop = threading.Event()
        self._listener_error: BaseException | None = None
        self._listener_thread: threading.Thread | None = None

    def ensure_started(self) -> None:
        with self._connection_lock:
            self._raise_if_listener_failed()

            if self._connection is None:
                self._connection = self._handler.open_serial()

            if self._listener_thread is None or not self._listener_thread.is_alive():
                self._listener_stop.clear()
                self._listener_ready.clear()
                self._listener_thread = threading.Thread(
                    target=self._listen_forever,
                    name="uart-listener",
                    daemon=True,
                )
                self._listener_thread.start()

        if not self._listener_ready.wait(timeout=self._handler.timeout_seconds + 1.0):
            raise RuntimeError("UART listener did not start in time")

        self._raise_if_listener_failed()

    def send_payload_with_handshake(self, payload: bytes) -> None:
        self.ensure_started()
        with self._write_lock:
            assert self._connection is not None
            self._ack_event.clear()
            logger.debug("Sending UART payload bytes: %s", payload)
            self._connection.write(payload)
            self._connection.flush()
            self._wait_for_ack()
            self.wait_for_event(
                {DONE_COMMAND},
                timeout_seconds=self._handler.done_timeout_seconds,
            )

    def wait_for_event(
        self,
        expected_events: set[ReceiveCommandCode],
        timeout_seconds: float,
    ) -> ReceiveCommandCode:
        self.ensure_started()
        deadline = time.monotonic() + timeout_seconds
        while True:
            self._raise_if_listener_failed()

            buffered = self._take_buffered_event(expected_events)
            if buffered is not None:
                return buffered

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Timed out waiting for one of {sorted(code.value for code in expected_events)}"
                )

            try:
                code = self._command_queue.get(timeout=min(remaining, self._handler.timeout_seconds))
            except queue.Empty:
                continue

            self._raise_if_command_error(code)
            if code in expected_events:
                return code

            with self._pending_lock:
                self._pending_commands.append(code)

            logger.debug(
                "Buffered UART event %s while waiting for %s",
                code,
                sorted(expected.value for expected in expected_events),
            )

    def _listen_forever(self) -> None:
        self._listener_ready.set()
        try:
            while not self._listener_stop.is_set():
                assert self._connection is not None
                try:
                    raw = self._handler.read_byte(self._connection)
                except TimeoutError:
                    continue

                if raw == ACK:
                    self._ack_event.set()
                    continue

                try:
                    code = self._handler.decode_byte(raw)
                except RuntimeError:
                    logger.warning("Ignoring invalid UART byte in listener: %r", raw)
                    continue

                logger.info("Received UART command %s", code.value)
                self._command_queue.put(code)
        except BaseException as exc:
            self._listener_error = exc
            logger.exception("UART listener stopped unexpectedly")
        finally:
            self._listener_stop.set()
            self._listener_ready.set()

    def _wait_for_ack(self) -> None:
        deadline = time.monotonic() + self._handler.ack_timeout_seconds
        while True:
            self._raise_if_listener_failed()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Timed out waiting for ACK")

            if self._ack_event.wait(timeout=min(remaining, self._handler.timeout_seconds)):
                self._ack_event.clear()
                return

    def _take_buffered_event(
        self,
        expected_events: set[ReceiveCommandCode],
    ) -> ReceiveCommandCode | None:
        with self._pending_lock:
            for _ in range(len(self._pending_commands)):
                code = self._pending_commands.popleft()
                self._raise_if_command_error(code)
                if code in expected_events:
                    return code
                self._pending_commands.append(code)
        return None

    @staticmethod
    def _raise_if_command_error(code: ReceiveCommandCode) -> None:
        if code is ERROR_COMMAND:
            raise RuntimeError("Microcontroller reported error")
        if code is INVALID_COMMAND:
            raise RuntimeError("Microcontroller reported invalid command")

    def _raise_if_listener_failed(self) -> None:
        if self._listener_error is not None:
            raise RuntimeError("UART listener stopped unexpectedly") from self._listener_error


class UartMicrocontrollerInterface(MicrocontrollerInterface):
    """UART transport with a persistent listener-backed session."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout_seconds: float = 1.0,
        byteorder: str = "<",
        ack_timeout_seconds: float = 2.0,
        done_timeout_seconds: float = 30.0,
        wait_for_start: bool = True,
    ) -> None:
        handler = UartHandler(
            port=port,
            baudrate=baudrate,
            timeout_seconds=timeout_seconds,
            byteorder=byteorder,
            ack_timeout_seconds=ack_timeout_seconds,
            done_timeout_seconds=done_timeout_seconds,
        )
        self._handler = handler
        self._session = _UartSession(handler)
        self.wait_for_start = wait_for_start

    def send_move(self, x: int, y: int, rotation: int) -> None:
        command = MoveCommand(x=x, y=y, rotation=rotation)
        logger.info(
            "Sending move command x=%d y=%d rotation=%d and waiting for done",
            command.x,
            command.y,
            command.rotation,
        )
        self._session.send_payload_with_handshake(self._encode_move(command))

    def send_command(self, command: SimpleSendCommand) -> None:
        logger.info("Sending UART command %s and waiting for done", command.value)
        self._session.send_payload_with_handshake(
            self._handler.encode_simple_command(command)
        )

    def wait_for_start_command(self) -> None:
        self._session.ensure_started()
        if not self.wait_for_start:
            logger.info("Skipping wait for start command due to configuration")
            return

        logger.info(
            "Waiting for start command '%s' on %s",
            START_COMMAND.value,
            self._handler.port,
        )
        self._session.wait_for_event({START_COMMAND}, timeout_seconds=float("inf"))
        logger.info("Received start command '%s'", START_COMMAND.value)

    def send_path(self, machine_points: list[MachinePlacement]) -> str:
        logger.info(
            "Sending %d machine placements over UART as pick-and-place sequences",
            len(machine_points),
        )
        logger.debug("UART placement payload: %s", machine_points)

        self._session.ensure_started()
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

            self._run_pick_and_place_sequence(start_move, end_move)

        result = f"sent_{len(machine_points)}_pick_and_place_sequences_over_uart"
        logger.info("UART send completed with result=%s", result)
        return result

    def receive_command(self) -> ReceivedCommand:
        logger.debug("Waiting for UART command on %s", self._handler.port)
        code = self._session.wait_for_event(
            expected_events={
                ReceiveCommandCode.START,
                ReceiveCommandCode.DONE,
                ReceiveCommandCode.ZEROED,
                ReceiveCommandCode.STOP,
            },
            timeout_seconds=self._handler.done_timeout_seconds,
        )
        return ReceivedCommand(code=code)

    def _run_pick_and_place_sequence(
        self,
        start_move: MoveCommand,
        end_move: MoveCommand,
    ) -> None:
        for command in (
            start_move,
            SimpleSendCommand.LOWER,
            SimpleSendCommand.HOLD_ON,
            SimpleSendCommand.LIFT,
            end_move,
            SimpleSendCommand.LOWER,
            SimpleSendCommand.HOLD_OFF,
            SimpleSendCommand.LIFT,
        ):
            self._send_transport_command(command)

    def _send_transport_command(self, command: MoveCommand | SimpleSendCommand) -> None:
        if isinstance(command, MoveCommand):
            payload = self._encode_move(command)
        else:
            payload = self._handler.encode_simple_command(command)
        self._session.send_payload_with_handshake(payload)

    @staticmethod
    def _encode_move(command: MoveCommand) -> bytes:
        # ToDo: switch to the full move payload once the microcontroller supports it.
        return b"M"
