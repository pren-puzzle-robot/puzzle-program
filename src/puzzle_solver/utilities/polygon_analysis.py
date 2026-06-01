from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np

from ..component import Point, Polygon, Edge, OuterEdge

def _to_xy(v) -> Tuple[float, float]:
    """Convert Point to (x, y) tuple of floats."""
    return float(v.x), float(v.y)


def _seg_len(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    return float(math.hypot(dx, dy))


def _edges_from_polygon(poly: Polygon) -> List[Edge]:
    verts_raw = list(poly.vertices)
    n = len(verts_raw)
    edges: List[Edge] = []

    for i in range(n):
        j = (i + 1) % n
        x1, y1 = _to_xy(verts_raw[i])
        x2, y2 = _to_xy(verts_raw[j])
        p1 = Point(x1, y1)
        p2 = Point(x2, y2)
        length = _seg_len((x1, y1), (x2, y2))
        edges.append(Edge(i=i, j=j, p1=p1, p2=p2, length=length))

    return edges


def analyze_polygon(poly: Polygon) -> List[OuterEdge]:
    edges = _edges_from_polygon(poly)
    if not edges:
        return []

    outer_candidates = [
        e for e in edges
        if _edge_can_be_outer(e, poly)
    ]

    outer_candidates = _remove_edges_with_vertices_in_edge_cones(
        edges=outer_candidates,
        vertices=list(poly.vertices),
        cone_half_angle_deg=20.0,
    )

    if not outer_candidates:
        return []

    chains = _build_edge_chains(outer_candidates)
    combos = _contiguous_edge_combos(chains)

    combos = _remove_combos_not_right_angle(combos)

    outer_edges: List[OuterEdge] = [OuterEdge(edges=c) for c in combos if c]

    perimeter = poly.perimeter()
    outer_edges = [oe for oe in outer_edges if oe.length >= 0.1 * perimeter]

    return sorted(outer_edges, key=lambda oe: -oe.length)


def _edge_can_be_outer(edge: Edge, poly: Polygon, relative_tolerance: float = 1e-1) -> bool:
    p1, p2 = edge.p1, edge.p2
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    length = edge.length

    def signed_dist(q):
        # signed distance from q to the line p1->p2
        area2 = dx * (q.y - p1.y) - dy * (q.x - p1.x)
        return area2 / length

    # per-edge epsilon: grows with edge length
    eps = relative_tolerance * length

    s_centroid = signed_dist(poly.centroid())

    if abs(s_centroid) < eps:
        # centroid very close to the line => not a valid outer edge
        return False

    for v in poly.vertices:
        s_v = signed_dist(v)

        # points very close to the line are treated as "on" the line
        if abs(s_v) < eps:
            continue

        # if they have opposite signs and both are clearly off the line:
        if s_centroid * s_v < 0:
            return False

    return True


def _remove_edges_with_vertices_in_edge_cones(
    edges: List[Edge],
    vertices: List[Point],
    cone_half_angle_deg: float = 20.0,
) -> List[Edge]:
    vertex_count = len(vertices)

    if vertex_count <= 3 or not edges:
        return edges

    to_remove = set()

    for edge_index, edge in enumerate(edges):
        # Edge is a -> b, where:
        # edge.i = index of a in the original polygon
        # edge.j = index of b in the original polygon
        ignored_vertex_indices = {
            (edge.i - 1) % vertex_count,  # vertex before a
            edge.i,                       # a
            edge.j,                       # b
            (edge.j + 1) % vertex_count,  # vertex after b
        }

        for vertex_index, vertex in enumerate(vertices):
            if vertex_index in ignored_vertex_indices:
                continue

            if _is_point_inside_edge_end_cones(
                edge=edge,
                point=vertex,
                cone_half_angle_deg=cone_half_angle_deg,
            ):
                to_remove.add(edge_index)
                break

    return [
        edge
        for edge_index, edge in enumerate(edges)
        if edge_index not in to_remove
    ]


def _is_point_inside_edge_end_cones(
    edge: Edge,
    point,
    cone_half_angle_deg: float,
) -> bool:
    a = np.array((edge.p1.x, edge.p1.y), dtype=np.float64)
    b = np.array((edge.p2.x, edge.p2.y), dtype=np.float64)

    edge_vec = b - a

    if np.linalg.norm(edge_vec) < 1e-9:
        return False

    # Cone from b forwards
    in_forward_cone = _is_point_inside_cone(
        apex=b,
        axis=edge_vec,
        point=point,
        cone_half_angle_deg=cone_half_angle_deg,
    )

    # Cone from a backwards
    in_backward_cone = _is_point_inside_cone(
        apex=a,
        axis=-edge_vec,
        point=point,
        cone_half_angle_deg=cone_half_angle_deg,
    )

    return in_forward_cone or in_backward_cone


def _is_point_inside_cone(
    apex: np.ndarray,
    axis: np.ndarray,
    point,
    cone_half_angle_deg: float,
) -> bool:
    p = np.array((point.x, point.y), dtype=np.float64)

    point_vec = p - apex

    axis_len = np.linalg.norm(axis)
    point_len = np.linalg.norm(point_vec)

    if axis_len < 1e-9 or point_len < 1e-9:
        return False

    cos_angle = np.dot(axis, point_vec) / (axis_len * point_len)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)

    angle_deg = np.rad2deg(np.arccos(cos_angle))

    return angle_deg <= cone_half_angle_deg



