from __future__ import annotations

from typing import Protocol

from .placements import MachinePlacement, SolverPlacement


class CameraPort(Protocol):
    def capture_frame(self) -> str: ...


class PuzzleSolverPort(Protocol):
    def solve(self, frame: str) -> list[SolverPlacement]: ...


class CoordinateMapperPort(Protocol):
    def map_to_machine(
        self,
        placements: list[SolverPlacement],
    ) -> list[MachinePlacement]: ...


class MicrocontrollerPort(Protocol):
    def wait_for_start_command(self) -> None: ...

    def send_path(self, machine_points: list[MachinePlacement]) -> str: ...
