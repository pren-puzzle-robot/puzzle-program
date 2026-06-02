from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from puzzle_models import (
    CameraPort,
    CoordinateMapperPort,
    MicrocontrollerPort,
    PuzzleSolverPort,
)

from .audio import SoundPlayer

logger = logging.getLogger(__name__)
T = TypeVar("T")


class PuzzleOrchestrator:
    """Coordinates camera capture, solving, mapping, and microcontroller output."""

    def __init__(
        self,
        camera_controller: CameraPort,
        puzzle_solver: PuzzleSolverPort,
        coordinate_mapper: CoordinateMapperPort,
        microcontroller_interface: MicrocontrollerPort,
        sound_player: SoundPlayer,
    ) -> None:
        self.camera_controller = camera_controller
        self.puzzle_solver = puzzle_solver
        self.coordinate_mapper = coordinate_mapper
        self.microcontroller_interface = microcontroller_interface
        self.sound_player = sound_player

    def run_once(self) -> str:
        logger.info("Waiting for microcontroller start command")
        self._run_stage(
            stage_name="microcontroller wait_for_start_command",
            sound_stage="microcontroller",
            operation=self.microcontroller_interface.wait_for_start_command,
        )
        logger.info("Start command received; running orchestration cycle")
        self.sound_player.start_run_audio()

        try:
            logger.info("Starting puzzle orchestration cycle")
            frame = self._run_stage(
                stage_name="camera capture_frame",
                sound_stage="camera",
                operation=self.camera_controller.capture_frame,
            )
            logger.info("Captured frame: %s", frame)

            grid_path = self._run_stage(
                stage_name="solver solve",
                sound_stage="solver",
                operation=lambda: self.puzzle_solver.solve(frame),
            )
            logger.info("Solver produced %d placement steps", len(grid_path))

            machine_path = self._run_stage(
                stage_name="coordinate mapper map_to_machine",
                sound_stage="coordinate_mapper",
                operation=lambda: self.coordinate_mapper.map_to_machine(grid_path, frame=frame),
            )
            logger.info("Mapped %d machine placements", len(machine_path))

            result = self._run_stage(
                stage_name="microcontroller send_path",
                sound_stage="microcontroller",
                operation=lambda: self.microcontroller_interface.send_path(machine_path),
            )
            logger.info("Microcontroller accepted path with result=%s", result)
            return result
        finally:
            self.sound_player.stop_in_progress_loop()

    def _run_stage(
        self,
        stage_name: str,
        sound_stage: str,
        operation: Callable[[], T],
    ) -> T:
        try:
            return operation()
        except Exception as exc:
            logger.exception("Orchestration stage failed: %s", stage_name)
            self.sound_player.play_error(sound_stage, exc)
            setattr(exc, "_puzzle_error_sound_played", True)
            raise
