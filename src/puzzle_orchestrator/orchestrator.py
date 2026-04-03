from __future__ import annotations

import logging

from camera_controller import CameraController
from coordinate_mapper import CoordinateMapper
from microcontroller_interface import MicrocontrollerInterface
from puzzle_solver import PuzzleSolver

logger = logging.getLogger(__name__)


class PuzzleOrchestrator:
    """Coordinates camera capture, solving, mapping, and microcontroller output."""

    def __init__(
        self,
        camera_controller: CameraController | None = None,
        puzzle_solver: PuzzleSolver | None = None,
        coordinate_mapper: CoordinateMapper | None = None,
        microcontroller_interface: MicrocontrollerInterface | None = None,
    ) -> None:
        self.camera_controller = camera_controller or CameraController()
        self.puzzle_solver = puzzle_solver or PuzzleSolver()
        self.coordinate_mapper = coordinate_mapper or CoordinateMapper()
        self.microcontroller_interface = (
            microcontroller_interface or MicrocontrollerInterface()
        )

    def run_once(self) -> str:
        logger.info("Waiting for microcontroller start command")
        self.microcontroller_interface.wait_for_start_command()
        logger.info("Start command received; running orchestration cycle")

        logger.info("Starting puzzle orchestration cycle")
        frame = self.camera_controller.capture_frame()
        logger.info("Captured frame: %s", frame)

        grid_path = self.puzzle_solver.solve(frame)
        logger.info("Solver produced %d placement steps", len(grid_path))

        machine_path = self.coordinate_mapper.map_to_machine(grid_path)
        logger.info("Mapped %d machine placements", len(machine_path))

        result = self.microcontroller_interface.send_path(machine_path)
        logger.info("Microcontroller accepted path with result=%s", result)
        return result
