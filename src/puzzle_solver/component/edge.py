from __future__ import annotations

import math
from dataclasses import dataclass

from .point import Point

@dataclass
class Edge:
    """Edge of a piece, expressed in terms of polygon vertex indices."""

    i: int  # start vertex index
    j: int  # end vertex index (wrapped)
    p1: Point  # start point
    p2: Point  # end point
    length: float  # Euclidean length

    @property
    def get_indices(self) -> tuple[int, int]:
        """Return the indices of the outer edge."""
        return self.i, self.j

    def rotated(self, angle_rad: float, center: Point) -> Edge:
        """Return a new Edge rotated around center by angle_rad."""
        def rotate_point(p: Point, angle: float) -> Point:
            s = math.sin(angle)
            c = math.cos(angle)

            # translate point back to origin:
            p_translated_x = p.x - center.x
            p_translated_y = p.y - center.y

            # rotate point
            x_new = p_translated_x * c - p_translated_y * s
            y_new = p_translated_x * s + p_translated_y * c

            # translate point back:
            x_final = x_new + center.x
            y_final = y_new + center.y

            return Point(x_final, y_final)

        new_p1 = rotate_point(self.p1, angle_rad)
        new_p2 = rotate_point(self.p2, angle_rad)
        new_length = math.hypot(new_p2.x - new_p1.x, new_p2.y - new_p1.y)

        return Edge(i=self.i, j=self.j, p1=new_p1, p2=new_p2, length=new_length)
    
    def translated(self, dx: float, dy: float) -> Edge:
        """Return a new Edge translated by (dx, dy)."""
        new_p1 = Point(self.p1.x + dx, self.p1.y + dy)
        new_p2 = Point(self.p2.x + dx, self.p2.y + dy)
        return Edge(i=self.i, j=self.j, p1=new_p1, p2=new_p2, length=self.length)

    def __repr__(self):
        return f"Edge(i={self.i}, j={self.j}, length={self.length:.2f}, \n\tp1={self.p1}, \n\tp2={self.p2})"

    def __hash__(self):
        return hash((self.i, self.j, self.p1.x, self.p1.y, self.p2.x, self.p2.y, self.length))