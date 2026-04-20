from __future__ import annotations

import copy
import logging
import math
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
        min_area: int | str = 60000,
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

    def _save_debug_image(
        self,
        puzzle_pieces: dict[int, PuzzlePiece],
        filename: str = "solved_puzzle.png",
    ) -> None:
        debug_image = print_whole_puzzle_image(puzzle_pieces)
        debug_path = self.output_dir / filename
        debug_image.save(debug_path)
        logger.info("Saved solved puzzle debug image to %s", debug_path)

    @staticmethod
    def _get_layout_bounds(
        puzzle_pieces: dict[int, PuzzlePiece],
    ) -> tuple[float, float, float, float]:
        vertices = [
            vertex
            for piece in puzzle_pieces.values()
            for vertex in piece.polygon.vertices
        ]
        min_x = min(vertex.x for vertex in vertices)
        min_y = min(vertex.y for vertex in vertices)
        max_x = max(vertex.x for vertex in vertices)
        max_y = max(vertex.y for vertex in vertices)
        return min_x, min_y, max_x, max_y

    @staticmethod
    def _transform_layout_point(
        x: float,
        y: float,
        min_x: float,
        min_y: float,
        rotate_to_landscape: bool,
        original_height: float,
    ) -> tuple[float, float]:
        local_x = x - min_x
        local_y = y - min_y
        if rotate_to_landscape:
            local_x, local_y = original_height - local_y, local_x
        return (local_x, local_y)

    def _build_normalized_debug_pieces(
        self,
        puzzle_pieces: dict[int, PuzzlePiece],
        normalized_rotations: dict[int, float],
        rotate_to_landscape: bool,
        min_x: float,
        min_y: float,
        height: float,
    ) -> dict[int, PuzzlePiece]:
        debug_pieces = copy.deepcopy(puzzle_pieces)
        for piece_id, piece in debug_pieces.items():
            transformed_points = [
                Point(
                    *self._transform_layout_point(
                        vertex.x,
                        vertex.y,
                        min_x,
                        min_y,
                        rotate_to_landscape,
                        height,
                    )
                )
                for vertex in piece.polygon.vertices
            ]
            normalized_piece = PuzzlePiece(transformed_points)
            normalized_piece._rotation = normalized_rotations[piece_id]
            debug_pieces[piece_id] = normalized_piece
        return debug_pieces

    def _normalize_end_layout(
        self,
        puzzle_pieces: dict[int, PuzzlePiece],
        ordered_piece_ids: list[int],
    ) -> tuple[dict[int, tuple[float, float]], dict[int, float], dict[int, PuzzlePiece]]:
        min_x, min_y, max_x, max_y = self._get_layout_bounds(puzzle_pieces)
        width = max_x - min_x
        height = max_y - min_y
        rotate_to_landscape = height > width

        transformed_centers = {
            piece_id: self._transform_layout_point(
                puzzle_pieces[piece_id].polygon.centroid().x,
                puzzle_pieces[piece_id].polygon.centroid().y,
                min_x,
                min_y,
                rotate_to_landscape,
                height,
            )
            for piece_id in ordered_piece_ids
        }
        transformed_rotations = {
            piece_id: (
                puzzle_pieces[piece_id].rotation + (math.pi / 2 if rotate_to_landscape else 0.0)
            )
            for piece_id in ordered_piece_ids
        }
        normalized_debug_pieces = self._build_normalized_debug_pieces(
            puzzle_pieces,
            transformed_rotations,
            rotate_to_landscape,
            min_x,
            min_y,
            height,
        )

        logger.info(
            "Normalized solved puzzle layout by aspect ratio%s",
            " with 90 degree rotation to landscape" if rotate_to_landscape else "",
        )
        return transformed_centers, transformed_rotations, normalized_debug_pieces

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

        if len(piece_images) != 4 and len(piece_images) != 6:
            raise ValueError(f"Unexpected number of piece images: {len(piece_images)}")

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
        normalized_end_positions, normalized_rotations, normalized_debug_pieces = (
            self._normalize_end_layout(
            puzzle_pieces,
            ordered_piece_ids,
            )
        )
        self._save_debug_image(normalized_debug_pieces, "solved_puzzle_normalized.png")

        solution = [
            SolverPlacement(
                piece_id=piece_id,
                start=(
                    float(start_positions[piece_id][0]),
                    float(start_positions[piece_id][1]),
                ),
                end=(
                    float(round(normalized_end_positions[piece_id][0])),
                    float(round(normalized_end_positions[piece_id][1])),
                ),
                rotation=float(normalized_rotations[piece_id]),
            )
            for piece_id in ordered_piece_ids
        ]
        logger.debug("Solver placement plan: %s", solution)

        return solution
