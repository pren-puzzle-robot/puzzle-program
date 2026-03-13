
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


from .point import Point
from .edge import Edge

class PieceType(str, Enum):
    CORNER = "corner"
    EDGE = "edge"  # default if not clearly a corner

@dataclass
class OuterEdge:
    """Outer edge of a piece, expressed in terms of polygon vertex indices."""

    type: PieceType
    edges: List[Edge]

    @property
    def length(self) -> float:
        """Return the total length of the OuterEdge."""
        return sum(edge.length for edge in self.edges)

    def rotate(self, angle_rad: float, center: Point) -> None:
        """Return a new OuterEdge rotated around center by angle_rad."""
        self.edges = [edge.rotated(angle_rad, center) for edge in self.edges]

    def translated(self, dx: float, dy: float) -> OuterEdge:
        """Return a new OuterEdge translated by (dx, dy)."""
        translated_edges = [edge.translated(dx, dy) for edge in self.edges]
        return OuterEdge(edges=translated_edges)

    def __init__(self, edges: List[Edge]) -> None:
        self.edges = edges
        self.type = PieceType.EDGE if len(edges) == 1 else PieceType.CORNER