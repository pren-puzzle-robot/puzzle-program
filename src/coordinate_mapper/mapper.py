from __future__ import annotations

import logging
from dataclasses import dataclass

from puzzle_models import MachinePlacement, SolverPlacement

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoordinateOffset:
    x_min: float
    y_min: float


class CoordinateMapper:
    """Maps puzzle-grid coordinates to machine coordinates."""

    def __init__(
        self,
        scale_x: float,
        scale_y: float,
        start_offset: CoordinateOffset,
        end_offset: CoordinateOffset,
    ) -> None:
        self.scale_x = float(scale_x)
        self.scale_y = float(scale_y)
        self.start_offset = start_offset
        self.end_offset = end_offset

    def map_to_machine(
        self,
        placements: list[SolverPlacement],
    ) -> list[MachinePlacement]:
        logger.info("Mapping %d solver placements to machine coordinates", len(placements))
        machine_points = [
            MachinePlacement(
                piece_id=placement.piece_id,
                start=self._map_point(placement.start, self.start_offset),
                end=self._map_point(placement.end, self.end_offset),
                rotation=float(placement.rotation),
            )
            for placement in placements
        ]
        logger.debug("Mapped machine placements: %s", machine_points)
        return machine_points

    def _map_point(
        self,
        point: tuple[float, float],
        offset: CoordinateOffset,
    ) -> tuple[float, float]:
        return (
            offset.x_min + float(point[0]) * self.scale_x,
            offset.y_min + float(point[1]) * self.scale_y,
        )
