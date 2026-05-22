"""Brute-force layout solver based on rectangular outer-edge combinations."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
import logging
import math
from pathlib import Path
from typing import Iterable

from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry.base import BaseGeometry

from .component import OuterEdge, Point, PuzzlePiece
from .utilities import Solver, print_whole_puzzle_image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BoundaryCandidate:
    piece_id: int
    outer_edge_index: int
    outer_edge_reversed: bool
    points: tuple[Point, ...]
    length: float
    first_angle: float


@dataclass(frozen=True)
class _BoundaryPlacement:
    piece_id: int
    outer_edge_index: int
    outer_edge_reversed: bool
    rotation: float
    target_start: Point
    polygon: BaseGeometry
    bounds: tuple[float, float, float, float]
    area: float


@dataclass(frozen=True)
class _BoundaryState:
    placements: tuple[_BoundaryPlacement, ...]
    remaining_piece_ids: frozenset[int]
    cursor: tuple[float, float]
    heading: float
    bounds: tuple[float, float, float, float] | None
    path_bounds: tuple[float, float, float, float]
    side_lengths: tuple[float, float, float, float]
    turn_signs: tuple[int, ...]
    turn_error: float
    piece_area: float
    overlap_area: float
    outer_edge_penalty: float
    score: float


class BruteForce(Solver):
    """Search a rectangle-forming sequence of detected outer edges.

    The solver first picks combinations of candidate outer edges and traces them
    around a four-corner boundary. Pieces are only placed by mapping the chosen
    outer-edge chain onto that boundary. The final score prefers a closed
    rectangle whose short:long ratio is roughly 1:sqrt(2), with little overlap.
    """

    TARGET_ASPECT_RATIO = 1.0 / math.sqrt(2.0)
    MAX_OUTER_EDGE_CANDIDATES_PER_PIECE = 20
    MAX_STATES_PER_DEPTH = 1800
    MAX_STATES_PER_PRUNE_BUCKET = 3
    MAX_TURNS = 4
    OUTER_EDGES_ARE_COUNTER_CLOCKWISE = True

    TURN_TOLERANCE = math.radians(12.0)
    RECTANGLE_CLOSURE_TOLERANCE = 0.08

    OVERLAP_PENALTY = 1000.0
    EMPTY_AREA_PENALTY = 4.0
    ASPECT_RATIO_PENALTY = 10000.0
    CLOSURE_PENALTY = 500.0
    SIDE_MATCH_PENALTY = 250.0
    TURN_ERROR_PENALTY = 4000.0
    BOUNDS_OVERFLOW_PENALTY = 120.0
    OUTER_EDGE_TIEBREAKER = 0.05

    AXIS_ANGLES = (0.0, math.pi / 2.0, math.pi, -math.pi / 2.0)
    AXIS_VECTORS = (
        (1.0, 0.0),   # east
        (0.0, 1.0),   # south
        (-1.0, 0.0),  # west
        (0.0, -1.0),  # north
    )
    # Stored as east, west, south, north for easy opposite-side comparison.
    AXIS_SIDE_INDEX = (0, 2, 1, 3)

    def __init__(
        self,
        debug_output_dir: Path | None = None,
        render_states: bool = False,
    ) -> None:
        self.debug_output_dir = debug_output_dir
        self.render_states = render_states

    def solve(self, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        return self._solve(puzzle)

    def _solve(self, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        if not puzzle:
            return []

        candidate_limit = self._max_outer_edge_candidates(len(puzzle))
        candidates_by_piece = {
            piece_id: self._build_boundary_candidates(piece_id, piece, candidate_limit)
            for piece_id, piece in puzzle.items()
        }
        best_outer_lengths = {
            piece_id: max(candidate.length for candidate in candidates)
            for piece_id, candidates in candidates_by_piece.items()
        }
        anchor_piece_id = self._select_anchor_piece(best_outer_lengths)

        states: list[_BoundaryState] = [
            _BoundaryState(
                placements=(),
                remaining_piece_ids=frozenset(puzzle),
                cursor=(0.0, 0.0),
                heading=0.0,
                bounds=None,
                path_bounds=(0.0, 0.0, 0.0, 0.0),
                side_lengths=(0.0, 0.0, 0.0, 0.0),
                turn_signs=(),
                turn_error=0.0,
                piece_area=0.0,
                overlap_area=0.0,
                outer_edge_penalty=0.0,
                score=0.0,
            )
        ]
        max_states_per_depth = self._max_states_per_depth(len(puzzle))
        max_states_per_prune_bucket = self._max_states_per_prune_bucket(len(puzzle))

        for depth in range(len(puzzle)):
            next_states: list[_BoundaryState] = []
            for state in states:
                candidate_piece_ids = (
                    (anchor_piece_id,)
                    if not state.placements and anchor_piece_id in state.remaining_piece_ids
                    else sorted(state.remaining_piece_ids)
                )
                for piece_id in candidate_piece_ids:
                    outer_edge_penalty_base = state.outer_edge_penalty
                    for candidate in candidates_by_piece[piece_id]:
                        outer_edge_penalty = (
                            outer_edge_penalty_base
                            + best_outer_lengths[piece_id]
                            - candidate.length
                        )
                        next_states.extend(
                            self._extend_state(
                                puzzle[piece_id],
                                state,
                                candidate,
                                outer_edge_penalty,
                            )
                        )

            if not next_states:
                raise RuntimeError(
                    "Brute-force solver could not generate rectangular boundary states"
                )

            states = self._prune_states(
                next_states,
                max_states_per_depth,
                max_states_per_prune_bucket,
            )
            self._render_search_states(puzzle, depth + 1, states)
            logger.debug(
                "Brute-force boundary depth %d retained %d states; best score %.2f",
                depth + 1,
                len(states),
                states[0].score,
            )

        completed = [
            finalized
            for state in states
            if (finalized := self._finalize_rectangle_state(state)) is not None
        ]
        if not completed:
            raise RuntimeError(
                "Brute-force solver could not find a closed rectangular outer-edge loop"
            )

        best = min(completed, key=lambda item: item.score)
        self._render_completed_states(puzzle, completed, best)
        self._apply_solution(puzzle, best)

        order = [placement.piece_id for placement in best.placements]
        width, height = self._bounds_size(best.bounds)
        path_width, path_height = self._bounds_size(best.path_bounds)
        overlap_ratio = (
            best.overlap_area / best.piece_area if best.piece_area > 0.0 else 0.0
        )
        logger.info(
            "Brute-force solver selected order %s with anchor piece %d, boundary %.1fx%.1f, "
            "layout %.1fx%.1f, boundary aspect %.3f, overlap ratio %.5f",
            order,
            anchor_piece_id,
            path_width,
            path_height,
            width,
            height,
            self._compact_aspect_ratio(path_width, path_height),
            overlap_ratio,
        )
        return order

    @staticmethod
    def _select_anchor_piece(best_outer_lengths: dict[int, float]) -> int:
        return max(
            best_outer_lengths,
            key=lambda piece_id: (best_outer_lengths[piece_id], -piece_id),
        )

    def _render_search_states(
        self,
        puzzle: dict[int, PuzzlePiece],
        depth: int,
        states: list[_BoundaryState],
    ) -> None:
        if not self.render_states or self.debug_output_dir is None:
            return

        depth_dir = self.debug_output_dir / f"depth_{depth:02d}"
        depth_dir.mkdir(parents=True, exist_ok=True)
        for state_index, state in enumerate(states):
            self._render_state_image(
                puzzle,
                state,
                depth_dir / f"state_{state_index:04d}_score_{state.score:.2f}.png",
            )

    def _render_completed_states(
        self,
        puzzle: dict[int, PuzzlePiece],
        completed: list[_BoundaryState],
        best: _BoundaryState,
    ) -> None:
        if not self.render_states or self.debug_output_dir is None:
            return

        completed_dir = self.debug_output_dir / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        for state_index, state in enumerate(sorted(completed, key=lambda item: item.score)):
            label = "best" if state is best else "candidate"
            self._render_state_image(
                puzzle,
                state,
                completed_dir / (
                    f"{label}_{state_index:04d}_score_{state.score:.2f}.png"
                ),
            )

    def _render_state_image(
        self,
        puzzle: dict[int, PuzzlePiece],
        state: _BoundaryState,
        output_path: Path,
    ) -> None:
        if not state.placements:
            return

        pieces = self._materialize_state_pieces(puzzle, state)
        image = print_whole_puzzle_image(pieces)
        image.save(output_path)

    def _materialize_state_pieces(
        self,
        puzzle: dict[int, PuzzlePiece],
        state: _BoundaryState,
    ) -> dict[int, PuzzlePiece]:
        rendered_pieces: dict[int, PuzzlePiece] = {}
        for placement in state.placements:
            piece = copy.deepcopy(puzzle[placement.piece_id])
            piece._outer_edge = piece.possible_outer_edges[placement.outer_edge_index]
            piece.rotate(placement.rotation)
            from_point = self._outer_edge_points(
                piece.outer_edge,
                placement.outer_edge_reversed,
            )[0]
            piece.translate(from_point, placement.target_start)
            rendered_pieces[placement.piece_id] = piece

        layout_bounds = self._pieces_bounds(rendered_pieces.values())
        layout_min_x, layout_min_y, _, _ = layout_bounds
        for piece in rendered_pieces.values():
            piece.translate(Point(layout_min_x, layout_min_y), Point(0.0, 0.0))

        return rendered_pieces

    def _build_boundary_candidates(
        self,
        piece_id: int,
        piece: PuzzlePiece,
        candidate_limit: int,
    ) -> list[_BoundaryCandidate]:
        candidates: list[_BoundaryCandidate] = []
        outer_edges = piece.possible_outer_edges[:candidate_limit]
        for outer_edge_index, outer_edge in enumerate(outer_edges):
            outer_edge_reversed = self.OUTER_EDGES_ARE_COUNTER_CLOCKWISE
            points = self._outer_edge_points(outer_edge, outer_edge_reversed)
            length = self._path_length(points)
            if length <= 0.0:
                continue
            first_angle = math.atan2(
                points[1].y - points[0].y,
                points[1].x - points[0].x,
            )
            candidates.append(
                _BoundaryCandidate(
                    piece_id=piece_id,
                    outer_edge_index=outer_edge_index,
                    outer_edge_reversed=outer_edge_reversed,
                    points=points,
                    length=length,
                    first_angle=first_angle,
                )
            )

        if not candidates:
            raise RuntimeError(f"No usable outer-edge candidates for piece {piece_id}")

        candidates.sort(key=lambda item: (-item.length, item.outer_edge_reversed))
        return candidates

    def _max_outer_edge_candidates(self, piece_count: int) -> int:
        if piece_count <= 4:
            return self.MAX_OUTER_EDGE_CANDIDATES_PER_PIECE
        return self.MAX_OUTER_EDGE_CANDIDATES_PER_PIECE * 2

    def _max_states_per_depth(self, piece_count: int) -> int:
        if piece_count <= 4:
            return self.MAX_STATES_PER_DEPTH
        return self.MAX_STATES_PER_DEPTH * 3

    def _max_states_per_prune_bucket(self, piece_count: int) -> int:
        if piece_count <= 4:
            return 1
        return self.MAX_STATES_PER_PRUNE_BUCKET

    def _extend_state(
        self,
        piece: PuzzlePiece,
        state: _BoundaryState,
        candidate: _BoundaryCandidate,
        outer_edge_penalty: float,
    ) -> list[_BoundaryState]:
        entry_headings = (
            (0.0,)
            if not state.placements
            else (
                state.heading,
                self._normalize_angle(state.heading + math.pi / 2.0),
                self._normalize_angle(state.heading - math.pi / 2.0),
            )
        )

        next_states: list[_BoundaryState] = []
        for entry_heading in entry_headings:
            turn_result = self._apply_turn(
                state.turn_signs,
                state.turn_error,
                state.heading,
                entry_heading,
                require_turn=bool(state.placements),
            )
            if turn_result is None:
                continue

            turn_signs, turn_error = turn_result
            trace = self._trace_candidate_path(
                candidate,
                state.cursor,
                entry_heading,
                state.path_bounds,
                state.side_lengths,
                turn_signs,
                turn_error,
            )
            if trace is None:
                continue

            (
                cursor,
                heading,
                path_bounds,
                side_lengths,
                turn_signs,
                turn_error,
            ) = trace

            placement = self._place_candidate(
                piece,
                candidate,
                entry_heading,
                state.cursor,
            )
            overlap_area = state.overlap_area + self._overlap_area(
                placement.polygon,
                placement.bounds,
                state.placements,
            )
            bounds = self._merge_bounds(state.bounds, placement.bounds)
            piece_area = state.piece_area + placement.area
            score = self._partial_score(
                bounds=bounds,
                path_bounds=path_bounds,
                piece_area=piece_area,
                overlap_area=overlap_area,
                outer_edge_penalty=outer_edge_penalty,
                turn_error=turn_error,
            )

            next_states.append(
                _BoundaryState(
                    placements=state.placements + (placement,),
                    remaining_piece_ids=state.remaining_piece_ids
                    - {candidate.piece_id},
                    cursor=cursor,
                    heading=heading,
                    bounds=bounds,
                    path_bounds=path_bounds,
                    side_lengths=side_lengths,
                    turn_signs=turn_signs,
                    turn_error=turn_error,
                    piece_area=piece_area,
                    overlap_area=overlap_area,
                    outer_edge_penalty=outer_edge_penalty,
                    score=score,
                )
            )

        return next_states

    def _trace_candidate_path(
        self,
        candidate: _BoundaryCandidate,
        cursor: tuple[float, float],
        entry_heading: float,
        path_bounds: tuple[float, float, float, float],
        side_lengths: tuple[float, float, float, float],
        turn_signs: tuple[int, ...],
        turn_error: float,
    ) -> (
        tuple[
            tuple[float, float],
            float,
            tuple[float, float, float, float],
            tuple[float, float, float, float],
            tuple[int, ...],
            float,
        ]
        | None
    ):
        rotation = self._normalize_angle(entry_heading - candidate.first_angle)
        heading = entry_heading

        for index, (start, end) in enumerate(self._segments(candidate.points)):
            segment_length = start.get_distance_between(end)
            if segment_length <= 0.0:
                continue

            raw_angle = math.atan2(end.y - start.y, end.x - start.x)
            axis_angle, axis_error, axis_index = self._snap_axis(
                raw_angle + rotation
            )
            if axis_error > self.TURN_TOLERANCE:
                return None

            if index > 0:
                turn_result = self._apply_turn(
                    turn_signs,
                    turn_error,
                    heading,
                    axis_angle,
                    require_turn=True,
                )
                if turn_result is None:
                    return None
                turn_signs, turn_error = turn_result

            turn_error += axis_error
            heading = axis_angle
            dx, dy = self.AXIS_VECTORS[axis_index]
            cursor = (
                cursor[0] + dx * segment_length,
                cursor[1] + dy * segment_length,
            )
            path_bounds = self._merge_bounds(
                path_bounds,
                (cursor[0], cursor[1], cursor[0], cursor[1]),
            )
            side_lengths = self._add_side_length(
                side_lengths,
                axis_index,
                segment_length,
            )

        return cursor, heading, path_bounds, side_lengths, turn_signs, turn_error

    def _prune_states(
        self,
        states: list[_BoundaryState],
        max_states: int,
        max_states_per_bucket: int,
    ) -> list[_BoundaryState]:
        buckets: dict[
            tuple[
                frozenset[int],
                tuple[float, float],
                int,
                int,
                tuple[int, ...],
            ],
            list[_BoundaryState],
        ] = {}
        for state in sorted(states, key=lambda item: item.score):
            heading_bucket = round(self._normalize_angle(state.heading), 6)
            key = (
                state.remaining_piece_ids,
                (round(state.cursor[0], 1), round(state.cursor[1], 1)),
                int(round(heading_bucket * 1000)),
                len(state.turn_signs),
                state.turn_signs,
            )
            bucket = buckets.setdefault(key, [])
            if len(bucket) >= max_states_per_bucket:
                continue
            bucket.append(state)

        pruned: list[_BoundaryState] = []
        for rank in range(max_states_per_bucket):
            ranked_states = [
                bucket[rank]
                for bucket in buckets.values()
                if len(bucket) > rank
            ]
            for state in sorted(ranked_states, key=lambda item: item.score):
                pruned.append(state)
                if len(pruned) >= max_states:
                    return pruned

        return pruned

    def _place_candidate(
        self,
        piece: PuzzlePiece,
        candidate: _BoundaryCandidate,
        entry_heading: float,
        target_start: tuple[float, float],
    ) -> _BoundaryPlacement:
        rotation = self._normalize_angle(entry_heading - candidate.first_angle)
        centroid = piece.polygon.centroid()
        rotated_anchor = self._rotate_point(candidate.points[0], centroid, rotation)
        dx = target_start[0] - rotated_anchor.x
        dy = target_start[1] - rotated_anchor.y
        rotated_points = [
            self._rotate_point(vertex, centroid, rotation)
            for vertex in piece.polygon.vertices
        ]
        polygon = self._make_geometry(
            [(point.x + dx, point.y + dy) for point in rotated_points]
        )
        bounds = tuple(float(value) for value in polygon.bounds)

        return _BoundaryPlacement(
            piece_id=candidate.piece_id,
            outer_edge_index=candidate.outer_edge_index,
            outer_edge_reversed=candidate.outer_edge_reversed,
            rotation=rotation,
            target_start=Point(target_start[0], target_start[1]),
            polygon=polygon,
            bounds=bounds,
            area=float(polygon.area),
        )

    def _finalize_rectangle_state(
        self,
        state: _BoundaryState,
    ) -> _BoundaryState | None:
        closing_turn = self._apply_turn(
            state.turn_signs,
            state.turn_error,
            state.heading,
            0.0,
            require_turn=True,
        )
        if closing_turn is None:
            return None

        turn_signs, turn_error = closing_turn
        if len(turn_signs) != self.MAX_TURNS:
            return None

        perimeter = sum(state.side_lengths)
        closure_error = math.hypot(state.cursor[0], state.cursor[1])
        max_closure_error = max(20.0, perimeter * self.RECTANGLE_CLOSURE_TOLERANCE)
        if closure_error > max_closure_error:
            return None

        if not self._piece_centers_inside_rectangle(state.placements, state.path_bounds):
            return None

        final_score = self._final_score(
            state=state,
            closure_error=closure_error,
            turn_error=turn_error,
        )
        return replace(
            state,
            turn_signs=turn_signs,
            turn_error=turn_error,
            score=final_score,
        )

    def _apply_solution(
        self,
        puzzle: dict[int, PuzzlePiece],
        state: _BoundaryState,
    ) -> None:
        for placement in state.placements:
            piece = puzzle[placement.piece_id]
            piece._outer_edge = piece.possible_outer_edges[
                placement.outer_edge_index
            ]
            piece.rotate(placement.rotation)
            from_point = self._outer_edge_points(
                piece.outer_edge,
                placement.outer_edge_reversed,
            )[0]
            piece.translate(from_point, placement.target_start)

        layout_bounds = self._pieces_bounds(puzzle.values())
        layout_min_x, layout_min_y, _, _ = layout_bounds
        for piece in puzzle.values():
            piece.translate(Point(layout_min_x, layout_min_y), Point(0.0, 0.0))

    @classmethod
    def _apply_turn(
        cls,
        turn_signs: tuple[int, ...],
        turn_error: float,
        previous_heading: float,
        next_heading: float,
        require_turn: bool,
    ) -> tuple[tuple[int, ...], float] | None:
        if not require_turn:
            return turn_signs, turn_error

        delta = cls._normalize_angle(next_heading - previous_heading)
        options = (0.0, math.pi / 2.0, -math.pi / 2.0)
        snapped_turn = min(
            options,
            key=lambda option: abs(cls._normalize_angle(delta - option)),
        )
        error = abs(cls._normalize_angle(delta - snapped_turn))
        if error > cls.TURN_TOLERANCE:
            return None

        if abs(snapped_turn) <= 1e-9:
            return turn_signs, turn_error + error

        sign = 1 if snapped_turn > 0.0 else -1
        if turn_signs and turn_signs[0] != sign:
            return None
        if len(turn_signs) >= cls.MAX_TURNS:
            return None
        return turn_signs + (sign,), turn_error + error

    @classmethod
    def _snap_axis(cls, angle: float) -> tuple[float, float, int]:
        normalized = cls._normalize_angle(angle)
        axis_index = min(
            range(len(cls.AXIS_ANGLES)),
            key=lambda index: abs(
                cls._normalize_angle(normalized - cls.AXIS_ANGLES[index])
            ),
        )
        axis_angle = cls.AXIS_ANGLES[axis_index]
        error = abs(cls._normalize_angle(normalized - axis_angle))
        return axis_angle, error, axis_index

    @classmethod
    def _add_side_length(
        cls,
        side_lengths: tuple[float, float, float, float],
        axis_index: int,
        length: float,
    ) -> tuple[float, float, float, float]:
        mutable = list(side_lengths)
        mutable[cls.AXIS_SIDE_INDEX[axis_index]] += length
        return tuple(mutable)  # type: ignore[return-value]

    @classmethod
    def _partial_score(
        cls,
        bounds: tuple[float, float, float, float] | None,
        path_bounds: tuple[float, float, float, float],
        piece_area: float,
        overlap_area: float,
        outer_edge_penalty: float,
        turn_error: float,
    ) -> float:
        width, height = cls._bounds_size(bounds)
        path_width, path_height = cls._bounds_size(path_bounds)
        bounding_area = width * height
        empty_area = max(0.0, bounding_area - piece_area)
        aspect_penalty = (
            cls._aspect_ratio_error(path_width, path_height)
            * cls.ASPECT_RATIO_PENALTY
            * 0.25
        )
        return (
            overlap_area * cls.OVERLAP_PENALTY
            + empty_area * cls.EMPTY_AREA_PENALTY
            + aspect_penalty
            + outer_edge_penalty * cls.OUTER_EDGE_TIEBREAKER
            + turn_error * cls.TURN_ERROR_PENALTY
        )

    @classmethod
    def _final_score(
        cls,
        state: _BoundaryState,
        closure_error: float,
        turn_error: float,
    ) -> float:
        east, west, south, north = state.side_lengths
        horizontal = (east + west) / 2.0
        vertical = (south + north) / 2.0
        side_mismatch = abs(east - west) + abs(south - north)
        path_aspect_error = cls._aspect_ratio_error(horizontal, vertical)
        width, height = cls._bounds_size(state.bounds)
        actual_aspect_error = cls._aspect_ratio_error(width, height)
        overflow = cls._bounds_overflow(state.bounds, state.path_bounds)

        return (
            state.overlap_area * cls.OVERLAP_PENALTY
            + cls._empty_area(state.bounds, state.piece_area)
            * cls.EMPTY_AREA_PENALTY
            + path_aspect_error * cls.ASPECT_RATIO_PENALTY
            + actual_aspect_error * cls.ASPECT_RATIO_PENALTY * 0.25
            + closure_error * cls.CLOSURE_PENALTY
            + side_mismatch * cls.SIDE_MATCH_PENALTY
            + overflow * cls.BOUNDS_OVERFLOW_PENALTY
            + state.outer_edge_penalty * cls.OUTER_EDGE_TIEBREAKER
            + turn_error * cls.TURN_ERROR_PENALTY
        )

    @staticmethod
    def _overlap_area(
        polygon: BaseGeometry,
        bounds: tuple[float, float, float, float],
        placements: Iterable[_BoundaryPlacement],
    ) -> float:
        overlap = 0.0
        for placement in placements:
            if not BruteForce._bounds_overlap(bounds, placement.bounds):
                continue
            intersection = polygon.intersection(placement.polygon)
            overlap += float(intersection.area)
        return overlap

    @staticmethod
    def _piece_centers_inside_rectangle(
        placements: Iterable[_BoundaryPlacement],
        rectangle_bounds: tuple[float, float, float, float],
    ) -> bool:
        min_x, min_y, max_x, max_y = rectangle_bounds
        tolerance = 1e-6
        for placement in placements:
            center = placement.polygon.centroid
            if (
                center.x < min_x - tolerance
                or center.x > max_x + tolerance
                or center.y < min_y - tolerance
                or center.y > max_y + tolerance
            ):
                return False
        return True

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
    def _segments(points: tuple[Point, ...]) -> Iterable[tuple[Point, Point]]:
        return zip(points, points[1:])

    @classmethod
    def _path_length(cls, points: tuple[Point, ...]) -> float:
        return sum(start.get_distance_between(end) for start, end in cls._segments(points))

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
    def _bounds_size(
        bounds: tuple[float, float, float, float] | None,
    ) -> tuple[float, float]:
        if bounds is None:
            return (0.0, 0.0)
        return (bounds[2] - bounds[0], bounds[3] - bounds[1])

    @staticmethod
    def _empty_area(
        bounds: tuple[float, float, float, float] | None,
        piece_area: float,
    ) -> float:
        width, height = BruteForce._bounds_size(bounds)
        return max(0.0, width * height - piece_area)

    @staticmethod
    def _bounds_overflow(
        inner: tuple[float, float, float, float] | None,
        outer: tuple[float, float, float, float],
    ) -> float:
        if inner is None:
            return 0.0
        return (
            max(0.0, outer[0] - inner[0])
            + max(0.0, outer[1] - inner[1])
            + max(0.0, inner[2] - outer[2])
            + max(0.0, inner[3] - outer[3])
        )

    @classmethod
    def _aspect_ratio_error(cls, width: float, height: float) -> float:
        if width <= 0.0 or height <= 0.0:
            return 0.0
        return abs(cls._compact_aspect_ratio(width, height) - cls.TARGET_ASPECT_RATIO)

    @staticmethod
    def _compact_aspect_ratio(width: float, height: float) -> float:
        if width <= 0.0 or height <= 0.0:
            return 0.0
        return min(width, height) / max(width, height)

    @staticmethod
    def _normalize_angle(angle: float) -> float:
        return (angle + math.pi) % (2.0 * math.pi) - math.pi