def _build_edge_chains(edges: List[Edge]) -> List[List[Edge]]:
    """Group edges into ordered chains by connectivity (e.j == next.i)."""
    if not edges:
        return []

    # Maps vertex index -> edge
    by_start = {e.i: e for e in edges}  # outgoing edges
    by_end   = {e.j: e for e in edges}  # incoming edges

    chains: List[List[Edge]] = []
    visited = set()

    for edge in edges:
        if edge in visited:
            continue

        # walk backwards to the start of this chain
        current = edge
        backward_seen = {current}
        while current.i in by_end:
            previous = by_end[current.i]
            if previous is current or previous in visited or previous in backward_seen:
                break
            current = previous
            backward_seen.add(current)

        # walk forwards to build the full chain
        chain: List[Edge] = []
        chain_seen = set()
        while current not in visited and current not in chain_seen:
            chain.append(current)
            visited.add(current)
            chain_seen.add(current)

            if current.j in by_start and by_start[current.j] not in visited:
                current = by_start[current.j]
            else:
                break

        chains.append(chain)

    return chains

def _contiguous_edge_combos(chains: List[List[Edge]]) -> List[List[Edge]]:
    """From chains of edges, build all contiguous sub-chains (combos)."""
    combos: List[List[Edge]] = []

    for chain in chains:
        n = len(chain)
        for start in range(n):
            for end in range(start, n):
                combos.append(chain[start:end+1])

    return combos

def _remove_combos_not_right_angle(
    combos: List[List[Edge]],
    angle_tolerance_deg: float = 3.0,
) -> List[List[Edge]]:
    """
    Keep combos where the first vertex, last vertex, and at least one intermediate
    vertex form a right angle.

    Checks angle: first_vertex -> middle_vertex -> last_vertex
    """
    valid_combos: List[List[Edge]] = []

    for combo in combos:
        if len(combo) < 2:
            valid_combos.append(combo)
            continue

        # Assuming combo is an ordered path:
        # edge1.p1 -> edge1.p2 -> edge2.p2 -> edge3.p2 ...
        vertices = [combo[0].p1] + [edge.p2 for edge in combo]

        if len(vertices) < 3:
            continue

        first_vertex = vertices[0]
        last_vertex = vertices[-1]
        middle_vertices = vertices[1:-1]

        first_point = np.array((first_vertex.x, first_vertex.y))
        last_point = np.array((last_vertex.x, last_vertex.y))

        found_right_angle = False

        for middle_vertex in middle_vertices:
            middle_point = np.array((middle_vertex.x, middle_vertex.y))

            vec_to_first = first_point - middle_point
            vec_to_last = last_point - middle_point

            if np.linalg.norm(vec_to_first) < 1e-9 or np.linalg.norm(vec_to_last) < 1e-9:
                continue

            cos_angle = np.dot(vec_to_first, vec_to_last) / (
                np.linalg.norm(vec_to_first) * np.linalg.norm(vec_to_last)
            )
            cos_angle = np.clip(cos_angle, -1.0, 1.0)

            angle_deg = np.rad2deg(np.arccos(cos_angle))

            if abs(angle_deg - 90.0) <= angle_tolerance_deg:
                found_right_angle = True
                break

        if found_right_angle:
            valid_combos.append(combo)

    return valid_combos