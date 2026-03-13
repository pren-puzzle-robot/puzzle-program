from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PuzzleSolver:
    """Contains puzzle-solving logic."""

    def solve(self, frame: str) -> list[tuple[int, int]]:
        """
        Solve puzzle state from an input frame reference and return path coordinates.
        Replace this stub with real solving logic.
        """
        logger.info("Solving puzzle from frame %s", frame)
        solution = [(0, 0), (1, 0), (1, 1)]
        logger.debug("Solver path: %s", solution)
        return solution
