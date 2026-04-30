"""Brute-force compact layout solver based on possible outer edges."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Iterable

from shapely import affinity
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry.base import BaseGeometry

from puzzle_solver.utilities.draw_puzzle_piece import render_and_show_puzzle_piece

from .component import Point, PuzzlePiece
from .utilities import Solver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Pose:
    piece_id: int
    outer_edge_index: int
    rotation: float
    polygon: BaseGeometry
    width: float
    height: float
    area: float
    outer_start: Point
    outer_end: Point
    outer_start_angle: float
    outer_end_angle: float
    outer_edge_length: float


@dataclass(frozen=True)
class _Placement:
    piece_id: int
    pose: _Pose
    x: float
    y: float
    polygon: BaseGeometry
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class _SearchState:
    placements: tuple[_Placement, ...]
    remaining_piece_ids: frozenset[int]
    bounds: tuple[float, float, float, float] | None
    piece_area: float
    overlap_area: float
    outer_edge_penalty: float
    score: float


class BruteForce(Solver):
    """Search for a compact no-overlap layout using detected outer edges.

    The search space is bounded because the real puzzle only has four or six
    pieces. Each pose is produced by selecting a possible outer edge and
    rotating one of its segments to a horizontal or vertical side. Placement is
    then searched with a beam over piece order, pose, and flush candidate
    positions.
    """

    TARGET_ASPECT_RATIO = 1.0 / math.sqrt(2.0)
    CLEARANCE = 10.0
    MAX_POSES_PER_PIECE = 8
    MAX_POSITION_CANDIDATES = 48
    MAX_STATES_PER_DEPTH = 100
    ANCHOR_DISTANCE_PENALTY = 25.0
    ANGLE_TOLERANCE = math.radians(5.0)
    OVERLAP_PENALTY = 1000.0
    ASPECT_RATIO_PENALTY = 10000.0
    OUTER_EDGE_TIEBREAKER = 0.05
    AXIS_ANGLES = (0.0, math.pi / 2.0, math.pi, -math.pi / 2.0)
    ANCHOR_OFFSETS = (
        (0.0, 0.0),
        (CLEARANCE, 0.0),
        (-CLEARANCE, 0.0),
        (0.0, CLEARANCE),
        (0.0, -CLEARANCE),
        (CLEARANCE, CLEARANCE),
        (CLEARANCE, -CLEARANCE),
        (-CLEARANCE, CLEARANCE),
        (-CLEARANCE, -CLEARANCE),
    )

    @classmethod
    def solve(cls, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        solver = cls()
        return solver._solve(puzzle)

    def _solve(self, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        if not puzzle:
            return []
        
        # for piece_id, piece in puzzle.items():
        #     render_and_show_puzzle_piece(piece)

        poses_by_piece = {
            piece_id: self._build_piece_poses(piece_id, piece)
            for piece_id, piece in puzzle.items()
        }
        total_area = sum(piece.polygon.area() for piece in puzzle.values())
        best_outer_lengths = {
            piece_id: max(pose.outer_edge_length for pose in poses)
            for piece_id, poses in poses_by_piece.items()
        }

        states: list[_SearchState] = [
            _SearchState(
                placements=(),
                remaining_piece_ids=frozenset(puzzle),
                bounds=None,
                piece_area=0.0,
                overlap_area=0.0,
                outer_edge_penalty=0.0,
                score=0.0,
            )
        ]

        for depth in range(len(puzzle)):
            next_states: list[_SearchState] = []
            for state in states:
                for piece_id in sorted(state.remaining_piece_ids):
                    for pose in poses_by_piece[piece_id]:
                        outer_edge_penalty = (
                            state.outer_edge_penalty
                            + best_outer_lengths[piece_id]
                            - pose.outer_edge_length
                        )
                        candidates = self._candidate_positions(state, pose)
                        for x, y, anchor_distance in candidates:
                            next_states.append(
                                self._place_pose(
                                    state,
                                    pose,
                                    x,
                                    y,
                                    outer_edge_penalty,
                                    anchor_distance,
                                )
                            )

            if not next_states:
                raise RuntimeError("Brute-force solver could not generate placements")

            states = sorted(next_states, key=lambda item: item.score)[
                : self.MAX_STATES_PER_DEPTH
            ]
            logger.debug(
                "Brute-force depth %d retained %d states; best score %.2f",
                depth + 1,
                len(states),
                states[0].score,
            )

        best = min(states, key=lambda item: item.score)
        self._apply_solution(puzzle, best)

        order = [placement.piece_id for placement in best.placements]
        width, height = self._bounds_size(best.bounds)
        overlap_ratio = best.overlap_area / total_area if total_area > 0.0 else 0.0
        logger.info(
            "Brute-force solver selected order %s, bounds %.1fx%.1f, "
            "aspect %.3f, overlap ratio %.5f",
            order,
            width,
            height,
            self._compact_aspect_ratio(width, height),
            overlap_ratio,
        )
        return order

    def _build_piece_poses(self, piece_id: int, piece: PuzzlePiece) -> list[_Pose]:
        rotations_by_edge: dict[tuple[int, float], float] = {}
        for outer_index, outer_edge in enumerate(piece.possible_outer_edges):
            for edge in outer_edge.edges:
                edge_angle = math.atan2(edge.p2.y - edge.p1.y, edge.p2.x - edge.p1.x)
                for axis_angle in self.AXIS_ANGLES:
                    rotation = self._normalize_angle(axis_angle - edge_angle)
                    key = (outer_index, round(rotation, 6))
                    rotations_by_edge[key] = rotation

        poses = [
            self._build_pose(
                piece_id=piece_id,
                piece=piece,
                outer_edge_index=outer_index,
                rotation=rotation,
            )
            for (outer_index, _), rotation in rotations_by_edge.items()
        ]
        poses.sort(key=lambda item: (-item.outer_edge_length, item.width * item.height))
        return poses[: self.MAX_POSES_PER_PIECE]

    def _build_pose(
        self,
        piece_id: int,
        piece: PuzzlePiece,
        outer_edge_index: int,
        rotation: float,
    ) -> _Pose:
        centroid = piece.polygon.centroid()
        rotated_points = [
            self._rotate_point(vertex, centroid, rotation)
            for vertex in piece.polygon.vertices
        ]
        origin_min_x = min(point.x for point in rotated_points)
        origin_min_y = min(point.y for point in rotated_points)
        normalized_points = [
            (point.x - origin_min_x, point.y - origin_min_y)
            for point in rotated_points
        ]
        outer_edge = piece.possible_outer_edges[outer_edge_index]
        outer_start_segment_p1 = self._rotate_point(
            outer_edge.edges[0].p1,
            centroid,
            rotation,
        )
        outer_start_segment_p2 = self._rotate_point(
            outer_edge.edges[0].p2,
            centroid,
            rotation,
        )
        outer_end_segment_p1 = self._rotate_point(
            outer_edge.edges[-1].p1,
            centroid,
            rotation,
        )
        outer_end_segment_p2 = self._rotate_point(
            outer_edge.edges[-1].p2,
            centroid,
            rotation,
        )
        outer_start = self._rotate_point(outer_edge.edges[0].p1, centroid, rotation)
        outer_end = self._rotate_point(outer_edge.edges[-1].p2, centroid, rotation)
        polygon = self._make_geometry(normalized_points)
        min_x, min_y, max_x, max_y = polygon.bounds

        return _Pose(
            piece_id=piece_id,
            outer_edge_index=outer_edge_index,
            rotation=rotation,
            polygon=polygon,
            width=max_x - min_x,
            height=max_y - min_y,
            area=float(polygon.area),
            outer_start=Point(
                outer_start.x - origin_min_x,
                outer_start.y - origin_min_y,
            ),
            outer_end=Point(
                outer_end.x - origin_min_x,
                outer_end.y - origin_min_y,
            ),
            outer_start_angle=math.atan2(
                outer_start_segment_p2.y - outer_start_segment_p1.y,
                outer_start_segment_p2.x - outer_start_segment_p1.x,
            ),
            outer_end_angle=math.atan2(
                outer_end_segment_p2.y - outer_end_segment_p1.y,
                outer_end_segment_p2.x - outer_end_segment_p1.x,
            ),
            outer_edge_length=piece.possible_outer_edges[outer_edge_index].length,
        )

    def _candidate_positions(
        self,
        state: _SearchState,
        pose: _Pose,
    ) -> list[tuple[float, float, float]]:
        if not state.placements:
            return [(0.0, 0.0, 0.0)]

        assert state.bounds is not None
        candidates = []
        for placement in state.placements:
            if not self._valid_outer_edge_direction(placement.pose, pose):
                continue

            anchor_x = placement.x + placement.pose.outer_end.x
            anchor_y = placement.y + placement.pose.outer_end.y
            for offset_x, offset_y in self.ANCHOR_OFFSETS:
                x = anchor_x + offset_x - pose.outer_start.x
                y = anchor_y + offset_y - pose.outer_start.y
                bounds = self._merge_bounds(
                    state.bounds,
                    (x, y, x + pose.width, y + pose.height),
                )
                width, height = self._bounds_size(bounds)
                anchor_distance = math.hypot(offset_x, offset_y)
                score = self._layout_score(
                    width=width,
                    height=height,
                    piece_area=state.piece_area + pose.area,
                    overlap_area=0.0,
                    outer_edge_penalty=0.0,
                    anchor_distance=anchor_distance,
                )
                candidates.append((score, round(x, 6), round(y, 6), anchor_distance))

        candidates.sort(key=lambda item: item[0])
        unique_candidates: list[tuple[float, float, float]] = []
        seen: set[tuple[float, float]] = set()
        for _, x, y, anchor_distance in candidates:
            key = (x, y)
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append((x, y, anchor_distance))
            if len(unique_candidates) >= self.MAX_POSITION_CANDIDATES:
                break
        return unique_candidates

    @classmethod
    def _valid_outer_edge_direction(cls, placed_pose: _Pose, next_pose: _Pose) -> bool:
        diff = abs(
            cls._normalize_angle(
                next_pose.outer_start_angle - placed_pose.outer_end_angle
            )
        )
        return diff <= cls.ANGLE_TOLERANCE
    # @classmethod
    # def _valid_outer_edge_direction(cls, placed_pose: _Pose, next_pose: _Pose) -> bool:
    #     diff = abs(
    #         cls._normalize_angle(
    #             next_pose.outer_start_angle - placed_pose.outer_end_angle
    #         )
    #     )
    #     return (
    #         diff <= cls.ANGLE_TOLERANCE
    #         or abs(diff - math.pi / 2.0) <= cls.ANGLE_TOLERANCE
    #     )

    def _place_pose(
        self,
        state: _SearchState,
        pose: _Pose,
        x: float,
        y: float,
        outer_edge_penalty: float,
        anchor_distance: float,
    ) -> _SearchState:
        polygon = affinity.translate(pose.polygon, xoff=x, yoff=y)
        bounds = tuple(float(value) for value in polygon.bounds)
        overlap_area = state.overlap_area + self._overlap_area(
            polygon,
            bounds,
            state.placements,
        )
        merged_bounds = self._merge_bounds(state.bounds, bounds)
        width, height = self._bounds_size(merged_bounds)
        score = self._layout_score(
            width=width,
            height=height,
            piece_area=state.piece_area + pose.area,
            overlap_area=overlap_area,
            outer_edge_penalty=outer_edge_penalty,
            anchor_distance=anchor_distance,
        )

        placement = _Placement(
            piece_id=pose.piece_id,
            pose=pose,
            x=x,
            y=y,
            polygon=polygon,
            bounds=bounds,
        )
        return _SearchState(
            placements=state.placements + (placement,),
            remaining_piece_ids=state.remaining_piece_ids - {pose.piece_id},
            bounds=merged_bounds,
            piece_area=state.piece_area + pose.area,
            overlap_area=overlap_area,
            outer_edge_penalty=outer_edge_penalty,
            score=score,
        )

    @staticmethod
    def _overlap_area(
        polygon: BaseGeometry,
        bounds: tuple[float, float, float, float],
        placements: Iterable[_Placement],
    ) -> float:
        overlap = 0.0
        for placement in placements:
            if not BruteForce._bounds_overlap(bounds, placement.bounds):
                continue
            intersection = polygon.intersection(placement.polygon)
            overlap += float(intersection.area)
        return overlap

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

    def _apply_solution(
        self,
        puzzle: dict[int, PuzzlePiece],
        state: _SearchState,
    ) -> None:
        assert state.bounds is not None
        layout_min_x, layout_min_y, _, _ = state.bounds

        for placement in state.placements:
            piece = puzzle[placement.piece_id]
            piece._outer_edge = piece.possible_outer_edges[
                placement.pose.outer_edge_index
            ]
            piece.rotate(placement.pose.rotation)

            current_min_x = min(vertex.x for vertex in piece.polygon.vertices)
            current_min_y = min(vertex.y for vertex in piece.polygon.vertices)
            piece.translate(
                Point(current_min_x, current_min_y),
                Point(placement.x - layout_min_x, placement.y - layout_min_y),
            )

    @staticmethod
    def _make_geometry(points: list[tuple[float, float]]) -> BaseGeometry:
        polygon = ShapelyPolygon(points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
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
    def _merge_bounds(
        first: tuple[float, float, float, float] | None,
        second: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        if first is None:
            return second
        return (
            min(first[0], second[0]),
            min(first[1], second[1]),
            max(first[2], second[2]),
            max(first[3], second[3]),
        )

    @staticmethod
    def _bounds_size(
        bounds: tuple[float, float, float, float] | None,
    ) -> tuple[float, float]:
        if bounds is None:
            return (0.0, 0.0)
        return (bounds[2] - bounds[0], bounds[3] - bounds[1])

    @classmethod
    def _layout_score(
        cls,
        width: float,
        height: float,
        piece_area: float,
        overlap_area: float,
        outer_edge_penalty: float,
        anchor_distance: float,
    ) -> float:
        bounding_area = width * height
        empty_area = max(0.0, bounding_area - piece_area)
        return (
            overlap_area * cls.OVERLAP_PENALTY
            + empty_area * 4
            + cls._aspect_ratio_error(width, height) * cls.ASPECT_RATIO_PENALTY
            + outer_edge_penalty * cls.OUTER_EDGE_TIEBREAKER
            + anchor_distance * cls.ANCHOR_DISTANCE_PENALTY
        )

    @classmethod
    def _aspect_ratio_error(cls, width: float, height: float) -> float:
        if width <= 0.0 or height <= 0.0:
            return 0.0
        return abs(cls._compact_aspect_ratio(width, height) - cls.TARGET_ASPECT_RATIO)

    @classmethod
    def _target_envelope_area(cls, width: float, height: float) -> float:
        if width <= 0.0 or height <= 0.0:
            return 0.0
        long_side = max(width, height)
        short_side = min(width, height)
        target_short_side = long_side * cls.TARGET_ASPECT_RATIO
        if short_side <= target_short_side:
            return long_side * target_short_side
        target_long_side = short_side / cls.TARGET_ASPECT_RATIO
        return target_long_side * short_side

    @staticmethod
    def _compact_aspect_ratio(width: float, height: float) -> float:
        if width <= 0.0 or height <= 0.0:
            return 0.0
        return min(width, height) / max(width, height)

    @staticmethod
    def _normalize_angle(angle: float) -> float:
        return (angle + math.pi) % (2.0 * math.pi) - math.pi
