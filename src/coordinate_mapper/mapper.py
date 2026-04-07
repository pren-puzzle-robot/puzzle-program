from __future__ import annotations

import logging

from puzzle_models import MachinePlacement, SolverPlacement

logger = logging.getLogger(__name__)


class CoordinateMapper:
    """Maps puzzle-grid coordinates to machine coordinates."""

    def map_to_machine(
        self,
        placements: list[SolverPlacement],
    ) -> list[MachinePlacement]:
        """
        Map solver placements to machine-space coordinates.
        Replace this placeholder with your calibration and transform logic.
        """
        logger.info("Mapping %d solver placements to machine coordinates", len(placements))
        machine_points = [
            MachinePlacement(
                piece_id=placement.piece_id,
                start=(
                    float(placement.start[0]),
                    float(placement.start[1]),
                ),
                end=(
                    float(placement.end[0]),
                    float(placement.end[1]),
                ),
                rotation=float(placement.rotation),
            )
            for placement in placements
        ]
        logger.debug("Mapped machine placements: %s", machine_points)
        return machine_points
