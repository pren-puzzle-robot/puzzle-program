"""Edge-walking solver strategy.

The solver searches placements by walking a cursor around an A5-style frame and
recursively trying straight candidate edges from each piece.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import math
from typing import Iterable

import numpy as np
from shapely.affinity import translate as translate_geometry
from shapely.geometry import LineString
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from .brute_force import BruteForce
from .component import OuterEdge, Point, PuzzlePiece
from .utilities import Solver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Frame:
    width: float
    height: float
    piece_gap: float
    edge_gap: float
    turn_margin: float
    geometry: BaseGeometry


@dataclass(frozen=True)
class _Cursor:
    point: Point
    heading: float
    angled_placement: bool = False


@dataclass(frozen=True)
class _EdgeCandidate:
    piece_id: int
    outer_edge_index: int | None
    outer_edge_reversed: bool
    points: tuple[Point, ...]
    length: float
    first_angle: float
    tier: int


@dataclass(frozen=True)
class _Placement:
    piece_id: int
    outer_edge_index: int | None
    outer_edge_reversed: bool
    source_start: Point
    rotation: float
    target_start: Point
    placed_points: tuple[Point, ...]
    walk_paths: tuple[tuple[Point, ...], ...]
    polygon: BaseGeometry
    bounds: tuple[float, float, float, float]
    area: float


class EdgeWalk(Solver):
    """Backtracking solver based on frame edge walking."""

    TARGET_ASPECT_RATIO = 1.0 / 1.484 # nicht A5 Seitenverhältnis math.sqrt(2)
    FRAME_AREA_MULTIPLIER = 1.2
    MAX_CANDIDATES_PER_PIECE = 24
    MAX_COMBINATIONS_PER_TIER = 120_000

    STRAIGHT_EDGE_TOLERANCE = math.radians(8.0)
    PLACED_EDGE_ANGLE_MARGIN = math.radians(5.0)
    OVERLAP_PERCENTAGE_MARGIN = 3.0
    FINAL_PERCENTAGE_MARGIN = 0.25
    SETTLE_ITERATIONS = 20
    RELAX_ITERATIONS = 10
    RELAX_STEP = 0.5

    TURN = -math.pi / 2.0

    def __init__(self) -> None:
        self._solution: tuple[_Placement, ...] | None = None
        self._combinations_tried = 0

    @classmethod
    def solve(cls, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        solver = cls()
        return solver._solve(puzzle)

    def _solve(self, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        if not puzzle:
            return []

        frame = self._derive_frame(puzzle.values())
        candidates_by_piece = {
            piece_id: self._build_candidates(piece_id, piece)
            for piece_id, piece in puzzle.items()
        }

        for min_edge_tier in (3, 2, 1):
            self._solution = None
            self._combinations_tried = 0
            logger.info("Trying edge-walk solver with minimum edge tier %d", min_edge_tier)

            for cursor in self._start_cursors(frame):
                for piece_id in sorted(puzzle):
                    for candidate in candidates_by_piece[piece_id]:
                        if candidate.tier < min_edge_tier:
                            continue
                        self._place_next(
                            puzzle=puzzle,
                            candidates_by_piece=candidates_by_piece,
                            frame=frame,
                            placements=(),
                            remaining_piece_ids=frozenset(puzzle),
                            cursor=cursor,
                            piece_id=piece_id,
                            candidate=candidate,
                            min_edge_tier=min_edge_tier,
                        )
                        if self._solution is not None:
                            break
                    if self._solution is not None:
                        break
                if self._solution is not None:
                    break

            logger.info(
                "Edge-walk solver tried %d combinations at minimum edge tier %d",
                self._combinations_tried,
                min_edge_tier,
            )
            if self._solution is not None:
                self._apply_solution(puzzle, self._solution)
                return [placement.piece_id for placement in self._solution]

        logger.warning(
            "Edge-walk solver could not place all pieces in the frame; "
            "falling back to brute_force"
        )
        return BruteForce.solve(puzzle)

    def _place_next(
        self,
        puzzle: dict[int, PuzzlePiece],
        candidates_by_piece: dict[int, list[_EdgeCandidate]],
        frame: _Frame,
        placements: tuple[_Placement, ...],
        remaining_piece_ids: frozenset[int],
        cursor: _Cursor,
        piece_id: int,
        candidate: _EdgeCandidate,
        min_edge_tier: int,
    ) -> None:
        if self._solution is not None:
            return
        if self._combinations_tried >= self.MAX_COMBINATIONS_PER_TIER:
            return

        self._combinations_tried += 1
        placement = self._place_candidate(puzzle[piece_id], candidate, cursor)
        if self._is_invalid_initial_placement(placement, placements, frame):
            return

        placement = self._settle_new_placement(placement, placements, frame)
        if self._is_invalid_final_placement(placement, placements, frame):
            return

        next_placements = placements + (placement,)
        next_remaining_piece_ids = remaining_piece_ids - {piece_id}

        if not next_remaining_piece_ids:
            relaxed = self._relax(next_placements, frame)
            if self._all_placements_valid(relaxed, frame):
                self._solution = relaxed
            return

        cursor = _Cursor(placement.placed_points[-1], cursor.heading, False)
        cursor = self._move_cursor_along_placed_edges(cursor, next_placements, (), frame)
        cursor = self._mark_angled_placement_if_needed(cursor, frame)

        straight_cursor = self._move_to_piece_gap(cursor, angled=False, frame=frame)
        angled_cursor = self._move_to_piece_gap(cursor, angled=True, frame=frame)

        for next_piece_id in sorted(next_remaining_piece_ids):
            for next_candidate in candidates_by_piece[next_piece_id]:
                if next_candidate.tier < min_edge_tier:
                    continue
                if cursor.angled_placement:
                    self._place_next(
                        puzzle,
                        candidates_by_piece,
                        frame,
                        next_placements,
                        next_remaining_piece_ids,
                        angled_cursor,
                        next_piece_id,
                        next_candidate,
                        min_edge_tier,
                    )
                    if self._solution is not None:
                        return
                if self._edge_fits_in_frame(next_candidate, cursor, frame):
                    self._place_next(
                        puzzle,
                        candidates_by_piece,
                        frame,
                        next_placements,
                        next_remaining_piece_ids,
                        straight_cursor,
                        next_piece_id,
                        next_candidate,
                        min_edge_tier,
                    )
                    if self._solution is not None:
                        return

    def _derive_frame(self, pieces: Iterable[PuzzlePiece]) -> _Frame:
        piece_area = sum(piece.polygon.area() for piece in pieces)
        target_area = max(piece_area * self.FRAME_AREA_MULTIPLIER, 1.0)
        long_side = math.sqrt(target_area / self.TARGET_ASPECT_RATIO)
        short_side = target_area / long_side
        width = long_side
        height = short_side
        piece_gap = max(8.0, min(width, height) * 0.018)
        edge_gap = max(piece_gap * 0.75, min(width, height) * 0.012)
        turn_margin = max(piece_gap * 3.0, min(width, height) * 0.08)
        overflow = max(edge_gap, min(width, height) * 0.015)

        return _Frame(
            width=width,
            height=height,
            piece_gap=piece_gap,
            edge_gap=edge_gap,
            turn_margin=turn_margin,
            geometry=box(-overflow, -overflow, width + overflow, height + overflow),
        )

    def _start_cursors(self, frame: _Frame) -> tuple[_Cursor, ...]:
        return (
            _Cursor(Point(0.0, frame.height), 0.0),
            _Cursor(Point(frame.width, frame.height), -math.pi / 2.0),
            _Cursor(Point(frame.width, 0.0), math.pi),
            _Cursor(Point(0.0, 0.0), math.pi / 2.0),
        )

    def _build_candidates(
        self,
        piece_id: int,
        piece: PuzzlePiece,
    ) -> list[_EdgeCandidate]:
        raw_candidates: list[tuple[int | None, bool, tuple[Point, ...], float, float]] = []
        seen: set[tuple[int | None, bool, tuple[tuple[float, float], ...]]] = set()

        for outer_edge_index, outer_edge_reversed, points in self._candidate_paths(piece):
            if len(points) < 2 or not self._is_straight_path(points):
                continue

            key = (
                outer_edge_index,
                outer_edge_reversed,
                tuple((round(point.x, 3), round(point.y, 3)) for point in points),
            )
            if key in seen:
                continue
            seen.add(key)

            length = self._path_length(points)
            if length <= 0.0:
                continue
            raw_candidates.append(
                (
                    outer_edge_index,
                    outer_edge_reversed,
                    points,
                    length,
                    self._angle(points[0], points[1]),
                )
            )

        if not raw_candidates:
            raw_candidates = self._fallback_candidates(piece)

        longest = max(candidate[3] for candidate in raw_candidates)
        candidates: list[_EdgeCandidate] = []
        for outer_edge_index, outer_edge_reversed, points, length, first_angle in raw_candidates:
            if length >= longest * 0.75:
                tier = 3
            elif length >= longest * 0.45:
                tier = 2
            else:
                tier = 1
            candidates.append(
                _EdgeCandidate(
                    piece_id=piece_id,
                    outer_edge_index=outer_edge_index,
                    outer_edge_reversed=outer_edge_reversed,
                    points=points,
                    length=length,
                    first_angle=first_angle,
                    tier=tier,
                )
            )

        candidates.sort(key=lambda item: (item.tier, item.length), reverse=True)
        if candidates and candidates[0].tier < 3:
            candidates[0] = replace(candidates[0], tier=3)
        return candidates[: self.MAX_CANDIDATES_PER_PIECE]

    def _fallback_candidates(
        self,
        piece: PuzzlePiece,
    ) -> list[tuple[int | None, bool, tuple[Point, ...], float, float]]:
        candidates: list[tuple[int | None, bool, tuple[Point, ...], float, float]] = []
        for outer_edge_index, outer_edge_reversed, points in self._candidate_paths(piece):
            if len(points) < 2:
                continue
            length = self._path_length(points)
            if length <= 0.0:
                continue
            candidates.append(
                (
                    outer_edge_index,
                    outer_edge_reversed,
                    points,
                    length,
                    self._angle(points[0], points[1]),
                )
            )
        if not candidates:
            raise RuntimeError("No usable edge candidates for puzzle piece")
        return sorted(candidates, key=lambda item: item[3], reverse=True)[
            : self.MAX_CANDIDATES_PER_PIECE
        ]

    def _place_candidate(
        self,
        piece: PuzzlePiece,
        candidate: _EdgeCandidate,
        cursor: _Cursor,
    ) -> _Placement:
        rotation = self._normalize_angle(cursor.heading - candidate.first_angle)
        centroid = piece.polygon.centroid()
        rotated_anchor = self._rotate_point(candidate.points[0], centroid, rotation)
        dx = cursor.point.x - rotated_anchor.x
        dy = cursor.point.y - rotated_anchor.y

        placed_points = tuple(
            Point(rotated.x + dx, rotated.y + dy)
            for rotated in (
                self._rotate_point(point, centroid, rotation)
                for point in candidate.points
            )
        )
        polygon = self._make_geometry(
            [
                (
                    rotated.x + dx,
                    rotated.y + dy,
                )
                for rotated in (
                    self._rotate_point(vertex, centroid, rotation)
                    for vertex in piece.polygon.vertices
                )
            ]
        )

        return _Placement(
            piece_id=candidate.piece_id,
            outer_edge_index=candidate.outer_edge_index,
            outer_edge_reversed=candidate.outer_edge_reversed,
            source_start=candidate.points[0],
            rotation=rotation,
            target_start=cursor.point,
            placed_points=placed_points,
            walk_paths=self._placed_walk_paths(piece, rotation, dx, dy),
            polygon=polygon,
            bounds=tuple(float(value) for value in polygon.bounds),
            area=float(polygon.area),
        )

    def _placed_walk_paths(
        self,
        piece: PuzzlePiece,
        rotation: float,
        dx: float,
        dy: float,
    ) -> tuple[tuple[Point, ...], ...]:
        centroid = piece.polygon.centroid()
        paths: list[tuple[Point, ...]] = []
        seen: set[tuple[tuple[float, float], ...]] = set()

        for _, _, points in self._candidate_paths(piece):
            if len(points) < 2 or not self._is_straight_path(points):
                continue

            placed = tuple(
                Point(rotated.x + dx, rotated.y + dy)
                for rotated in (
                    self._rotate_point(point, centroid, rotation)
                    for point in points
                )
            )
            key = tuple((round(point.x, 3), round(point.y, 3)) for point in placed)
            if key in seen:
                continue
            seen.add(key)
            paths.append(placed)

        return tuple(paths)

    def _candidate_paths(
        self,
        piece: PuzzlePiece,
    ) -> Iterable[tuple[int | None, bool, tuple[Point, ...]]]:
        for outer_edge_index, outer_edge in enumerate(
            piece.possible_outer_edges[: self.MAX_CANDIDATES_PER_PIECE]
        ):
            for outer_edge_reversed in (False, True):
                yield (
                    outer_edge_index,
                    outer_edge_reversed,
                    self._outer_edge_points(outer_edge, outer_edge_reversed),
                )

        for start, end in self._raw_outer_segments(piece):
            yield None, False, (start, end)
            yield None, True, (end, start)

    def _raw_outer_segments(self, piece: PuzzlePiece) -> Iterable[tuple[Point, Point]]:
        vertices = piece.polygon.vertices
        if len(vertices) < 2:
            return

        polygon = self._make_geometry([(point.x, point.y) for point in vertices])
        shrink = max(10.0, math.sqrt(max(piece.polygon.area(), 1.0)) * 0.02)
        inner_polygon = polygon.buffer(-shrink)
        min_length = max(50.0, piece.polygon.perimeter() * 0.04)

        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % len(vertices)]
            length = start.get_distance_between(end)
            if length < min_length:
                continue

            line = LineString([(start.x, start.y), (end.x, end.y)])
            extended = self._extend_line(line)
            if inner_polygon.is_empty or not extended.intersects(inner_polygon):
                yield Point(start.x, start.y), Point(end.x, end.y)

    def _is_invalid_initial_placement(
        self,
        placement: _Placement,
        placed: tuple[_Placement, ...],
        frame: _Frame,
    ) -> bool:
        return (
            self._overlap_percentage(placement, placed) > self.OVERLAP_PERCENTAGE_MARGIN
            or self._overflow_percentage(placement, frame) > self.OVERLAP_PERCENTAGE_MARGIN
        )

    def _is_invalid_final_placement(
        self,
        placement: _Placement,
        placed: tuple[_Placement, ...],
        frame: _Frame,
    ) -> bool:
        return (
            self._overlap_percentage(placement, placed) > self.FINAL_PERCENTAGE_MARGIN
            or self._overflow_percentage(placement, frame) > self.FINAL_PERCENTAGE_MARGIN
        )

    def _all_placements_valid(
        self,
        placements: tuple[_Placement, ...],
        frame: _Frame,
    ) -> bool:
        for index, placement in enumerate(placements):
            others = placements[:index] + placements[index + 1 :]
            if self._is_invalid_final_placement(placement, others, frame):
                return False
        return True

    def _settle_new_placement(
        self,
        placement: _Placement,
        placed: tuple[_Placement, ...],
        frame: _Frame,
    ) -> _Placement:
        current = placement
        for _ in range(self.SETTLE_ITERATIONS):
            total_move = np.array([0.0, 0.0])
            for other in placed:
                total_move += self._separation_vector(
                    current.polygon,
                    other.polygon,
                    frame.piece_gap,
                )
            total_move += self._frame_separation_vector(
                current.polygon,
                frame,
                frame.edge_gap,
            )

            dx, dy = total_move * self.RELAX_STEP
            if np.hypot(dx, dy) < 1e-3:
                break
            current = self._move_placement(current, float(dx), float(dy))
        return current

    def _relax(
        self,
        placements: tuple[_Placement, ...],
        frame: _Frame,
    ) -> tuple[_Placement, ...]:
        mutable = list(placements)
        for _ in range(self.RELAX_ITERATIONS):
            moves = [np.array([0.0, 0.0]) for _ in mutable]

            for first_index in range(len(mutable)):
                for second_index in range(first_index + 1, len(mutable)):
                    dx, dy = self._push_vector(
                        mutable[first_index].polygon,
                        mutable[second_index].polygon,
                        frame.piece_gap,
                    )
                    moves[first_index] += np.array([dx, dy]) * 0.5
                    moves[second_index] += np.array([-dx, -dy]) * 0.5

            for index, placement in enumerate(mutable):
                dx, dy = self._frame_push_vector(
                    placement.polygon,
                    frame,
                    frame.edge_gap,
                )
                moves[index] += np.array([dx, dy])

            max_move = 0.0
            for index, move in enumerate(moves):
                dx, dy = move * self.RELAX_STEP
                max_move = max(max_move, float(np.hypot(dx, dy)))
                mutable[index] = self._move_placement(mutable[index], float(dx), float(dy))

            if max_move < 1e-3:
                break
        return tuple(mutable)

    def _move_cursor_along_placed_edges(
        self,
        cursor: _Cursor,
        placements: tuple[_Placement, ...],
        visited: tuple[int, ...],
        frame: _Frame,
    ) -> _Cursor:
        current = cursor
        for placement_index, placement in enumerate(placements):
            if placement_index in visited:
                continue

            for path in placement.walk_paths:
                edge_start = path[0]
                edge_end = path[-1]
                edge_heading = self._angle(edge_start, edge_end)
                aligned_heading: float | None = None

                if abs(self._normalize_angle(edge_heading - current.heading)) <= (
                    self.PLACED_EDGE_ANGLE_MARGIN
                ):
                    aligned_heading = current.heading
                elif abs(
                    self._normalize_angle(edge_heading - (current.heading + self.TURN))
                ) <= self.PLACED_EDGE_ANGLE_MARGIN:
                    aligned_heading = self._normalize_angle(current.heading + self.TURN)

                if aligned_heading is None:
                    continue

                if current.point.get_distance_between(edge_start) <= frame.piece_gap * 3.0:
                    moved = _Cursor(edge_end, aligned_heading, current.angled_placement)
                    return self._move_cursor_along_placed_edges(
                        moved,
                        placements,
                        visited + (placement_index,),
                        frame,
                    )

        return current

    def _mark_angled_placement_if_needed(
        self,
        cursor: _Cursor,
        frame: _Frame,
    ) -> _Cursor:
        heading = self._snap_heading(cursor.heading)
        must_turn = (
            heading == 0
            and cursor.point.x > frame.width - frame.turn_margin
            or heading == 3
            and cursor.point.y < frame.turn_margin
            or heading == 2
            and cursor.point.x < frame.turn_margin
            or heading == 1
            and cursor.point.y > frame.height - frame.turn_margin
        )
        return replace(cursor, angled_placement=must_turn)

    def _move_to_piece_gap(
        self,
        cursor: _Cursor,
        angled: bool,
        frame: _Frame,
    ) -> _Cursor:
        move_heading = cursor.heading + (self.TURN / 2.0 if angled else 0.0)
        next_heading = self._normalize_angle(cursor.heading + (self.TURN if angled else 0.0))
        x = cursor.point.x + frame.piece_gap * math.cos(move_heading)
        y = cursor.point.y + frame.piece_gap * math.sin(move_heading)

        snapped_heading = self._snap_heading(next_heading)
        if snapped_heading == 0:
            y = frame.height
        elif snapped_heading == 3:
            x = frame.width
        elif snapped_heading == 2:
            y = 0.0
        elif snapped_heading == 1:
            x = 0.0

        return _Cursor(Point(x, y), next_heading, False)

    def _edge_fits_in_frame(
        self,
        candidate: _EdgeCandidate,
        cursor: _Cursor,
        frame: _Frame,
    ) -> bool:
        heading = self._snap_heading(cursor.heading)
        if heading == 0:
            available = frame.width - cursor.point.x
        elif heading == 3:
            available = cursor.point.y
        elif heading == 2:
            available = cursor.point.x
        elif heading == 1:
            available = frame.height - cursor.point.y
        else:
            available = 0.0
        return candidate.length <= available + frame.turn_margin

    def _apply_solution(
        self,
        puzzle: dict[int, PuzzlePiece],
        placements: tuple[_Placement, ...],
    ) -> None:
        for placement in placements:
            piece = puzzle[placement.piece_id]
            if placement.outer_edge_index is not None:
                piece._outer_edge = piece.possible_outer_edges[placement.outer_edge_index]
            centroid = piece.polygon.centroid()
            rotated_start = self._rotate_point(
                placement.source_start,
                centroid,
                placement.rotation,
            )
            piece.rotate(placement.rotation)
            piece.translate(rotated_start, placement.target_start)

        min_x, min_y, _, _ = self._pieces_bounds(puzzle.values())
        for piece in puzzle.values():
            piece.translate(Point(min_x, min_y), Point(0.0, 0.0))

    @staticmethod
    def _move_placement(
        placement: _Placement,
        dx: float,
        dy: float,
    ) -> _Placement:
        moved_polygon = translate_geometry(placement.polygon, xoff=dx, yoff=dy)
        return replace(
            placement,
            target_start=Point(placement.target_start.x + dx, placement.target_start.y + dy),
            placed_points=tuple(
                Point(point.x + dx, point.y + dy) for point in placement.placed_points
            ),
            walk_paths=tuple(
                tuple(Point(point.x + dx, point.y + dy) for point in path)
                for path in placement.walk_paths
            ),
            polygon=moved_polygon,
            bounds=tuple(float(value) for value in moved_polygon.bounds),
        )

    @staticmethod
    def _overlap_percentage(
        placement: _Placement,
        placed: tuple[_Placement, ...],
    ) -> float:
        if placement.area <= 0.0:
            return 100.0
        overlap_area = 0.0
        for other in placed:
            if not EdgeWalk._bounds_overlap(placement.bounds, other.bounds):
                continue
            overlap_area += float(placement.polygon.intersection(other.polygon).area)
        return overlap_area * 100.0 / placement.area

    @staticmethod
    def _overflow_percentage(
        placement: _Placement,
        frame: _Frame,
    ) -> float:
        if placement.area <= 0.0:
            return 100.0
        return float(placement.polygon.difference(frame.geometry).area) * 100.0 / placement.area

    @staticmethod
    def _push_vector(
        first: BaseGeometry,
        second: BaseGeometry,
        target_distance: float,
    ) -> tuple[float, float]:
        first_point, second_point = nearest_points(first, second)
        dx = first_point.x - second_point.x
        dy = first_point.y - second_point.y
        distance = math.hypot(dx, dy)

        if distance == 0.0:
            dx, dy = 1e-6, 0.0
            distance = 1e-6

        deficit = target_distance - distance
        if deficit <= 0.0:
            return 0.0, 0.0

        return dx / distance * deficit, dy / distance * deficit

    @staticmethod
    def _frame_push_vector(
        polygon: BaseGeometry,
        frame: _Frame,
        target_distance: float,
    ) -> tuple[float, float]:
        move = EdgeWalk._frame_separation_vector(polygon, frame, target_distance)
        return float(move[0]), float(move[1])

    @staticmethod
    def _separation_vector(
        first: BaseGeometry,
        second: BaseGeometry,
        target_distance: float,
    ) -> np.ndarray:
        if first.intersects(second):
            first_center = np.array([first.centroid.x, first.centroid.y])
            second_center = np.array([second.centroid.x, second.centroid.y])
            direction = first_center - second_center
            norm = np.linalg.norm(direction)

            if norm < 1e-9:
                direction = np.array([1.0, 0.0])
                norm = 1.0

            overlap_area = float(first.intersection(second).area)
            return direction / norm * (target_distance + math.sqrt(overlap_area))

        first_point, second_point = nearest_points(first, second)
        direction = np.array(
            [first_point.x - second_point.x, first_point.y - second_point.y]
        )
        distance = np.linalg.norm(direction)
        if distance < 1e-9:
            return np.array([0.0, 0.0])

        deficit = target_distance - distance
        if deficit <= 0.0:
            return np.array([0.0, 0.0])
        return direction / distance * deficit

    @staticmethod
    def _frame_separation_vector(
        polygon: BaseGeometry,
        frame: _Frame,
        target_distance: float,
    ) -> np.ndarray:
        if polygon.intersects(frame.geometry.boundary):
            piece_center = np.array([polygon.centroid.x, polygon.centroid.y])
            frame_center = np.array([frame.geometry.centroid.x, frame.geometry.centroid.y])
            direction = frame_center - piece_center
            norm = np.linalg.norm(direction)

            if norm < 1e-9:
                direction = np.array([0.0, -1.0])
                norm = 1.0

            overflow_area = float(polygon.difference(frame.geometry).area)
            return direction / norm * (target_distance + math.sqrt(overflow_area))

        return EdgeWalk._separation_vector(
            polygon,
            frame.geometry.boundary,
            target_distance,
        )

    @staticmethod
    def _is_straight_path(points: tuple[Point, ...]) -> bool:
        if len(points) <= 2:
            return True

        base_angle = EdgeWalk._angle(points[0], points[1])
        for start, end in zip(points, points[1:]):
            if start.get_distance_between(end) <= 0.0:
                continue
            if abs(EdgeWalk._normalize_angle(EdgeWalk._angle(start, end) - base_angle)) > (
                EdgeWalk.STRAIGHT_EDGE_TOLERANCE
            ):
                return False
        return True

    @staticmethod
    def _outer_edge_points(
        outer_edge: OuterEdge,
        outer_edge_reversed: bool,
    ) -> tuple[Point, ...]:
        if not outer_edge.edges:
            return ()
        if outer_edge_reversed:
            edges = list(reversed(outer_edge.edges))
            return (edges[0].p2, *(edge.p1 for edge in edges))
        return (outer_edge.edges[0].p1, *(edge.p2 for edge in outer_edge.edges))

    @staticmethod
    def _path_length(points: tuple[Point, ...]) -> float:
        return sum(start.get_distance_between(end) for start, end in zip(points, points[1:]))

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
    def _extend_line(line: LineString, scale: float = 1e6) -> LineString:
        start = np.array(line.coords[0], dtype=np.float64)
        end = np.array(line.coords[-1], dtype=np.float64)
        direction = end - start
        norm = np.linalg.norm(direction)
        if norm < 1e-9:
            return line
        direction = direction / norm
        return LineString([start - direction * scale, end + direction * scale])

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
    def _snap_heading(angle: float) -> int:
        axes = (0.0, math.pi / 2.0, math.pi, -math.pi / 2.0)
        return min(
            range(len(axes)),
            key=lambda index: abs(EdgeWalk._normalize_angle(angle - axes[index])),
        )

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
    def _normalize_angle(angle: float) -> float:
        return (angle + math.pi) % (2.0 * math.pi) - math.pi
