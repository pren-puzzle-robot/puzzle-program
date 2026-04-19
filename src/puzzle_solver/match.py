"""Code-File providing the matching of puzzle edges."""

from __future__ import annotations

import logging
import math
import time

from .component import PuzzlePiece, Point, OuterEdge
from .utilities import Solver
from .utilities.draw_puzzle_piece import print_whole_puzzle_image
from .utilities.puzzle_piece_loader import PuzzlePieceLoader

logger = logging.getLogger(__name__)

class Match(Solver):

    @staticmethod
    def rotate_first_corner(puzzlePiece: PuzzlePiece) -> None:
        """Rotates the first corner piece to point down horizontally."""

        # Rotates the polygon so that the last outer edge is at the bottom
        bottom_edge = puzzlePiece.outer_edge.edges[-1]
        # Calculate the angle of the bottom edge
        dx = bottom_edge.p2.x - bottom_edge.p1.x
        dy = bottom_edge.p2.y - bottom_edge.p1.y
        angle = math.atan2(dy, dx)
        rotation_needed = -angle + math.pi / 2  # Rotate to point downwards
        # Rotate all points in the polygon
        puzzlePiece.rotate(rotation_needed)

    @classmethod
    def solve(cls, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        """Solves the puzzle using hoalistic matching algorithm."""
        first_corner = next(i for i, p in puzzle.items() if p.is_corner)
        
        # render_and_show_puzzle_piece(puzzle[first_corner])
        cls.rotate_first_corner(puzzle[first_corner])

        # render_and_show_puzzle_piece(puzzle[first_corner])

        start = time.perf_counter()
        order = cls.solve_greedily(first_corner, puzzle)
        end = time.perf_counter()
        logger.info("Time taken (s): %.6f", end - start)
        logger.info("Solved order: %s", order)
        logger.info("Number of pieces: %d", len(order))
        logger.debug(
            "Rotation of pieces (radians): %s",
            [puzzle[pid].rotation for pid in order],
        )

        cls.move_pieces_to_fit(order, puzzle)

        logger.debug(
            "Outer edges after moving: %s",
            "\n\n".join(str(puzzle[pid].outer_edge.edges) for pid in order),
        )
        return order

    @classmethod
    def solve_greedily(cls, start_id: int, pieces: dict[int, PuzzlePiece]) -> list[int]:
        """Greedy recursive solver: always picks the next piece with most matching points."""
        remaining = pieces.copy()
        current = remaining.pop(start_id)  # remove start from pool
        order = [start_id]

        def recurse(current_piece: PuzzlePiece,
                    remaining_pieces: dict[int, PuzzlePiece],
                    placed_order: list[int]) -> None:
            if not remaining_pieces:
                logger.info("All pieces processed. Order: %s", placed_order)
                return

            score = 0
            best_pid: int | None = None
            best_piece: PuzzlePiece | None = None
            best_score = -1
            best_outer_edge: OuterEdge | None = None
            best_current_outer_edge: OuterEdge | None = None
            best_additional_rotation: 0.0

            current_outer_edge_start_index = current_piece.outer_edge.edges[0].i

            # Try all possible outer edges of the current piece
            for outer_edges in current_piece.possible_outer_edges:
                # Only consider outer edges that start with the same index as the current outer edge
                # Start of the outer edge must match, because this was found to match the previous piece
                if outer_edges.edges[0].i != current_outer_edge_start_index:
                    continue

                current_piece._outer_edge = outer_edges
                # Try all remaining pieces and pick the one with most matches
                for pid, piece in remaining_pieces.items():
                    # Try all possible outer edges of the new piece
                    for outer_edge in piece.possible_outer_edges:
                        piece._outer_edge = outer_edge
                        next_piece = cls.rotate_to_fit(current_piece, piece)
                        logger.debug("Rotated piece %d to fit.", pid)

                        def check_match(additional_rotation: float = 0.0) -> None:
                            nonlocal score, best_score, best_pid, best_piece, best_outer_edge, best_current_outer_edge, best_additional_rotation
                            score = cls.get_amount_of_matching_points(current_piece, next_piece)
                            logger.debug(
                                "Piece %d has %d matching points with current piece.",
                                pid,
                                score,
                            )

                            if score > best_score:
                                best_score = score
                                best_pid = pid
                                best_piece = next_piece
                                best_outer_edge = outer_edge
                                best_current_outer_edge = outer_edges
                                best_additional_rotation = additional_rotation

                        check_match()

                        next_piece.rotate(math.pi / 2)
                        check_match(math.pi / 2)

                        next_piece.rotate(-math.pi / 2)
                        check_match(-math.pi / 2)

            # Use the best matching piece as the next current
            assert (best_pid is not None
                    and best_piece is not None
                    and best_outer_edge is not None), "No suitable next piece found!"

            current_piece._outer_edge = best_current_outer_edge

            best_piece._outer_edge = best_outer_edge
            best_piece = cls.rotate_to_fit(current_piece, best_piece)
            best_piece.rotate(best_additional_rotation)

            # render_and_show_puzzle_piece(best_piece)

            # Remove chosen piece from remaining and recurse
            remaining_copy = dict(remaining_pieces)
            remaining_copy.pop(best_pid)

            placed_order.append(best_pid)
            recurse(best_piece, remaining_copy, placed_order)

        recurse(current, remaining, order)
        return order

    @staticmethod
    def move_pieces_to_fit(order: list[int], pieces: dict[int, PuzzlePiece]) -> None:
        """Moves pieces in the order to form an A5 size image."""

        first_piece = pieces[order[0]]
        first_piece.translate(first_piece.outer_edge.edges[-1].p1, Point(0, 0))

        for idx in range(1, len(order)):
            current_piece = pieces[order[idx - 1]]
            next_piece = pieces[order[idx]]

            # Get the last outer edge of the current piece
            current_edge = current_piece.outer_edge.edges[-1]
            # Get the first outer edge of the next piece
            next_edge = next_piece.outer_edge.edges[0]

            MARGIN = 10.0 # margin between pieces

            # direction vector along the current edge
            dx = current_edge.p2.x - current_edge.p1.x
            dy = current_edge.p2.y - current_edge.p1.y

            # normalize
            length = math.hypot(dx, dy)
            ux = dx / length
            uy = dy / length

            # target point = p2 + margin along the direction
            target = Point(
                current_edge.p2.x + ux * MARGIN,
                current_edge.p2.y + uy * MARGIN
            )

            next_piece.translate(next_edge.p1, target)


    @staticmethod
    def get_amount_of_matching_points(current: PuzzlePiece, next_piece: PuzzlePiece) -> int:
        """Calculates the amount of matching points between two puzzle pieces."""
        current_piece_index = current.outer_edge.edges[-1].j
        next_piece_index = next_piece.outer_edge.edges[0].i

        max_steps = min(len(current.polygon.vertices), len(next_piece.polygon.vertices))
        steps = 0

        matching_points = 0

        def point_distance(current_index: int, next_index: int) -> float:
            current_point = current.polygon.vertices[current_index % len(current.polygon.vertices)]
            current_point_next = current.polygon.vertices[(current_index + 1) % len(current.polygon.vertices)]

            next_point = next_piece.polygon.vertices[next_index % len(next_piece.polygon.vertices)]
            next_point_next = next_piece.polygon.vertices[(next_index - 1) % len(next_piece.polygon.vertices)]

            # Check whether the direction from current_point to current_point_next is similar to the direction from next_point to next_point_next
            dx1 = current_point_next.x - current_point.x
            dy1 = current_point_next.y - current_point.y
            dx2 = next_point_next.x - next_point.x
            dy2 = next_point_next.y - next_point.y
            return math.hypot(dx1 - dx2, dy1 - dy2)

        # Check, whether the points match
        while steps < max_steps:
            distance = point_distance(current_piece_index, next_piece_index)

            if distance < 50.0:  # Threshold for matching points
                matching_points += 1
                current_piece_index += 1
                next_piece_index -= 1
            else:
                # check if any of the next few points match
                found_better = False
                # for look_ahead in range(1, 4):
                #     distance_ahead_1 = point_distance(current_piece_index, next_piece_index - look_ahead)
                #     distance_ahead_2 = point_distance(current_piece_index + look_ahead, next_piece_index)
                #     if distance_ahead_1 < 15.0 or distance_ahead_2 < 15.0:
                #         matching_points += 1
                #         current_piece_index += look_ahead + 1
                #         next_piece_index -= look_ahead + 1
                #         found_better = True
                #         break
                if not found_better:
                    break

            steps += 1


        return matching_points

    @staticmethod
    def rotate_to_fit(puzzle_piece: PuzzlePiece, piece: PuzzlePiece) -> PuzzlePiece:
        """Rotates a puzzle piece to fit the current puzzle piece."""
        # Get the last outer edge of the current puzzle piece
        current_edge = puzzle_piece.outer_edge.edges[-1]

        # Get the first outer edge of the new piece
        new_edge = piece.outer_edge.edges[0]

        # Calculate the angle of the current edge
        dx1 = current_edge.p2.x - current_edge.p1.x
        dy1 = current_edge.p2.y - current_edge.p1.y
        angle1 = math.atan2(dy1, dx1)

        # Calculate the angle of the new edge
        dx2 = new_edge.p2.x - new_edge.p1.x
        dy2 = new_edge.p2.y - new_edge.p1.y
        angle2 = math.atan2(dy2, dx2)

        # Calculate the rotation needed to align the new edge with the current edge
        rotation_needed = angle1 - angle2
        piece.rotate(rotation_needed)
        return piece


    if __name__ == "__main__":
        PUZZLE: dict[int, PuzzlePiece] = PuzzlePieceLoader.load_pieces()
        solve(PUZZLE)
        print_whole_puzzle_image(PUZZLE)

