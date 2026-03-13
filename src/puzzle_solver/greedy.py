"""Code-File providing the matching of puzzle edges."""

from __future__ import annotations

import math

from .component import PuzzlePiece, Point
from .utilities import print_whole_puzzle_image, Solver
from .utilities.puzzle_piece_loader import PuzzlePieceLoader


class Greedy(Solver):
    """Alternative `Solver` implementation using a greedy algorithm.\n
    If there is a solution, it will find it. Just slower."""

    ERROR_MARCHING_LENGTH: float = 0.05
    ERROR_MARCHING_ANGLE: float = 10  # degrees

    _puzzle: dict[int, PuzzlePiece]

    def __init__(self, puzzle: dict[int, PuzzlePiece]) -> None:
        self._puzzle = puzzle

    @property
    def puzzle(self) -> dict[int, PuzzlePiece]:
        """get the puzzle pieces to be solved"""
        return self._puzzle

    @classmethod
    def solve(cls, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        """greedy matching"""

        solver = Greedy(puzzle)
        result = solver.solve_greedy_corner_matching()

        if result is not None:
            print(result)
            solver.align_whole_puzzle(result)
            print_whole_puzzle_image(puzzle)
            ordered_piece_ids = list(dict.fromkeys(piece_id for piece_id, _ in result))
            return ordered_piece_ids
        else:
            print("ERROR")
            return []

    def align_whole_puzzle(self, solution: list[tuple[int, tuple[int, int]]]) -> None:
        """Align the whole puzzle to the origin (0,0)"""
        first_piece_id, first_edge = solution.pop(0)
        first_piece = self.puzzle[first_piece_id]
        self.rotate_first_corner(first_piece)
        first_piece.translate(first_piece.outer_edge.edges[-1].p1, Point(0, 0))

        previous_piece = first_piece
        previous_edge = first_edge

        odd: bool = True

        for next_piece_id, next_edge in solution:
            current_piece = self.puzzle[next_piece_id]
            if odd:
                rotation = self.get_angle(
                    (
                        previous_piece.polygon.vertices[previous_edge[0]],
                        previous_piece.polygon.vertices[previous_edge[1]],
                    ),
                    (
                        current_piece.polygon.vertices[next_edge[0]],
                        current_piece.polygon.vertices[next_edge[1]],
                    ),
                )
                current_piece.rotate(rotation)

                current_piece.translate(
                    current_piece.polygon.vertices[next_edge[0]],
                    previous_piece.polygon.vertices[previous_edge[0]],
                )

                odd = False
            else:
                odd = True

            previous_piece = current_piece
            previous_edge = next_edge

    def solve_greedy_corner_matching(self) -> list[tuple[int, tuple[int, int]]] | None:
        """Greedy Corner Matching Algorithm"""

        return self._pick_first_puzzle_piece()

    def _pick_first_puzzle_piece(self) -> list[tuple[int, tuple[int, int]]]:
        # get the first corner piece
        index: int = next(i for i, p in self.puzzle.items() if p.is_corner)
        direction: bool = True
        remaining_edges: list[int] = [k for k in self.puzzle if k != index]

        result: list[tuple[int, tuple[int, int]]] = []
        limits: list[tuple[int, int]] = self.puzzle[index].get_possible_limits()

        print(limits)

        for limit in limits:
            origin_edge: tuple[int, bool, tuple[int, int]] = (index, direction, limit)
            temp_result = self._find_next_matching_puzzle_piece(
                origin_edge, remaining_edges
            )

            if temp_result is not None:
                result = temp_result
                break

        return result

    @staticmethod
    def get_angle(
        this_edge: tuple[Point, Point], next_edge: tuple[Point, Point]
    ) -> float:
        """Rotates a puzzle piece to fit the current puzzle piece."""
        # Calculate the angle of the current edge
        dx1 = this_edge[1].x - this_edge[0].x
        dy1 = this_edge[1].y - this_edge[0].y
        angle1 = math.atan2(dy1, dx1)

        # Calculate the angle of the new edge
        dx2 = next_edge[1].x - next_edge[0].x
        dy2 = next_edge[1].y - next_edge[0].y
        angle2 = math.atan2(dy2, dx2)

        # Calculate the rotation needed to align the new edge with the current edge
        rotation_needed = angle1 - angle2

        return rotation_needed

    @staticmethod
    def rotate_first_corner(puzzle_piece: PuzzlePiece) -> None:
        """Rotates the first corner piece to point down horizontally."""

        # Rotates the polygon so that the last outer edge is at the bottom
        bottom_edge = puzzle_piece.outer_edge.edges[-1]
        # Calculate the angle of the bottom edge
        dx = bottom_edge.p2.x - bottom_edge.p1.x
        dy = bottom_edge.p2.y - bottom_edge.p1.y
        angle = math.atan2(dy, dx)
        rotation_needed = -angle + math.pi / 2  # Rotate to point downwards
        # Rotate all points in the polygon
        puzzle_piece.rotate(rotation_needed)

    def _generate_all_possible_edges(
        self,
        puzzle_pieces: list[int],
    ) -> list[tuple[int, bool, tuple[int, int]]]:
        pieces_n_directions: list[tuple[int, bool]] = [
            (n, True) for n in puzzle_pieces
        ] + [(n, False) for n in puzzle_pieces]

        pieces_n_directions_n_limits: list[tuple[int, bool, tuple[int, int]]] = [
            (piece_id, direction, limit)
            for (piece_id, direction) in pieces_n_directions
            for limit in self.puzzle[piece_id].get_possible_limits()
        ]

        return pieces_n_directions_n_limits

    def _find_next_matching_puzzle_piece(
        self, origin: tuple[int, bool, tuple[int, int]], remaining: list[int]
    ) -> list[tuple[int, tuple[int, int]]] | None:
        # trivial case: no remaining pieces
        if remaining == []:
            return []

        # remaining matches generated from the remaining puzzle pieces
        prev_remaining: list[tuple[int, bool, tuple[int, int]]] = (
            self._generate_all_possible_edges(remaining)
        )
        curr_remaining: list[tuple[int, bool, tuple[int, int]]] = prev_remaining.copy()

        # setup values for the original puzzlepiece
        origin_piece = self.puzzle[origin[0]]
        o_direction = origin[1]
        o_length: int = len(origin_piece.polygon.vertices)
        o_limit: tuple[int, int] = origin[2]
        o_start: int = o_limit[1] if o_direction else o_limit[0]
        o_dir: int = 1 if o_direction else -1

        # default solution to be overritten
        this_edge: tuple[int, int] = (o_start, o_start)
        next_edges: list[tuple[int, bool, tuple[int, int]]] = []

        for i in range(0, o_length):
            # current points and edges for origin
            o_index = o_start + i * o_dir
            o_points = origin_piece.get_triplet(o_index, o_direction)
            for m_piece, m_direction, m_limit in prev_remaining:
                # current points and edges for a potential match
                m_start = m_limit[1] if m_direction else m_limit[0]
                m_dir = 1 if m_direction else -1
                m_index = m_start + i * m_dir
                m_points = self.puzzle[m_piece].get_triplet(m_index, m_direction)

                # result of the matching
                matching = (
                    self._first_segment_matches(o_points, m_points)
                    if i == 0
                    else self._next_segment_matches(o_points, m_points)
                )

                # remove from pool if it does not fit
                if not matching:
                    curr_remaining.remove((m_piece, m_direction, m_limit))

            if len(curr_remaining) == 0:
                # in this round the remaining pieces droped out
                o_last = (o_start + (i * o_dir)) % o_length
                this_edge = (o_start, o_last)
                next_edges = prev_remaining
                break

            # shuffel remaining pieces into the upcoming pool
            prev_remaining = curr_remaining.copy()

        # how to handle recursion

        # Failure: not a single Segment could match
        if (
            next_edges == remaining and this_edge[1] == o_start - 1 * o_dir
        ):  # could not complete a single loop
            return None

        if (this_edge[1] - this_edge[0]) % o_length <= 1:
            return None  # could not match at least two segments

        for next_piece, next_dir, next_limit in next_edges:
            next_edge = (next_piece, not next_dir, next_limit)
            next_remaining = remaining.copy()
            next_remaining.remove(next_piece)
            temp_result = self._find_next_matching_puzzle_piece(
                next_edge, next_remaining
            )

            if temp_result is not None:
                this_match: tuple[int, tuple[int, int]] = (origin[0], this_edge)

                next_length: int = len(self.puzzle[next_piece].polygon.vertices)
                edge_length: int = (this_edge[1] - this_edge[0]) % o_length

                next_start: int = next_limit[1] if next_dir else next_limit[0]
                next_direction: int = 1 if next_dir else -1
                next_last: int = (
                    next_start + (edge_length * next_direction)
                ) % next_length

                next_match: tuple[int, tuple[int, int]] = (
                    next_piece,
                    (next_start, next_last),
                )

                temp_result.insert(0, next_match)
                temp_result.insert(0, this_match)
                return temp_result

        return None

    @staticmethod
    def _same_remaining_puzzle_piece(
        remaining: list[tuple[int, bool, tuple[int, int]]],
    ) -> bool:
        if not remaining:
            raise ValueError("Remaining list is empty")
        reference = remaining[0][0]
        return all(piece == reference for piece, _, _ in remaining)

    @classmethod
    def _first_segment_matches(
        cls, origin: tuple[Point, Point, Point], match: tuple[Point, Point, Point]
    ) -> bool:
        return cls._length_matching((origin[1], origin[2]), (match[1], match[2]))

    @classmethod
    def _next_segment_matches(
        cls, origin: tuple[Point, Point, Point], match: tuple[Point, Point, Point]
    ) -> bool:
        return cls._first_segment_matches(origin, match) and cls._angle_matching(
            origin, match
        )

    @classmethod
    def _length_matching(
        cls, origin: tuple[Point, Point], match: tuple[Point, Point]
    ) -> bool:
        o_this, o_next = origin
        m_this, m_next = match

        o_length: float = (
            (o_this.x - o_next.x) ** 2 + (o_this.y - o_next.y) ** 2
        ) ** 0.5
        m_length: float = (
            (m_this.x - m_next.x) ** 2 + (m_this.y - m_next.y) ** 2
        ) ** 0.5

        err_margin_len: float = o_length * cls.ERROR_MARCHING_LENGTH

        return abs(o_length - m_length) <= err_margin_len

    @classmethod
    def _angle_matching(
        cls, origin: tuple[Point, Point, Point], match: tuple[Point, Point, Point]
    ) -> bool:
        o_prev, o_this, o_next = origin
        m_prev, m_this, m_next = match

        o_angle = cls._angle_at_this(o_prev, o_this, o_next)
        m_angle = cls._angle_at_this(m_prev, m_this, m_next)

        return abs(cls._angle_diff(o_angle, m_angle)) <= math.radians(
            cls.ERROR_MARCHING_ANGLE / 2.0
        )

    @staticmethod
    def _angle_diff(a: float, b: float) -> float:
        return (a - b + math.pi) % (2 * math.pi) - math.pi

    @staticmethod
    def _angle_at_this(prev: Point, this: Point, follow: Point) -> float:
        # vectors leaving the point "this"
        v1_x: float = prev.x - this.x
        v1_y: float = prev.y - this.y
        v2_x: float = follow.x - this.x
        v2_y: float = follow.y - this.y

        # compute their length
        len1_sq: float = v1_x * v1_x + v1_y * v1_y
        len2_sq: float = v2_x * v2_x + v2_y * v2_y

        # edgecase if identical points
        if len1_sq == 0 or len2_sq == 0:
            return float("nan")

        dot = v1_x * v2_x + v1_y * v2_y
        cross = v1_x * v2_y - v1_y * v2_x  # Skalar in 2D

        # radiant angle between the two vectors
        angle_rad = math.atan2(cross, dot)
        return angle_rad


if __name__ == "__main__":
    # simple test code
    PUZZLE: dict[int, PuzzlePiece] = PuzzlePieceLoader.load_pieces()
    Greedy.solve(PUZZLE)
    print_whole_puzzle_image(PUZZLE)
