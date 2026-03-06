from __future__ import annotations

from camera_controller import CameraController
from coordinate_mapper import CoordinateMapper
from microcontroller_interface import MicrocontrollerInterface
from puzzle_solver import PuzzleSolver


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
        frame = self.camera_controller.capture_frame()
        grid_path = self.puzzle_solver.solve(frame)
        machine_path = self.coordinate_mapper.map_to_machine(grid_path)
        return self.microcontroller_interface.send_path(machine_path)
