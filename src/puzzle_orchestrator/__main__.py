import logging

from camera_controller import CameraController, MockCameraController
from coordinate_mapper import CoordinateMapper, CoordinateOffset
from microcontroller_interface import (
    MicrocontrollerInterface,
    UartMicrocontrollerInterface,
)
from puzzle_models import CameraPort, CoordinateMapperPort, MicrocontrollerPort, PuzzleSolverPort
from puzzle_solver import PuzzleSolver

from .config import AppConfig, load_config
from .orchestrator import PuzzleOrchestrator


def configure_logging(config: AppConfig) -> None:
    level_name = config.logging.level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_microcontroller_interface(config: AppConfig) -> MicrocontrollerPort:
    transport = config.microcontroller.transport
    if transport == "stub":
        return MicrocontrollerInterface()
    if transport != "uart":
        raise ValueError(
            "microcontroller.transport in config.ini must be 'uart' or 'stub', "
            f"got {transport!r}"
        )

    return UartMicrocontrollerInterface(
        port=config.uart.port,
        baudrate=config.uart.baudrate,
        timeout_seconds=config.uart.timeout_seconds,
        ack_timeout_seconds=config.uart.ack_timeout_seconds,
        done_timeout_seconds=config.uart.done_timeout_seconds,
        wait_for_start=config.uart.wait_for_start,
    )


def build_camera_controller(config: AppConfig) -> CameraPort:
    transport = config.camera.transport
    if transport == "mock":
        return MockCameraController(image_path=config.camera.mock_image)
    if transport != "gopro":
        raise ValueError(
            "camera.transport in config.ini must be 'gopro' or 'mock', "
            f"got {transport!r}"
        )

    return CameraController()


def build_puzzle_solver(config: AppConfig) -> PuzzleSolverPort:
    return PuzzleSolver(
        min_area=config.solver.min_area,
        threshold_value=config.solver.threshold_value,
        variant=config.solver.algorithm,
    )


def build_coordinate_mapper(config: AppConfig) -> CoordinateMapperPort:
    return CoordinateMapper(
        scale_x=config.coordinate_mapper.scale_x,
        scale_y=config.coordinate_mapper.scale_y,
        start_offset=CoordinateOffset(
            x_min=config.coordinate_mapper.start.x_min,
            y_min=config.coordinate_mapper.start.y_min,
        ),
        end_offset=CoordinateOffset(
            x_min=config.coordinate_mapper.end.x_min,
            y_min=config.coordinate_mapper.end.y_min,
        ),
    )


def main() -> None:
    config = load_config()
    configure_logging(config)
    logger = logging.getLogger(__name__)
    orchestrator = PuzzleOrchestrator(
        camera_controller=build_camera_controller(config),
        puzzle_solver=build_puzzle_solver(config),
        coordinate_mapper=build_coordinate_mapper(config),
        microcontroller_interface=build_microcontroller_interface(config),
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
