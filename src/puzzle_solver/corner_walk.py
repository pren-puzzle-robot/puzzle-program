"""Corner-based frame solver strategy."""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import logging
import math
from typing import Iterable

from shapely.affinity import translate as translate_geometry
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from .component import OuterEdge, Point, PuzzlePiece
from .component.outer_edge import PieceType
from .utilities import Solver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FrameCorner:
    name: str
    point: Point
    rays: tuple[tuple[float, float], tuple[float, float]]


@dataclass(frozen=True)
class _FrameSide:
    name: str
    start: Point
    end: Point
    direction: tuple[float, float]
    length: float
    angle: float


@dataclass(frozen=True)
class _Frame:
    width: float
    height: float
    geometry: BaseGeometry
    corners: tuple[_FrameCorner, ...]
    sides: tuple[_FrameSide, ...]


@dataclass(frozen=True)
class _CornerCandidate:
    piece_id: int
    outer_edge_index: int
    path: tuple[Point, ...]
    corner_index: int
    corner: Point
    leg_angles: tuple[float, float]
    length: float


@dataclass(frozen=True)
class _EdgeCandidate:
    piece_id: int
    outer_edge_index: int
    points: tuple[Point, ...]
    length: float
    first_angle: float


@dataclass(frozen=True)
class _Placement:
    piece_id: int
    outer_edge_index: int
    source_anchor: Point
    rotation: float
    target_anchor: Point
    boundary_points: tuple[Point, ...]
    polygon: BaseGeometry
    bounds: tuple[float, float, float, float]
    area: float
    alignment_error: float


@dataclass(frozen=True)
class _Layout:
    placements: tuple[_Placement, ...]
    score: tuple[float, float, float]


