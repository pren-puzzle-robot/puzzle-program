from __future__ import annotations

import argparse
import threading
import time

from .uart_handler import (
    MoveCommand,
    RECEIVE_COMMANDS,
    SimpleSendCommand,
    UartHandler,
)


class ManualUartConsole:
    def __init__(self, port: str, baudrate: int, timeout_seconds: float) -> None:
        self._handler = UartHandler(
            port=port,
            baudrate=baudrate,
            timeout_seconds=timeout_seconds,
            ack_timeout_seconds=2.0,
            done_timeout_seconds=2.0,
        )
        self._serial = self._handler.open_serial()
        self._stop_event = threading.Event()
        self._serial_lock = threading.Lock()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)

    def start(self) -> None:
        self._reader_thread.start()

    def close(self) -> None:
        self._stop_event.set()
        if self._serial.is_open:
            self._serial.close()

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._serial_lock.acquire(timeout=0.05):
                continue
            try:
                try:
                    raw = self._handler.read_byte(self._serial)
                except TimeoutError:
                    continue

                try:
                    code = self._handler.decode_byte(raw)
                except RuntimeError:
                    print(f"< invalid byte {raw!r}")
                    continue

                if code in RECEIVE_COMMANDS:
                    print(f"< {code.value}")
                else:
                    print(f"< unexpected {code!r}")
            finally:
                self._serial_lock.release()

    def send_simple(self, command: SimpleSendCommand) -> None:
        with self._serial_lock:
            self._handler.send_simple_command(self._serial, command)

    def send_move(self, x: int, y: int, rotation: int) -> None:
        with self._serial_lock:
            self._handler.send_move(
                self._serial,
                MoveCommand(x=x, y=y, rotation=rotation),
            )

    @staticmethod
    def parse_simple_command(raw: str) -> SimpleSendCommand | None:
        mapping = {
            "L": SimpleSendCommand.LIFT,
            "l": SimpleSendCommand.LOWER,
            "H": SimpleSendCommand.HOLD_ON,
            "h": SimpleSendCommand.HOLD_OFF,
        }
        return mapping.get(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual UART console for puzzle commands.")
    parser.add_argument("--port", default="/dev/serial0", help="UART port, for example COM3")
    parser.add_argument("--baudrate", type=int, default=57600, help="UART baudrate")
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.2,
        help="serial read timeout in seconds",
    )
    args = parser.parse_args()

    console = ManualUartConsole(
        port=args.port,
        baudrate=args.baudrate,
        timeout_seconds=args.timeout,
    )
    console.start()

    print("Commands: M x y r | L | l | H | h | quit")

    try:
        while True:
            line = input("> ").strip()
            if not line:
                continue
            if line.lower() in {"quit", "exit"}:
                break

            parts = line.split()
            command = parts[0]

            if command == "M":
                if len(parts) != 4:
                    print("Usage: M <x> <y> <rotation>")
                    continue
                try:
                    x, y, rotation = (int(parts[1]), int(parts[2]), int(parts[3]))
                    console.send_move(x, y, rotation)
                    print("> sent M")
                except Exception as exc:
                    print(f"! {exc}")
                continue

            simple_command = console.parse_simple_command(command)
            if simple_command is not None:
                try:
                    console.send_simple(simple_command)
                    print(f"> sent {simple_command.value} (Acknowledged)")
                except Exception as exc:
                    print(f"! {exc}")
                continue

            print("Unknown command. Use: M x y r | L | l | H | h | quit")
    finally:
        console.close()
        time.sleep(0.1)


if __name__ == "__main__":
    main()
