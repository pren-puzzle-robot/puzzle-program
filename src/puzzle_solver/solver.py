from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
import shutil
from typing import Iterable

import cv2 as cv
import numpy as np
from shapely import affinity
from shapely.geometry import GeometryCollection, MultiPolygon
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from puzzle_models import SolverPlacement

logger = logging.getLogger(__name__)


TARGET_ASPECT_RATIO = 1.0 / math.sqrt(2.0)


@dataclass(frozen=True)
class ExtractedPiece:
    piece_id: int
    polygon: ShapelyPolygon
    start: tuple[float, float]

    @property
    def area(self) -> float:
        return float(self.polygon.area)


@dataclass(frozen=True)
class OrientedPiece:
    piece_id: int
    polygon: ShapelyPolygon
    rotation: float
    centroid: tuple[float, float]
    width: float
    height: float


@dataclass(frozen=True)
class PlacedPiece:
    piece_id: int
    polygon: ShapelyPolygon
    end: tuple[float, float]
    rotation: float


class PuzzleSolver:
    """Extract puzzle pieces as Shapely polygons and pack them tightly."""

    def __init__(
        self,
        output_dir: str | None = None,
        variant: str = "fast",
        min_area: int | str = 60000,
        threshold_value: int | str | None = 140,
        clearance: float = 0.0,
        aspect_tolerance: float = 0.08,
        simplify_tolerance: float = 12.0,
        max_overlap_ratio: float = 0.08,
        max_empty_ratio: float = 0.10,
    ) -> None:
        self.output_dir = (
            Path(output_dir) if output_dir is not None else Path(__file__).with_name("output")
        )
        self.variant = variant
        self.min_area = self._validate_min_area(min_area)
        self.threshold_value = self._validate_threshold(threshold_value)
        self.clearance = float(clearance)
        self.aspect_tolerance = float(aspect_tolerance)
        self.simplify_tolerance = float(simplify_tolerance)
        self.max_overlap_ratio = float(max_overlap_ratio)
        self.max_empty_ratio = float(max_empty_ratio)

        if self.clearance < 0:
            raise ValueError("clearance must be non-negative")
        if not 0.0 <= self.max_overlap_ratio <= 0.2:
            raise ValueError("max_overlap_ratio must be between 0.0 and 0.2")
        if not 0.0 <= self.max_empty_ratio < 1.0:
            raise ValueError("max_empty_ratio must be between 0.0 and 1.0")

    def solve(self, frame: str) -> list[SolverPlacement]:
        """Solve a captured puzzle image into pick-and-place instructions."""
        logger.info("Solving puzzle from frame %s", frame)
        self._prepare_output_dir()

        image = cv.imread(frame)
        if image is None:
            raise RuntimeError(f"Could not read puzzle image: {frame}")

        pieces = self._extract_pieces(image)
        if not pieces:
            raise ValueError("No puzzle pieces were detected in the image")

        logger.info("Extracted %d Shapely puzzle polygons", len(pieces))

        placed_pieces = self._shift_layout_to_origin(self._pack_pieces(pieces))
        self._save_solution_debug_image(placed_pieces)
        self._save_solution_debug_json(pieces, placed_pieces)

        by_id = {piece.piece_id: piece for piece in pieces}
        solution = [
            SolverPlacement(
                piece_id=placed_piece.piece_id,
                start=by_id[placed_piece.piece_id].start,
                end=(
                    float(round(placed_piece.end[0])),
                    float(round(placed_piece.end[1])),
                ),
                rotation=float(placed_piece.rotation),
            )
            for placed_piece in placed_pieces
        ]

        logger.debug("Solver placement plan: %s", solution)
        return solution

    def _prepare_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for path in self.output_dir.iterdir():
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

    @staticmethod
    def _validate_min_area(min_area: int | str) -> int:
        if isinstance(min_area, str):
            min_area = min_area.strip()

        try:
            resolved_min_area = int(min_area)
        except (TypeError, ValueError) as exc:
            raise ValueError("min_area must be an integer") from exc

        if resolved_min_area < 0:
            raise ValueError("min_area must be non-negative")

        return resolved_min_area

    @staticmethod
    def _validate_threshold(threshold_value: int | str | None) -> int | None:
        if threshold_value is None:
            return None

        if isinstance(threshold_value, str):
            normalized = threshold_value.strip().lower()
            if normalized in {"", "none", "otsu"}:
                return None
            try:
                threshold_value = int(normalized)
            except ValueError as exc:
                raise ValueError(
                    "threshold_value must be an integer, 'none', or 'otsu'"
                ) from exc

        if not isinstance(threshold_value, int):
            raise ValueError("threshold_value must be an integer, 'none', or 'otsu'")

        if not 0 <= threshold_value <= 255:
            raise ValueError("threshold_value must be between 0 and 255")
        return threshold_value

    def _extract_pieces(self, image: np.ndarray) -> list[ExtractedPiece]:
        mask = self._segment_image(image)
        cv.imwrite(str(self.output_dir / "foreground_mask.png"), mask)

        contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE)
        contours = [contour for contour in contours if cv.contourArea(contour) >= self.min_area]
        contours.sort(key=lambda contour: cv.boundingRect(contour)[:2])

        pieces: list[ExtractedPiece] = []
        for piece_id, contour in enumerate(contours):
            polygon = self._contour_to_polygon(contour)
            if polygon is None or polygon.area < self.min_area:
                continue

            centroid = polygon.centroid
            pieces.append(
                ExtractedPiece(
                    piece_id=piece_id,
                    polygon=polygon,
                    start=(float(centroid.x), float(centroid.y)),
                )
            )

        self._save_extraction_debug_image(image, pieces)
        return pieces

    def _segment_image(self, image: np.ndarray) -> np.ndarray:
        gray = self._preprocess_image(image)
        if self.threshold_value is not None:
            return self._segment_foreground(gray, self.threshold_value)

        candidates: list[tuple[int | None, np.ndarray, list[np.ndarray]]] = []
        for threshold in (None, 80, 100, 120, 140, 160, 180, 200, 220):
            mask = self._segment_foreground(gray, threshold)
            contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE)
            contours = [
                contour for contour in contours if cv.contourArea(contour) >= self.min_area
            ]
            candidates.append((threshold, mask, contours))

        threshold, best_mask, best_contours = max(
            candidates,
            key=lambda candidate: self._segmentation_score(candidate[2]),
        )
        logger.info(
            "Selected %s threshold with %d detected pieces",
            "Otsu" if threshold is None else threshold,
            len(best_contours),
        )
        return best_mask

    @staticmethod
    def _preprocess_image(image: np.ndarray) -> np.ndarray:
        lab = cv.cvtColor(image, cv.COLOR_BGR2LAB)
        lightness, channel_a, channel_b = cv.split(lab)
        clahe = cv.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        lightness = clahe.apply(lightness)
        equalized = cv.cvtColor(cv.merge([lightness, channel_a, channel_b]), cv.COLOR_LAB2BGR)
        blurred = cv.GaussianBlur(equalized, (5, 5), 0)
        return cv.cvtColor(blurred, cv.COLOR_BGR2GRAY)

    @classmethod
    def _segment_foreground(cls, gray: np.ndarray, threshold_value: int | None) -> np.ndarray:
        if threshold_value is None:
            _, mask = cv.threshold(gray, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
        else:
            _, mask = cv.threshold(gray, threshold_value, 255, cv.THRESH_BINARY)

        mask = cls._select_foreground_polarity(mask)
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5))
        mask = cv.morphologyEx(mask, cv.MORPH_OPEN, kernel, iterations=2)
        mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(mask)
        cv.drawContours(filled, contours, -1, 255, thickness=cv.FILLED)
        return filled

    @staticmethod
    def _select_foreground_polarity(mask: np.ndarray) -> np.ndarray:
        inverted = cv.bitwise_not(mask)

        def border_white_fraction(candidate: np.ndarray) -> float:
            border = np.concatenate(
                (candidate[0, :], candidate[-1, :], candidate[:, 0], candidate[:, -1])
            )
            return float(np.count_nonzero(border)) / float(border.size)

        if border_white_fraction(inverted) < border_white_fraction(mask):
            return inverted
        return mask

    @staticmethod
    def _segmentation_score(contours: list[np.ndarray]) -> tuple[int, int, float]:
        count = len(contours)
        expected_count_score = 2 if count in {4, 6} else 1 if count > 0 else 0
        total_area = sum(float(cv.contourArea(contour)) for contour in contours)
        return (expected_count_score, count, total_area)

    def _contour_to_polygon(self, contour: np.ndarray) -> ShapelyPolygon | None:
        points = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
        if len(points) < 3:
            return None

        polygon = self._largest_polygon(ShapelyPolygon(points))
        if polygon is None:
            return None

        if self.simplify_tolerance > 0:
            simplified = polygon.simplify(
                self.simplify_tolerance,
                preserve_topology=True,
            )
            polygon = self._largest_polygon(simplified) or polygon

        return orient(polygon, sign=1.0)

    @classmethod
    def _largest_polygon(cls, geometry: BaseGeometry) -> ShapelyPolygon | None:
        if geometry.is_empty:
            return None

        if not geometry.is_valid:
            geometry = geometry.buffer(0)

        if geometry.is_empty:
            return None

        if isinstance(geometry, ShapelyPolygon):
            return geometry if geometry.area > 0 else None

        if isinstance(geometry, MultiPolygon):
            return max(geometry.geoms, key=lambda polygon: polygon.area, default=None)

        if isinstance(geometry, GeometryCollection):
            polygons = [geom for geom in geometry.geoms if isinstance(geom, ShapelyPolygon)]
            return max(polygons, key=lambda polygon: polygon.area, default=None)

        return None

    def _pack_pieces(self, pieces: list[ExtractedPiece]) -> list[PlacedPiece]:
        orientation_options = {
            piece.piece_id: self._build_orientation_options(piece) for piece in pieces
        }

        lower_area = max(sum(piece.area for piece in pieces), 1.0)
        low_area = lower_area
        high_area = lower_area
        best_layout: list[PlacedPiece] | None = None

        for _ in range(30):
            layout = self._try_pack_area(high_area, pieces, orientation_options)
            if layout is not None:
                best_layout = layout
                break
            high_area *= 1.3

        if best_layout is None:
            raise RuntimeError("Could not find an acceptable layout for the puzzle pieces")

        for _ in range(12):
            mid_area = (low_area + high_area) / 2.0
            layout = self._try_pack_area(mid_area, pieces, orientation_options)
            if layout is None:
                low_area = mid_area
            else:
                high_area = mid_area
                best_layout = layout

        assert best_layout is not None
        best_score = self._layout_score(best_layout, exact_empty=True)

        for factor in (1.0, 1.05, 1.1, 1.2, 1.35):
            layout = self._try_pack_area(high_area * factor, pieces, orientation_options)
            if layout is None:
                continue
            score = self._layout_score(layout, exact_empty=True)
            if score < best_score:
                best_layout = layout
                best_score = score

        width, height = self._layout_size(best_layout)
        empty_area_ratio = self._empty_area_ratio(best_layout)
        logger.info(
            "Packed %d pieces into %.1fx%.1f layout; aspect ratio %.3f; empty area %.1f%%",
            len(best_layout),
            width,
            height,
            width / height if height else 0.0,
            empty_area_ratio * 100.0,
        )
        if empty_area_ratio > self.max_empty_ratio:
            logger.warning(
                "Best layout has %.1f%% empty area, above configured %.1f%% limit",
                empty_area_ratio * 100.0,
                self.max_empty_ratio * 100.0,
            )
        return best_layout

    def _try_pack_area(
        self,
        area: float,
        pieces: list[ExtractedPiece],
        orientation_options: dict[int, list[OrientedPiece]],
    ) -> list[PlacedPiece] | None:
        width = math.sqrt(area * TARGET_ASPECT_RATIO)
        height = width / TARGET_ASPECT_RATIO
        return self._try_pack_container(width, height, pieces, orientation_options)

    def _try_pack_container(
        self,
        width: float,
        height: float,
        pieces: list[ExtractedPiece],
        orientation_options: dict[int, list[OrientedPiece]],
    ) -> list[PlacedPiece] | None:
        best_layout: list[PlacedPiece] | None = None
        best_score: tuple[float, float, float, float] | None = None

        for order in self._candidate_orders(pieces, orientation_options):
            layout = self._pack_order(order, width, height, orientation_options)
            if layout is None:
                continue

            score = self._layout_score(layout, exact_empty=True)
            if best_score is None or score < best_score:
                best_layout = layout
                best_score = score

        return best_layout

    def _candidate_orders(
        self,
        pieces: list[ExtractedPiece],
        orientation_options: dict[int, list[OrientedPiece]],
    ) -> list[list[int]]:
        by_id = {piece.piece_id: piece for piece in pieces}

        def max_width(piece_id: int) -> float:
            return max(option.width for option in orientation_options[piece_id])

        def max_height(piece_id: int) -> float:
            return max(option.height for option in orientation_options[piece_id])

        raw_orders = [
            [piece.piece_id for piece in pieces],
            [piece.piece_id for piece in sorted(pieces, key=lambda piece: -piece.area)],
            sorted(by_id, key=max_width, reverse=True),
            sorted(by_id, key=max_height, reverse=True),
            sorted(by_id, key=lambda piece_id: -(max_width(piece_id) * max_height(piece_id))),
        ]

        unique_orders: list[list[int]] = []
        seen: set[tuple[int, ...]] = set()
        for order in raw_orders:
            key = tuple(order)
            if key not in seen:
                unique_orders.append(order)
                seen.add(key)

        return unique_orders

    def _pack_order(
        self,
        order: list[int],
        width: float,
        height: float,
        orientation_options: dict[int, list[OrientedPiece]],
    ) -> list[PlacedPiece] | None:
        placed: list[PlacedPiece] = []
        for piece_id in order:
            next_piece = self._place_piece(piece_id, width, height, placed, orientation_options)
            if next_piece is None:
                return None
            placed.append(next_piece)
        return placed

    def _place_piece(
        self,
        piece_id: int,
        width: float,
        height: float,
        placed: list[PlacedPiece],
        orientation_options: dict[int, list[OrientedPiece]],
    ) -> PlacedPiece | None:
        best_piece: PlacedPiece | None = None
        best_score: tuple[float, float, float, float, float] | None = None

        for option in orientation_options[piece_id]:
            x_candidates = self._candidate_axis_positions(width, option.width, placed, "x")
            y_candidates = self._candidate_axis_positions(height, option.height, placed, "y")

            for y in y_candidates:
                for x in x_candidates:
                    candidate = self._translate_option(option, x, y)
                    if not self._fits_container(candidate.polygon, width, height):
                        continue
                    if self._overlaps_existing(candidate.polygon, placed):
                        continue

                    score = self._placement_score(candidate, placed)
                    if best_score is None or score < best_score:
                        best_piece = candidate
                        best_score = score

        return best_piece

    def _candidate_axis_positions(
        self,
        container_size: float,
        item_size: float,
        placed: list[PlacedPiece],
        axis: str,
    ) -> list[float]:
        values = {0.0, max(0.0, container_size - item_size)}
        offsets = self._axis_overlap_offsets(item_size)
        for placed_piece in placed:
            minx, miny, maxx, maxy = placed_piece.polygon.bounds
            if axis == "x":
                values.add(minx)
                values.add(max(0.0, maxx - item_size))
                for offset in offsets:
                    values.add(maxx + offset)
                    values.add(minx - item_size - offset)
            else:
                values.add(miny)
                values.add(max(0.0, maxy - item_size))
                for offset in offsets:
                    values.add(maxy + offset)
                    values.add(miny - item_size - offset)

        return sorted(
            {
                float(round(value, 3))
                for value in values
                if -1e-6 <= value <= container_size - item_size + 1e-6
            }
        )

    def _axis_overlap_offsets(self, item_size: float) -> list[float]:
        if self.max_overlap_ratio <= 0:
            return [self.clearance]

        overlap = item_size * self.max_overlap_ratio
        return [
            self.clearance,
            0.0,
            -overlap * 0.5,
            -overlap,
            -overlap * 1.5,
        ]

    @staticmethod
    def _translate_option(option: OrientedPiece, x: float, y: float) -> PlacedPiece:
        polygon = affinity.translate(option.polygon, xoff=x, yoff=y)
        return PlacedPiece(
            piece_id=option.piece_id,
            polygon=polygon,
            end=(float(option.centroid[0] + x), float(option.centroid[1] + y)),
            rotation=option.rotation,
        )

    @staticmethod
    def _fits_container(polygon: ShapelyPolygon, width: float, height: float) -> bool:
        minx, miny, maxx, maxy = polygon.bounds
        return minx >= -1e-6 and miny >= -1e-6 and maxx <= width + 1e-6 and maxy <= height + 1e-6

    def _overlaps_existing(
        self,
        polygon: ShapelyPolygon,
        placed: list[PlacedPiece],
    ) -> bool:
        candidate_overlap = 0.0
        candidate_allowed_overlap = self.max_overlap_ratio * polygon.area
        for placed_piece in placed:
            candidate_bounds = polygon.bounds
            placed_bounds = placed_piece.polygon.bounds
            bounds_intersect = self._bounds_intersect(candidate_bounds, placed_bounds)
            if (
                not bounds_intersect
                and not self._expanded_bounds_intersect(candidate_bounds, placed_bounds)
            ):
                continue

            overlap_area = 0.0
            if bounds_intersect:
                overlap_area = float(polygon.intersection(placed_piece.polygon).area)

            if self.max_overlap_ratio <= 0 and overlap_area > 1e-6:
                return True
            pair_allowed_overlap = self.max_overlap_ratio * min(
                polygon.area,
                placed_piece.polygon.area,
            )
            if overlap_area > pair_allowed_overlap + 1e-6:
                return True

            candidate_overlap += overlap_area
            if candidate_overlap > candidate_allowed_overlap + 1e-6:
                return True

            if (
                overlap_area <= 1e-6
                and self.clearance > 0
                and polygon.distance(placed_piece.polygon) < self.clearance - 1e-6
            ):
                return True
        return False

    @staticmethod
    def _bounds_intersect(
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
    ) -> bool:
        first_minx, first_miny, first_maxx, first_maxy = first
        second_minx, second_miny, second_maxx, second_maxy = second
        return not (
            first_maxx < second_minx
            or second_maxx < first_minx
            or first_maxy < second_miny
            or second_maxy < first_miny
        )

    def _expanded_bounds_intersect(
        self,
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
    ) -> bool:
        first_minx, first_miny, first_maxx, first_maxy = first
        second_minx, second_miny, second_maxx, second_maxy = second
        gap = self.clearance
        if self.max_overlap_ratio > 0:
            max_first_size = max(first[2] - first[0], first[3] - first[1])
            max_second_size = max(second[2] - second[0], second[3] - second[1])
            gap -= max(max_first_size, max_second_size) * self.max_overlap_ratio * 1.5
        return not (
            first_maxx + gap < second_minx
            or second_maxx + gap < first_minx
            or first_maxy + gap < second_miny
            or second_maxy + gap < first_miny
        )

    def _placement_score(
        self,
        candidate: PlacedPiece,
        placed: list[PlacedPiece],
    ) -> tuple[float, float, float, float, float]:
        layout = [*placed, candidate]
        base_score = self._partial_layout_score(layout)
        return (
            base_score[0],
            base_score[1],
            base_score[2],
            base_score[3],
            candidate.rotation % (2.0 * math.pi),
        )

    def _build_orientation_options(self, piece: ExtractedPiece) -> list[OrientedPiece]:
        angles = self._candidate_angles(piece.polygon)
        options = [self._build_oriented_piece(piece, angle) for angle in angles]
        options.sort(key=lambda option: (option.width * option.height, option.height, option.width))
        return options

    def _candidate_angles(self, polygon: ShapelyPolygon) -> list[float]:
        angles = {self._normalize_angle(index * math.pi / 4.0) for index in range(8)}

        min_rect = polygon.minimum_rotated_rectangle
        coords = list(min_rect.exterior.coords)
        for index in range(min(4, len(coords) - 1)):
            x1, y1 = coords[index]
            x2, y2 = coords[index + 1]
            edge_angle = math.atan2(y2 - y1, x2 - x1)
            angles.add(self._normalize_angle(-edge_angle))
            angles.add(self._normalize_angle(math.pi / 2.0 - edge_angle))

        if self.variant.strip().lower() in {"quality", "precise", "best"}:
            angles.update(self._normalize_angle(index * math.pi / 8.0) for index in range(16))

        return sorted(angles)

    @staticmethod
    def _normalize_angle(angle: float) -> float:
        tau = 2.0 * math.pi
        normalized = angle % tau
        if math.isclose(normalized, tau, abs_tol=1e-9):
            return 0.0
        return normalized

    @staticmethod
    def _build_oriented_piece(piece: ExtractedPiece, angle: float) -> OrientedPiece:
        rotated = affinity.rotate(
            piece.polygon,
            angle,
            origin=piece.start,
            use_radians=True,
        )
        minx, miny, maxx, maxy = rotated.bounds
        local_polygon = affinity.translate(rotated, xoff=-minx, yoff=-miny)
        centroid = local_polygon.centroid
        return OrientedPiece(
            piece_id=piece.piece_id,
            polygon=local_polygon,
            rotation=angle,
            centroid=(float(centroid.x), float(centroid.y)),
            width=float(maxx - minx),
            height=float(maxy - miny),
        )

    @staticmethod
    def _shift_layout_to_origin(placed: list[PlacedPiece]) -> list[PlacedPiece]:
        minx, miny, _, _ = PuzzleSolver._layout_bounds(placed)
        return [
            PlacedPiece(
                piece_id=piece.piece_id,
                polygon=affinity.translate(piece.polygon, xoff=-minx, yoff=-miny),
                end=(float(piece.end[0] - minx), float(piece.end[1] - miny)),
                rotation=piece.rotation,
            )
            for piece in placed
        ]

    @staticmethod
    def _layout_bounds(placed: Iterable[PlacedPiece]) -> tuple[float, float, float, float]:
        pieces = list(placed)
        if not pieces:
            return (0.0, 0.0, 0.0, 0.0)

        minx = min(piece.polygon.bounds[0] for piece in pieces)
        miny = min(piece.polygon.bounds[1] for piece in pieces)
        maxx = max(piece.polygon.bounds[2] for piece in pieces)
        maxy = max(piece.polygon.bounds[3] for piece in pieces)
        return (float(minx), float(miny), float(maxx), float(maxy))

    @staticmethod
    def _layout_size(placed: Iterable[PlacedPiece]) -> tuple[float, float]:
        minx, miny, maxx, maxy = PuzzleSolver._layout_bounds(placed)
        return (float(maxx - minx), float(maxy - miny))

    def _layout_score(
        self,
        placed: list[PlacedPiece],
        exact_empty: bool,
    ) -> tuple[float, float, float, float]:
        width, height = self._layout_size(placed)
        if width <= 0 or height <= 0:
            return (float("inf"), float("inf"), float("inf"), float("inf"))

        aspect = width / height
        relative_aspect_error = abs(aspect - TARGET_ASPECT_RATIO) / TARGET_ASPECT_RATIO
        aspect_violation = max(0.0, relative_aspect_error - self.aspect_tolerance)
        empty_ratio = (
            self._empty_area_ratio(placed)
            if exact_empty
            else self._estimated_empty_area_ratio(placed)
        )
        empty_violation = max(0.0, empty_ratio - self.max_empty_ratio)
        adjusted_area = self._adjusted_area_for_size(width, height)
        actual_area = width * height
        return (empty_violation, aspect_violation, empty_ratio, adjusted_area + actual_area)

    def _partial_layout_score(self, placed: list[PlacedPiece]) -> tuple[float, float, float, float]:
        width, height = self._layout_size(placed)
        if width <= 0 or height <= 0:
            return (float("inf"), float("inf"), float("inf"), float("inf"))

        aspect = width / height
        relative_aspect_error = abs(aspect - TARGET_ASPECT_RATIO) / TARGET_ASPECT_RATIO
        aspect_violation = max(0.0, relative_aspect_error - self.aspect_tolerance)
        adjusted_area = self._adjusted_area_for_size(width, height)
        actual_area = width * height
        return (aspect_violation, adjusted_area, relative_aspect_error, actual_area)

    def _empty_area_ratio(self, placed: list[PlacedPiece]) -> float:
        width, height = self._layout_size(placed)
        layout_area = width * height
        if layout_area <= 0:
            return 0.0

        occupied_area = float(unary_union([piece.polygon for piece in placed]).area)
        return max(0.0, min(1.0, (layout_area - occupied_area) / layout_area))

    def _estimated_empty_area_ratio(self, placed: list[PlacedPiece]) -> float:
        width, height = self._layout_size(placed)
        layout_area = width * height
        if layout_area <= 0:
            return 0.0

        # This is an optimistic upper-bound estimate for occupied area. It is
        # cheap enough for per-candidate scoring; final layouts use union area.
        occupied_area = sum(float(piece.polygon.area) for piece in placed)
        return max(0.0, min(1.0, (layout_area - occupied_area) / layout_area))

    @staticmethod
    def _adjusted_area_for_size(width: float, height: float) -> float:
        if width <= 0 or height <= 0:
            return float("inf")

        aspect = width / height
        if aspect > TARGET_ASPECT_RATIO:
            height = width / TARGET_ASPECT_RATIO
        else:
            width = height * TARGET_ASPECT_RATIO
        return float(width * height)

    def _save_extraction_debug_image(
        self,
        image: np.ndarray,
        pieces: list[ExtractedPiece],
    ) -> None:
        debug = image.copy()
        for piece in pieces:
            points = np.rint(np.asarray(piece.polygon.exterior.coords, dtype=np.float64)).astype(
                np.int32
            )
            cv.polylines(debug, [points], True, (0, 255, 255), 4)
            cv.putText(
                debug,
                str(piece.piece_id),
                (int(round(piece.start[0])), int(round(piece.start[1]))),
                cv.FONT_HERSHEY_SIMPLEX,
                2.0,
                (0, 0, 255),
                4,
            )

        cv.imwrite(str(self.output_dir / "extracted_pieces.png"), debug)

    def _save_solution_debug_image(self, placed: list[PlacedPiece]) -> None:
        minx, miny, maxx, maxy = self._layout_bounds(placed)
        margin = 40
        width = max(1, int(math.ceil(maxx - minx)) + 2 * margin)
        height = max(1, int(math.ceil(maxy - miny)) + 2 * margin)
        image = np.full((height, width, 3), 255, dtype=np.uint8)

        for piece in placed:
            color = self._debug_color(piece.piece_id)
            exterior = np.asarray(piece.polygon.exterior.coords, dtype=np.float64)
            exterior[:, 0] = exterior[:, 0] - minx + margin
            exterior[:, 1] = exterior[:, 1] - miny + margin
            points = np.rint(exterior).astype(np.int32)
            cv.fillPoly(image, [points], color)
            cv.polylines(image, [points], True, (0, 0, 0), 2)
            cv.circle(
                image,
                (
                    int(round(piece.end[0] - minx + margin)),
                    int(round(piece.end[1] - miny + margin)),
                ),
                5,
                (0, 0, 0),
                -1,
            )
            cv.putText(
                image,
                str(piece.piece_id),
                (
                    int(round(piece.end[0] - minx + margin + 8)),
                    int(round(piece.end[1] - miny + margin - 8)),
                ),
                cv.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 0),
                2,
            )

        cv.rectangle(image, (margin, margin), (width - margin, height - margin), (80, 80, 80), 2)
        cv.imwrite(str(self.output_dir / "solved_puzzle.png"), image)

    @staticmethod
    def _debug_color(piece_id: int) -> tuple[int, int, int]:
        rng = np.random.default_rng(piece_id + 101)
        color = rng.integers(70, 220, size=3)
        return (int(color[0]), int(color[1]), int(color[2]))

    def _save_solution_debug_json(
        self,
        pieces: list[ExtractedPiece],
        placed: list[PlacedPiece],
    ) -> None:
        source_by_id = {piece.piece_id: piece for piece in pieces}
        width, height = self._layout_size(placed)
        empty_area_ratio = self._empty_area_ratio(placed)
        payload = {
            "target_aspect_ratio": TARGET_ASPECT_RATIO,
            "layout_width": width,
            "layout_height": height,
            "layout_aspect_ratio": width / height if height else None,
            "empty_area_ratio": empty_area_ratio,
            "max_empty_ratio": self.max_empty_ratio,
            "clearance": self.clearance,
            "max_overlap_ratio": self.max_overlap_ratio,
            "placements": [
                {
                    "piece_id": piece.piece_id,
                    "start": source_by_id[piece.piece_id].start,
                    "end": piece.end,
                    "rotation": piece.rotation,
                }
                for piece in placed
            ],
        }
        with open(self.output_dir / "placements.json", "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)


__all__ = ["PuzzleSolver"]
