from __future__ import annotations

import argparse
import threading
import time

from .uart_interface import ACK, RECEIVE_COMMANDS


class ManualUartConsole:
    def __init__(self, port: str, baudrate: int, timeout_seconds: float) -> None:
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial is required for the manual UART console") from exc

        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout_seconds,
        )
        self._stop_event = threading.Event()
        self._ack_event = threading.Event()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)

    def start(self) -> None:
        self._reader_thread.start()

    def close(self) -> None:
        self._stop_event.set()
        if self._serial.is_open:
            self._serial.close()

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            raw = self._serial.read(1)
            if not raw:
                continue

            if raw == ACK:
                self._ack_event.set()
                continue

            try:
                code = raw.decode("ascii")
            except UnicodeDecodeError:
                print(f"< invalid byte {raw!r}")
                continue

            if code in RECEIVE_COMMANDS:
                print(f"< {code}")
            else:
                print(f"< unexpected {code!r}")

    def _send_and_wait_for_ack(self, payload: bytes) -> None:
        self._ack_event.clear()
        self._serial.write(payload)
        self._serial.flush()

        if not self._ack_event.wait(timeout=2.0):
            raise RuntimeError("Timed out waiting for ACK")

    def send_simple(self, command: str) -> None:
        self._send_and_wait_for_ack(command.encode("ascii"))

    def send_move(self, x: int, y: int, rotation: int) -> None:
        import struct

        for name, value in (("x", x), ("y", y), ("rotation", rotation)):
            if not 0 <= value <= 0xFFFF:
                raise ValueError(f"{name} must be in range 0..65535")

        payload = b"M" + struct.pack("<HHH", x, y, rotation)
        self._send_and_wait_for_ack(payload)


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

            if command in {"L", "l", "H", "h"}:
                try:
                    console.send_simple(command)
                    print(f"> sent {command} (Acknowledged)")
                except Exception as exc:
                    print(f"! {exc}")
                continue

            print("Unknown command. Use: M x y r | L | l | H | h | quit")
    finally:
        console.close()
        time.sleep(0.1)


if __name__ == "__main__":
    main()
