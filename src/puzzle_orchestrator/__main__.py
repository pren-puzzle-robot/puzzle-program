import logging
import os

from microcontroller_interface import (
    MicrocontrollerInterface,
    UartMicrocontrollerInterface,
)

from .orchestrator import PuzzleOrchestrator


def configure_logging() -> None:
    level_name = os.getenv("PUZZLE_LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_microcontroller_interface() -> MicrocontrollerInterface:
    transport = os.getenv("PUZZLE_MICROCONTROLLER_TRANSPORT", "uart").strip().lower()
    if transport == "stub":
        return MicrocontrollerInterface()
    if transport != "uart":
        raise ValueError(
            "PUZZLE_MICROCONTROLLER_TRANSPORT must be 'uart' or 'stub', "
            f"got {transport!r}"
        )

    port = os.getenv("PUZZLE_UART_PORT", "/dev/serial0")
    baudrate = int(os.getenv("PUZZLE_UART_BAUDRATE", "57600"))
    timeout_seconds = float(os.getenv("PUZZLE_UART_TIMEOUT_SECONDS", "0.2"))
    ack_timeout_seconds = float(os.getenv("PUZZLE_UART_ACK_TIMEOUT_SECONDS", "1.0"))
    done_timeout_seconds = float(
        os.getenv("PUZZLE_UART_DONE_TIMEOUT_SECONDS", "30.0")
    )
    wait_for_start = os.getenv("PUZZLE_UART_WAIT_FOR_START", "false").lower() in {
        "true",
        "1",
        "yes",
    }

    return UartMicrocontrollerInterface(
        port=port,
        baudrate=baudrate,
        timeout_seconds=timeout_seconds,
        ack_timeout_seconds=ack_timeout_seconds,
        done_timeout_seconds=done_timeout_seconds,
        wait_for_start=wait_for_start
    )


def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    orchestrator = PuzzleOrchestrator(
        microcontroller_interface=build_microcontroller_interface()
    )
    try:
        result = orchestrator.run_once()
    except Exception:
        logger.exception("Puzzle run failed")
        raise

    logger.info("Puzzle run completed with result=%s", result)
    print(result)


if __name__ == "__main__":
    main()
