import logging
import os

from camera_controller import CameraController, MockCameraController
from coordinate_mapper import CoordinateMapper
from microcontroller_interface import (
    MicrocontrollerInterface,
    UartMicrocontrollerInterface,
)
from puzzle_models import CameraPort, CoordinateMapperPort, MicrocontrollerPort, PuzzleSolverPort
from puzzle_solver import PuzzleSolver

from .orchestrator import PuzzleOrchestrator


def configure_logging() -> None:
    level_name = os.getenv("PUZZLE_LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_microcontroller_interface() -> MicrocontrollerPort:
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


def build_camera_controller() -> CameraPort:
    transport = os.getenv("PUZZLE_CAMERA_TRANSPORT", "gopro").strip().lower()
    if transport == "mock":
        image_path = os.getenv(
            "PUZZLE_MOCK_CAMERA_IMAGE",
            str(os.path.join(".", "data", "with_aruco2_flattened.JPG")),
        )
        return MockCameraController(image_path=image_path)
    if transport != "gopro":
        raise ValueError(
            "PUZZLE_CAMERA_TRANSPORT must be 'gopro' or 'mock', "
            f"got {transport!r}"
        )

    return CameraController()

def build_puzzle_solver() -> PuzzleSolverPort:
    return PuzzleSolver(
        min_area=os.getenv("PUZZLE_SOLVER_MIN_AREA", "60000"),
        threshold_value=os.getenv("PUZZLE_SOLVER_THRESHOLD"),
        variant=os.getenv("PUZZLE_SOLVER_ALGO", "fast"),
    )


def build_coordinate_mapper() -> CoordinateMapperPort:
    return CoordinateMapper()


def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    orchestrator = PuzzleOrchestrator(
        camera_controller=build_camera_controller(),
        puzzle_solver=build_puzzle_solver(),
        coordinate_mapper=build_coordinate_mapper(),
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
