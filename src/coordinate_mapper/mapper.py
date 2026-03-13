from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CoordinateMapper:
    """Maps puzzle-grid coordinates to machine coordinates."""

    def map_to_machine(self, points: list[tuple[int, int]]) -> list[tuple[float, float]]:
        """
        Map grid points to machine-space points.
        Replace this placeholder with your calibration and transform logic.
        """
        logger.info("Mapping %d grid points to machine coordinates", len(points))
        machine_points = [(float(x), float(y)) for x, y in points]
        logger.debug("Mapped machine points: %s", machine_points)
        return machine_points