class CornerWalk(Solver):
    """Place detected corner pieces on an A5-ratio frame and score by overlap."""

    TARGET_ASPECT_RATIO = 1.0 / 1.484375 # nicht A5 Seitenverhältnis math.sqrt(2)

    MAX_CORNER_CANDIDATES_PER_PIECE = 12
    MAX_EDGE_CANDIDATES_PER_PIECE = 16
    MAX_CORNER_PLACEMENTS_PER_PIECE_AND_FRAME_CORNER = 8
    INSIDE_FRAME_AREA_TOLERANCE_RATIO = 1e-6

    @classmethod
    def solve(cls, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        solver = cls()
        return solver._solve(puzzle)

    def _solve(self, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        piece_count = len(puzzle)
        if piece_count not in {4, 6}:
            raise RuntimeError(
                f"corner_walk supports exactly 4 or 6 pieces, got {piece_count}"
            )
        if not puzzle:
            return []

        frame = self._derive_frame(puzzle.values())
        corner_placements = self._build_corner_placements(puzzle, frame)
        best = self._find_best_layout(puzzle, frame, corner_placements)
        if best is None:
            raise RuntimeError("corner_walk could not build a corner-based layout")

        self._apply_solution(puzzle, best.placements)
        logger.info(
            "corner_walk selected order %s with overlap %.2f, overflow %.2f, "
            "alignment error %.3f",
            [placement.piece_id for placement in best.placements],
            best.score[0],
            best.score[1],
            best.score[2],
        )
        return [placement.piece_id for placement in best.placements]

    def _derive_frame(self, pieces: Iterable[PuzzlePiece]) -> _Frame:
        piece_area = max(sum(piece.polygon.area() for piece in pieces), 1.0)
        width = math.sqrt(piece_area / self.TARGET_ASPECT_RATIO)
        height = piece_area / width
        geometry = box(0.0, 0.0, width, height)

        bottom_left = Point(0.0, height)
        bottom_right = Point(width, height)
        top_right = Point(width, 0.0)
        top_left = Point(0.0, 0.0)

        corners = (
            _FrameCorner("bottom_left", bottom_left, ((1.0, 0.0), (0.0, -1.0))),
            _FrameCorner("bottom_right", bottom_right, ((0.0, -1.0), (-1.0, 0.0))),
            _FrameCorner("top_right", top_right, ((-1.0, 0.0), (0.0, 1.0))),
            _FrameCorner("top_left", top_left, ((0.0, 1.0), (1.0, 0.0))),
        )
        sides = (
            _FrameSide(
                "bottom",
                bottom_left,
                bottom_right,
                (1.0, 0.0),
                width,
                0.0,
            ),
            _FrameSide(
                "right",
                bottom_right,
                top_right,
                (0.0, -1.0),
                height,
                -math.pi / 2.0,
            ),
            _FrameSide(
                "top",
                top_right,
                top_left,
                (-1.0, 0.0),
                width,
                math.pi,
            ),
            _FrameSide(
                "left",
                top_left,
                bottom_left,
                (0.0, 1.0),
                height,
                math.pi / 2.0,
            ),
        )

        return _Frame(
            width=width,
            height=height,
            geometry=geometry,
            corners=corners,
            sides=sides,
        )

    def _build_corner_placements(
        self,
        puzzle: dict[int, PuzzlePiece],
        frame: _Frame,
    ) -> dict[str, tuple[_Placement, ...]]:
        result: dict[str, tuple[_Placement, ...]] = {}
        candidates_by_piece = {
            piece_id: self._build_corner_candidates(piece_id, piece)
            for piece_id, piece in puzzle.items()
        }

        total_corner_candidates = sum(len(items) for items in candidates_by_piece.values())
        if total_corner_candidates < 4:
            raise RuntimeError(
                "corner_walk needs at least four detected corner candidates"
            )

        for frame_corner in frame.corners:
            placements: list[_Placement] = []
            for piece_id, piece in puzzle.items():
                piece_placements: list[_Placement] = []
                for candidate in candidates_by_piece[piece_id]:
                    for placement in self._place_corner_candidate(
                        piece,
                        candidate,
                        frame_corner,
                    ):
                        fitted = self._fit_inside_frame(placement, frame)
                        if fitted is not None:
                            piece_placements.append(fitted)

                piece_placements.sort(
                    key=lambda placement: (
                        placement.alignment_error,
                        self._overflow_area(placement, frame),
                        -placement.area,
                    )
                )
                placements.extend(
                    piece_placements[
                        : self.MAX_CORNER_PLACEMENTS_PER_PIECE_AND_FRAME_CORNER
                    ]
                )

            placements.sort(
                key=lambda placement: (
                    placement.alignment_error,
                    self._overflow_area(placement, frame),
                    placement.piece_id,
                )
            )
            if not placements:
                raise RuntimeError(
                    f"corner_walk found no placements for {frame_corner.name}"
                )
            result[frame_corner.name] = tuple(placements)

        return result

    def _build_corner_candidates(
        self,
        piece_id: int,
        piece: PuzzlePiece,
    ) -> tuple[_CornerCandidate, ...]:
        candidates: list[_CornerCandidate] = []
        indexed_outer_edges = [
            (outer_edge_index, outer_edge)
            for outer_edge_index, outer_edge in enumerate(piece.possible_outer_edges)
            if outer_edge.type == PieceType.CORNER
        ]
        indexed_outer_edges.sort(key=lambda item: item[1].length, reverse=True)

        for outer_edge_index, outer_edge in indexed_outer_edges[
            : self.MAX_CORNER_CANDIDATES_PER_PIECE
        ]:
            path = self._outer_edge_points(outer_edge, reversed_path=False)
            if len(path) < 3:
                continue

            corner_index = self._corner_index(path)
            corner = path[corner_index]
            previous_point = path[corner_index - 1]
            next_point = path[corner_index + 1]
            if (
                corner.get_distance_between(previous_point) <= 0.0
                or corner.get_distance_between(next_point) <= 0.0
            ):
                continue

            candidates.append(
                _CornerCandidate(
                    piece_id=piece_id,
                    outer_edge_index=outer_edge_index,
                    path=path,
                    corner_index=corner_index,
                    corner=corner,
                    leg_angles=(
                        self._angle(corner, previous_point),
                        self._angle(corner, next_point),
                    ),
                    length=self._path_length(path),
                )
            )

        return tuple(candidates)

    def _place_corner_candidate(
        self,
        piece: PuzzlePiece,
        candidate: _CornerCandidate,
        frame_corner: _FrameCorner,
    ) -> tuple[_Placement, ...]:
        placements: list[_Placement] = []
        target_angles = (
            self._vector_angle(frame_corner.rays[0]),
            self._vector_angle(frame_corner.rays[1]),
        )

        for first_leg, second_leg in ((0, 1), (1, 0)):
            rotation = self._normalize_angle(
                target_angles[0] - candidate.leg_angles[first_leg]
            )
            second_error = abs(
                self._normalize_angle(
                    candidate.leg_angles[second_leg] + rotation - target_angles[1]
                )
            )
            placements.append(
                self._make_placement(
                    piece=piece,
                    piece_id=candidate.piece_id,
                    outer_edge_index=candidate.outer_edge_index,
                    source_anchor=candidate.corner,
                    target_anchor=frame_corner.point,
                    rotation=rotation,
                    boundary_points=candidate.path,
                    alignment_error=second_error,
                )
            )

        return tuple(placements)

    def _find_best_layout(
        self,
        puzzle: dict[int, PuzzlePiece],
        frame: _Frame,
        corner_placements: dict[str, tuple[_Placement, ...]],
    ) -> _Layout | None:
        best: _Layout | None = None
        states: list[tuple[_Placement, ...]] = [()]

        for frame_corner in frame.corners:
            next_states: list[tuple[_Placement, ...]] = []
            for placements in states:
                used_piece_ids = {placement.piece_id for placement in placements}
                for placement in corner_placements[frame_corner.name]:
                    if placement.piece_id in used_piece_ids:
                        continue
                    next_states.append(placements + (placement,))

            states = next_states

        for corner_layout in states:
            if len(puzzle) == 4:
                best = self._choose_better(
                    best,
                    _Layout(corner_layout, self._score_layout(corner_layout, frame)),
                )
                continue

            for complete_layout in self._complete_with_edge_pieces(
                puzzle,
                frame,
                corner_layout,
            ):
                best = self._choose_better(
                    best,
                    _Layout(
                        complete_layout,
                        self._score_layout(complete_layout, frame),
                    ),
                )

        return best

    def _complete_with_edge_pieces(
        self,
        puzzle: dict[int, PuzzlePiece],
        frame: _Frame,
        corner_layout: tuple[_Placement, ...],
    ) -> Iterable[tuple[_Placement, ...]]:
        used_piece_ids = {placement.piece_id for placement in corner_layout}
        remaining_piece_ids = sorted(set(puzzle) - used_piece_ids)
        if len(remaining_piece_ids) != 2:
            return

        edge_candidates_by_piece = {
            piece_id: self._build_edge_candidates(piece_id, puzzle[piece_id])
            for piece_id in remaining_piece_ids
        }
        if any(not edge_candidates for edge_candidates in edge_candidates_by_piece.values()):
            return

        gaps_by_side = {
            side.name: self._side_gap(side, corner_layout, frame)
            for side in frame.sides
        }

        first_piece_id, second_piece_id = remaining_piece_ids
        for first_side, second_side in itertools.permutations(frame.sides, 2):
            first_gap = gaps_by_side[first_side.name]
            second_gap = gaps_by_side[second_side.name]

            for first_candidate in edge_candidates_by_piece[first_piece_id]:
                first_placement = self._place_edge_candidate(
                    puzzle[first_piece_id],
                    first_candidate,
                    first_side,
                    first_gap,
                )
                first_placement = self._fit_inside_side_placement(
                    first_placement,
                    frame,
                    first_side,
                )
                if first_placement is None:
                    continue

                for second_candidate in edge_candidates_by_piece[second_piece_id]:
                    second_placement = self._place_edge_candidate(
                        puzzle[second_piece_id],
                        second_candidate,
                        second_side,
                        second_gap,
                    )
                    second_placement = self._fit_inside_side_placement(
                        second_placement,
                        frame,
                        second_side,
                    )
                    if second_placement is None:
                        continue

                    yield corner_layout + (first_placement, second_placement)

    def _build_edge_candidates(
        self,
        piece_id: int,
        piece: PuzzlePiece,
    ) -> tuple[_EdgeCandidate, ...]:
        candidates: list[_EdgeCandidate] = []
        for outer_edge_index, outer_edge in enumerate(piece.possible_outer_edges):
            if outer_edge.type != PieceType.EDGE:
                continue

            for reversed_path in (False, True):
                points = self._outer_edge_points(outer_edge, reversed_path)
                if len(points) < 2:
                    continue

                length = self._path_length(points)
                if length <= 0.0:
                    continue

                candidates.append(
                    _EdgeCandidate(
                        piece_id=piece_id,
                        outer_edge_index=outer_edge_index,
                        points=points,
                        length=length,
                        first_angle=self._angle(points[0], points[1]),
                    )
                )

        candidates.sort(key=lambda candidate: candidate.length, reverse=True)
        return tuple(candidates[: self.MAX_EDGE_CANDIDATES_PER_PIECE])

    def _place_edge_candidate(
        self,
        piece: PuzzlePiece,
        candidate: _EdgeCandidate,
        side: _FrameSide,
        gap: tuple[float, float],
    ) -> _Placement:
        gap_start, gap_end = gap
        gap_midpoint = (gap_start + gap_end) / 2.0
        max_start = max(0.0, side.length - candidate.length)
        start_scalar = self._clamp(
            gap_midpoint - candidate.length / 2.0,
            0.0,
            max_start,
        )
        target_anchor = self._point_on_side(side, start_scalar)
        rotation = self._normalize_angle(side.angle - candidate.first_angle)

        return self._make_placement(
            piece=piece,
            piece_id=candidate.piece_id,
            outer_edge_index=candidate.outer_edge_index,
            source_anchor=candidate.points[0],
            target_anchor=target_anchor,
            rotation=rotation,
            boundary_points=candidate.points,
            alignment_error=0.0,
        )

    def _make_placement(
        self,
        piece: PuzzlePiece,
        piece_id: int,
        outer_edge_index: int,
        source_anchor: Point,
        target_anchor: Point,
        rotation: float,
        boundary_points: tuple[Point, ...],
        alignment_error: float,
    ) -> _Placement:
        centroid = piece.polygon.centroid()
        rotated_anchor = self._rotate_point(source_anchor, centroid, rotation)
        dx = target_anchor.x - rotated_anchor.x
        dy = target_anchor.y - rotated_anchor.y

        polygon = self._make_geometry(
            [
                (rotated.x + dx, rotated.y + dy)
                for rotated in (
                    self._rotate_point(vertex, centroid, rotation)
                    for vertex in piece.polygon.vertices
                )
            ]
        )
        placed_boundary_points = tuple(
            Point(rotated.x + dx, rotated.y + dy)
            for rotated in (
                self._rotate_point(point, centroid, rotation)
                for point in boundary_points
            )
        )

        return _Placement(
            piece_id=piece_id,
            outer_edge_index=outer_edge_index,
            source_anchor=source_anchor,
            rotation=rotation,
            target_anchor=target_anchor,
            boundary_points=placed_boundary_points,
            polygon=polygon,
            bounds=tuple(float(value) for value in polygon.bounds),
            area=float(polygon.area),
            alignment_error=alignment_error,
        )

    def _side_gap(
        self,
        side: _FrameSide,
        placements: tuple[_Placement, ...],
        frame: _Frame,
    ) -> tuple[float, float]:
        tolerance = max(8.0, min(frame.width, frame.height) * 0.025)
        intervals: list[tuple[float, float]] = []
        for placement in placements:
            interval = self._boundary_interval(placement.boundary_points, side, tolerance)
            if interval is not None:
                intervals.append(interval)

        if not intervals:
            return 0.0, side.length

        intervals = sorted(
            (
                self._clamp(start, 0.0, side.length),
                self._clamp(end, 0.0, side.length),
            )
            for start, end in intervals
        )
        merged: list[tuple[float, float]] = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))

        gaps: list[tuple[float, float]] = []
        cursor = 0.0
        for start, end in merged:
            if start > cursor:
                gaps.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < side.length:
            gaps.append((cursor, side.length))

        if not gaps:
            midpoint = side.length / 2.0
            return midpoint, midpoint

        return max(gaps, key=lambda item: item[1] - item[0])

    def _boundary_interval(
        self,
        points: tuple[Point, ...],
        side: _FrameSide,
        tolerance: float,
    ) -> tuple[float, float] | None:
        scalars: list[float] = []
        for point in points:
            scalar, distance = self._side_scalar_and_distance(side, point)
            if -tolerance <= scalar <= side.length + tolerance and distance <= tolerance:
                scalars.append(scalar)

        if not scalars:
            return None

        return min(scalars), max(scalars)

    @staticmethod
    def _side_scalar_and_distance(
        side: _FrameSide,
        point: Point,
    ) -> tuple[float, float]:
        dx, dy = side.direction
        offset_x = point.x - side.start.x
        offset_y = point.y - side.start.y
        scalar = offset_x * dx + offset_y * dy
        closest_x = side.start.x + scalar * dx
        closest_y = side.start.y + scalar * dy
        return scalar, math.hypot(point.x - closest_x, point.y - closest_y)

    @staticmethod
    def _point_on_side(side: _FrameSide, scalar: float) -> Point:
        return Point(
            side.start.x + side.direction[0] * scalar,
            side.start.y + side.direction[1] * scalar,
        )

    def _score_layout(
        self,
        placements: tuple[_Placement, ...],
        frame: _Frame,
    ) -> tuple[float, float, float]:
        return (
            self._overlap_area(placements),
            sum(self._overflow_area(placement, frame) for placement in placements),
            sum(placement.alignment_error for placement in placements),
        )

    @staticmethod
    def _choose_better(
        current: _Layout | None,
        candidate: _Layout,
    ) -> _Layout:
        if current is None or candidate.score < current.score:
            return candidate
        return current

    @staticmethod
    def _overlap_area(placements: tuple[_Placement, ...]) -> float:
        overlap = 0.0
        for first_index, first in enumerate(placements):
            for second in placements[first_index + 1 :]:
                if not CornerWalk._bounds_overlap(first.bounds, second.bounds):
                    continue
                overlap += float(first.polygon.intersection(second.polygon).area)
        return overlap

    @staticmethod
    def _overflow_area(placement: _Placement, frame: _Frame) -> float:
        return float(placement.polygon.difference(frame.geometry).area)

    @classmethod
    def _is_inside_frame(cls, placement: _Placement, frame: _Frame) -> bool:
        tolerance = max(
            1e-3,
            placement.area * cls.INSIDE_FRAME_AREA_TOLERANCE_RATIO,
        )
        return cls._overflow_area(placement, frame) <= tolerance

    @classmethod
    def _fit_inside_frame(
        cls,
        placement: _Placement,
        frame: _Frame,
    ) -> _Placement | None:
        min_x, min_y, max_x, max_y = placement.bounds
        if max_x - min_x > frame.width or max_y - min_y > frame.height:
            return None

        dx = 0.0
        dy = 0.0
        if min_x < 0.0:
            dx = -min_x
        elif max_x > frame.width:
            dx = frame.width - max_x

        if min_y < 0.0:
            dy = -min_y
        elif max_y > frame.height:
            dy = frame.height - max_y

        fitted = placement
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            fitted = cls._move_placement(placement, dx, dy)

        if not cls._is_inside_frame(fitted, frame):
            return None
        return fitted

    @classmethod
    def _fit_inside_side_placement(
        cls,
        placement: _Placement,
        frame: _Frame,
        side: _FrameSide,
    ) -> _Placement | None:
        min_x, min_y, max_x, max_y = placement.bounds
        tolerance = max(
            1e-3,
            placement.area * cls.INSIDE_FRAME_AREA_TOLERANCE_RATIO,
        )

        dx = 0.0
        dy = 0.0
        if abs(side.direction[0]) > 0.0:
            if min_y < -tolerance or max_y > frame.height + tolerance:
                return None
            if min_x < 0.0:
                dx = -min_x
            elif max_x > frame.width:
                dx = frame.width - max_x
        else:
            if min_x < -tolerance or max_x > frame.width + tolerance:
                return None
            if min_y < 0.0:
                dy = -min_y
            elif max_y > frame.height:
                dy = frame.height - max_y

        fitted = placement
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            fitted = cls._move_placement(placement, dx, dy)

        if not cls._is_inside_frame(fitted, frame):
            return None
        return fitted

    @staticmethod
    def _move_placement(
        placement: _Placement,
        dx: float,
        dy: float,
    ) -> _Placement:
        moved_polygon = translate_geometry(placement.polygon, xoff=dx, yoff=dy)
        return _Placement(
            piece_id=placement.piece_id,
            outer_edge_index=placement.outer_edge_index,
            source_anchor=placement.source_anchor,
            rotation=placement.rotation,
            target_anchor=Point(
                placement.target_anchor.x + dx,
                placement.target_anchor.y + dy,
            ),
            boundary_points=tuple(
                Point(point.x + dx, point.y + dy)
                for point in placement.boundary_points
            ),
            polygon=moved_polygon,
            bounds=tuple(float(value) for value in moved_polygon.bounds),
            area=placement.area,
            alignment_error=placement.alignment_error,
        )

    def _apply_solution(
        self,
        puzzle: dict[int, PuzzlePiece],
        placements: tuple[_Placement, ...],
    ) -> None:
        for placement in placements:
            piece = puzzle[placement.piece_id]
            piece._outer_edge = piece.possible_outer_edges[placement.outer_edge_index]
            centroid = piece.polygon.centroid()
            rotated_anchor = self._rotate_point(
                placement.source_anchor,
                centroid,
                placement.rotation,
            )
            piece.rotate(placement.rotation)
            piece.translate(rotated_anchor, placement.target_anchor)

        min_x, min_y, _, _ = self._pieces_bounds(puzzle.values())
        for piece in puzzle.values():
            piece.translate(Point(min_x, min_y), Point(0.0, 0.0))

    @staticmethod
    def _corner_index(points: tuple[Point, ...]) -> int:
        best_index = 1
        best_error = float("inf")
        for index in range(1, len(points) - 1):
            incoming_angle = CornerWalk._angle(points[index], points[index - 1])
            outgoing_angle = CornerWalk._angle(points[index], points[index + 1])
            corner_angle = abs(CornerWalk._normalize_angle(outgoing_angle - incoming_angle))
            error = abs(corner_angle - math.pi / 2.0)
            if error < best_error:
                best_index = index
                best_error = error
        return best_index

    @staticmethod
    def _outer_edge_points(
        outer_edge: OuterEdge,
        reversed_path: bool,
    ) -> tuple[Point, ...]:
        if not outer_edge.edges:
            return ()
        if reversed_path:
            edges = list(reversed(outer_edge.edges))
            return (edges[0].p2, *(edge.p1 for edge in edges))
        return (outer_edge.edges[0].p1, *(edge.p2 for edge in outer_edge.edges))

    @staticmethod
    def _path_length(points: tuple[Point, ...]) -> float:
        return sum(
            start.get_distance_between(end)
            for start, end in zip(points, points[1:])
        )

    @staticmethod
    def _make_geometry(points: list[tuple[float, float]]) -> BaseGeometry:
        polygon = ShapelyPolygon(points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if isinstance(polygon, MultiPolygon):
            polygon = max(polygon.geoms, key=lambda geometry: geometry.area)
        if polygon.is_empty:
            polygon = ShapelyPolygon(points).convex_hull
        return polygon

    @staticmethod
    def _rotate_point(point: Point, center: Point, angle: float) -> Point:
        translated_x = point.x - center.x
        translated_y = point.y - center.y
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        return Point(
            translated_x * cos_a - translated_y * sin_a + center.x,
            translated_x * sin_a + translated_y * cos_a + center.y,
        )

    @staticmethod
    def _angle(start: Point, end: Point) -> float:
        return math.atan2(end.y - start.y, end.x - start.x)

    @staticmethod
    def _vector_angle(vector: tuple[float, float]) -> float:
        return math.atan2(vector[1], vector[0])

    @staticmethod
    def _bounds_overlap(
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
    ) -> bool:
        return (
            first[0] < second[2]
            and first[2] > second[0]
            and first[1] < second[3]
            and first[3] > second[1]
        )

    @staticmethod
    def _pieces_bounds(
        pieces: Iterable[PuzzlePiece],
    ) -> tuple[float, float, float, float]:
        vertices = [vertex for piece in pieces for vertex in piece.polygon.vertices]
        return (
            min(vertex.x for vertex in vertices),
            min(vertex.y for vertex in vertices),
            max(vertex.x for vertex in vertices),
            max(vertex.y for vertex in vertices),
        )

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return min(max(value, minimum), maximum)

    @staticmethod
    def _normalize_angle(angle: float) -> float:
        return (angle + math.pi) % (2.0 * math.pi) - math.pi
