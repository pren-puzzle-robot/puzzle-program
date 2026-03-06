from __future__ import annotations


class CoordinateMapper:
    """Maps puzzle-grid coordinates to machine coordinates."""

    def map_to_machine(self, points: list[tuple[int, int]]) -> list[tuple[float, float]]:
        """
        Map grid points to machine-space points.
        Replace this placeholder with your calibration and transform logic.
        """
        return [(float(x), float(y)) for x, y in points]
