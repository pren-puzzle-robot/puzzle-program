from __future__ import annotations
import math
from typing import Iterable, List, Optional

from .point import Point


class Polygon:
    """
    Simple 2D polygon represented by an ordered list of Point vertices.
    - vertices are stored in CCW or CW order (user-provided)
    - requires at least 3 vertices
    """

    def __init__(self, vertices: Iterable[Point]):
        verts: List[Point] = [Point(float(p.x), float(p.y)) for p in vertices]
        if len(verts) < 3:
            raise ValueError("Polygon requires at least 3 vertices")
        self._vertices: List[Point] = verts

    @property
    def vertices(self) -> List[Point]:
        return list(self._vertices)

    def edges(self) -> List[tuple[Point, Point]]:
        """Return list of (Point, Point) edges in order, wrapping around."""
        v = self._vertices
        return [(v[i], v[(i + 1) % len(v)]) for i in range(len(v))]

    def perimeter(self) -> float:
        per = 0.0
        for a, b in self.edges():
            dx = b.x - a.x
            dy = b.y - a.y
            per += math.hypot(dx, dy)
        return per

    def area(self) -> float:
        """Absolute area using shoelace formula."""
        v = self._vertices
        a = 0.0
        n = len(v)
        for i in range(n):
            x1, y1 = v[i].x, v[i].y
            x2, y2 = v[(i + 1) % n].x, v[(i + 1) % n].y
            a += x1 * y2 - x2 * y1
        return abs(a) * 0.5

    def centroid(self) -> Point:
        """Centroid of the polygon (Shoelace formula)."""
        v = self._vertices
        n = len(v)
        a = 0.0
        cx = 0.0
        cy = 0.0

        for i in range(n):
            x0, y0 = v[i].x, v[i].y
            x1, y1 = v[(i + 1) % n].x, v[(i + 1) % n].y

            cross = x0 * y1 - x1 * y0
            a += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross

        a *= 0.5

        # Degenerate polygon: fallback to mean
        if abs(a) < 1e-12:
            sx = sum(p.x for p in v) / n
            sy = sum(p.y for p in v) / n
            return Point(sx, sy)

        cx /= (6.0 * a)
        cy /= (6.0 * a)
        return Point(cx, cy)

    def translate(self, dx: float, dy: float) -> None:
        """Translate polygon in-place."""
        self._vertices = [Point(p.x + dx, p.y + dy) for p in self._vertices]

    def rotate(self, angle_radians: float, origin: Optional[Point] = None) -> None:
        """Rotate polygon in-place."""
        if origin is None:
            origin = self.centroid()

        ox, oy = origin.x, origin.y
        c = math.cos(angle_radians)
        s = math.sin(angle_radians)

        new_vertices = []
        for p in self._vertices:
            tx = p.x - ox
            ty = p.y - oy
            rx = tx * c - ty * s + ox
            ry = tx * s + ty * c + oy
            new_vertices.append(Point(rx, ry))
        
        self._vertices = new_vertices

    def __len__(self) -> int:
        return len(self._vertices)

    def __repr__(self) -> str:
        return f"Polygon({self._vertices})"
