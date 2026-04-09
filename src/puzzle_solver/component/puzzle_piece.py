from __future__ import annotations
import logging
from typing import Iterable, List

from .point import Point
from .polygon import Polygon
from .outer_edge import OuterEdge, PieceType

logger = logging.getLogger(__name__)


class PuzzlePiece:
    """
    Represents a single puzzle piece.

    The piece is defined by:
    - a polygon (constructed from a list of Point instances)
    - a type (corner or edge)
    - a list of detected outer edges
    """

    _polygon: Polygon
    _possible_possible_outer_edges: List[OuterEdge]
    _outer_edge: OuterEdge

    _rotation: float = 0.0  # in radians
    _translation: tuple[float, float] = (0.0, 0.0)

    def __init__(self, points: Iterable[Point]) -> None:
        points_list: List[Point] = list(points)
        if len(points_list) < 3:
            raise ValueError("PuzzlePiece requires at least 3 points")

        self._translation: tuple[float, float] = (0.0, 0.0)
        self._polygon = Polygon(points_list)

        # First analysis
        # analysis = analyze_polygon(self._polygon)
        # # Normalize vertex order based on this analysis
        # self._normalize_vertex_order(analysis)

        # Re-analyze after rotation so indices and outer_edges match
        from ..utilities import analyze_polygon

        final_analysis = analyze_polygon(self._polygon)
        self._possible_outer_edges = final_analysis
        self._outer_edge = final_analysis[0]

    # def _normalize_vertex_order(self, analysis: PieceAnalysis) -> None:
    #     """
    #     Rotate polygon vertices so that the first vertex is the
    #     end point (j) of a chosen outer edge.
    #     """
    #     if not analysis.outer_edges:
    #         # Should not happen with only corner/edge pieces,
    #         # but do nothing if it does.
    #         return

    #     # Choose the last outer edge as canonical
    #     edge = analysis.outer_edges[-1]
    #     target_index = edge.j  # last vertex index of that edge

    #     verts = self._polygon.vertices
    #     n = len(verts)
    #     if n == 0:
    #         return

    #     # Rotate list: new_verts[0] == verts[target_index]
    #     target_index = target_index % n
    #     new_verts = verts[target_index:] + verts[:target_index]

    #     # Replace polygon with rotated vertices
    #     self._polygon = Polygon(new_verts)

    def get_triplet(self, index: int, direction: bool) -> tuple[Point, Point, Point]:
        """
        Get the point at the given `index` but also the two surounding\n
        points before and after. Works like a wrapper. After the last\n
        in the list comes the first again. The boolean says if you are\n
        going forward or backwards. Example `direction` == `true` -> forward,\n
        `false` -> backwards.
        """
        points: list[Point] = self.polygon.vertices
        length: int = len(points)
        inverted: int = 1 if direction else -1

        prev_index: int = (index - 1 * inverted) % length
        next_index: int = (index + 1 * inverted) % length

        norm_index = index % length

        return (points[prev_index], points[norm_index], points[next_index])
    
    def get_possible_limits(self) -> List[tuple[int, int]]:
        """
        Get the lowest and the highest index of all possible `OuterEdge`s
        detected for this piece.
        """
        results: List[tuple[int, int]] = []
        possible_outer_edges: List[OuterEdge] = self.possible_outer_edges

        for outer_edge in possible_outer_edges:
            limits = self._get_limits(outer_edge)
            results.append(limits)
        return results

    def _get_limits(self, outer_edge: OuterEdge | None = None) -> tuple[int, int]:
        """
        Get the lowest and the highest index of the given `OuterEdge`\n
        In case that none is provided the method will simply take the\n
        first in the list of possible ones.\n
        """
        if outer_edge is None:
            if len(self.possible_outer_edges) > 0:
                outer_edge = self.possible_outer_edges[0]
            else:
                raise RuntimeError("No outer edges detected for this piece")

        data: list[tuple[int, int]] = [
            edge.get_indices for edge in outer_edge.edges
        ]
        length: int = len(self.polygon.vertices)

        vertices: set[int] = {v for u, v in data for v in (u, v)}

        if not vertices:
            raise RuntimeError("No vertices found for outer edge")

        return self._get_start_end_indices(length, vertices)

    @staticmethod
    def _get_start_end_indices(length: int, vertices: set[int]) -> tuple[int, int]:
        if length <= 0:
            raise ValueError("Length must be positive")

        points_sorted = sorted(vertices)

        if len(points_sorted) == 1:
            v = points_sorted[0]
            return (v, v)

        m = len(points_sorted)
        gaps: list[int] = []
        for i in range(m):
            a = points_sorted[i]
            b = points_sorted[(i + 1) % m]
            gap = (b - a) % length
            gaps.append(gap)

        max_gap_idx = max(range(m), key=lambda i: gaps[i])

        start = points_sorted[(max_gap_idx + 1) % m]
        end = points_sorted[max_gap_idx]

        return (start, end)


    def rotate(self, angle_rad: float) -> None:
        """Rotate the puzzle piece polygon by the given angle in radians."""
        self._rotation += angle_rad

        self._polygon.rotate(angle_rad)
        for edge in self._possible_outer_edges:
            edge.rotate(angle_rad, self.polygon.centroid())

    def translate(self, from_point: Point, to_point: Point) -> None:
        """Translate the puzzle piece so that from_point moves to to_point."""
        dx = to_point.x - from_point.x
        dy = to_point.y - from_point.y

        self._translation = (self._translation[0] + dx, self._translation[1] + dy)
        logger.debug("Translation: %s", self._translation)

        self._polygon.translate(dx, dy)
        self._possible_outer_edges = [
            edge.translated(dx, dy) for edge in self._possible_outer_edges
        ]
        self._outer_edge = self.outer_edge.translated(dx, dy)

    @property
    def polygon(self) -> Polygon:
        return self._polygon

    @property
    def type(self) -> PieceType:
        return self.outer_edge.type

    @property
    def possible_outer_edges(self) -> List[OuterEdge]:
        """Detected outer edges of this piece."""
        return self._possible_outer_edges

    @property
    def outer_edge(self) -> OuterEdge:
        """Outer edge of this piece."""
        return self._outer_edge

    @property
    def is_corner(self) -> bool:
        return self.outer_edge.type == PieceType.CORNER

    @property
    def is_edge(self) -> bool:
        return self.outer_edge.type == PieceType.EDGE

    @property
    def rotation(self) -> float:
        """Get the current rotation of the puzzle piece in radians."""
        return self._rotation

    @property
    def translation(self) -> tuple[float, float]:
        """Get the current translation (dx, dy) of the puzzle piece."""
        return self._translation

    def __repr__(self) -> str:
        return f"PuzzlePiece(polygon={self._polygon!r}, outer_edge={self.outer_edge})"
