from __future__ import annotations

import logging
from pathlib import Path
import shutil

import cv2 as cv

from puzzle_models import SolverPlacement

from .component import PuzzlePiece, Point
from .corners import detect_corners
from .greedy import Greedy
from .match import Match
from .pull_pieces import pull_pieces
from .utilities import Solver, print_whole_puzzle_image

logger = logging.getLogger(__name__)


class PuzzleSolver:
    """Contains puzzle-solving logic."""

    def __init__(
        self,
        output_dir: str | None = None,
        variant: str = "fast",
        min_area: int = 200000,
        threshold_value: int | str | None = 140,
    ) -> None:
        self.output_dir = (
            Path(output_dir) if output_dir is not None else Path(__file__).with_name("output")
        )
        self.variant = variant
        self.min_area = min_area
        self.threshold_value = threshold_value

    def _prepare_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for path in self.output_dir.iterdir():
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

    def _build_puzzle_pieces(
        self, corners: list[tuple[str, list[tuple[int, int]]]]
    ) -> dict[int, PuzzlePiece]:
        puzzle_pieces: dict[int, PuzzlePiece] = {}
        for index, (filename, corner_list) in enumerate(corners):
            points = [Point(x=float(x), y=float(y)) for x, y in corner_list]
            piece = PuzzlePiece(points)
            puzzle_pieces[index] = piece
            logger.debug("Created PuzzlePiece %d from %s", index, filename)

        return puzzle_pieces

    def _create_solver(self, puzzle_pieces: dict[int, PuzzlePiece]) -> Solver:
        if self.variant == "greedy":
            return Greedy(puzzle_pieces)

        return Match()

    def _save_debug_image(self, puzzle_pieces: dict[int, PuzzlePiece]) -> None:
        debug_image = print_whole_puzzle_image(puzzle_pieces)
        debug_path = self.output_dir / "solved_puzzle.png"
        debug_image.save(debug_path)
        logger.info("Saved solved puzzle debug image to %s", debug_path)

    def solve(self, frame: str) -> list[SolverPlacement]:
        """Run the current simulator-style solver pipeline for a captured image."""
        logger.info("Solving puzzle from frame %s", frame)
        self._prepare_output_dir()

        image = cv.imread(frame)
        if image is None:
            raise RuntimeError(f"Could not read puzzle image: {frame}")

        piece_images = pull_pieces(
            image,
            str(self.output_dir),
            min_area=self.min_area,
            threshold_value=self.threshold_value,
        )
        logger.info("Extracted %d piece masks", len(piece_images))

        corners = detect_corners(piece_images, str(self.output_dir))
        logger.info("Detected corners for %d pieces", len(corners))

        puzzle_pieces = self._build_puzzle_pieces(corners)
        start_positions = {
            piece_id: (
                int(round(piece.polygon.centroid().x)),
                int(round(piece.polygon.centroid().y)),
            )
            for piece_id, piece in puzzle_pieces.items()
        }
        solver = self._create_solver(puzzle_pieces)
        ordered_piece_ids = solver.solve(puzzle_pieces)
        logger.info("Solver produced piece order %s", ordered_piece_ids)
        self._save_debug_image(puzzle_pieces)

        solution = [
            SolverPlacement(
                piece_id=piece_id,
                start=(
                    float(start_positions[piece_id][0]),
                    float(start_positions[piece_id][1]),
                ),
                end=(
                    float(round(puzzle_pieces[piece_id].polygon.centroid().x)),
                    float(round(puzzle_pieces[piece_id].polygon.centroid().y)),
                ),
                rotation=float(puzzle_pieces[piece_id].rotation),
            )
            for piece_id in ordered_piece_ids
        ]
        logger.debug("Solver placement plan: %s", solution)

        return solution
