from __future__ import annotations

import math
from typing import Tuple
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..component.outer_edge import OuterEdge
from ..component.puzzle_piece import PuzzlePiece
from ..component.point import Point


OUTER_EDGE_COLORS = (
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (148, 103, 189),
    (140, 86, 75),
    (227, 119, 194),
    (127, 127, 127),
    (188, 189, 34),
    (23, 190, 207),
)


def _compute_bounds(piece: PuzzlePiece) -> Tuple[float, float, float, float]:
    verts = piece.polygon.vertices
    xs = [p.x for p in verts]
    ys = [p.y for p in verts]
    return min(xs), max(xs), min(ys), max(ys)

def _to_img_coords(p: Point, xmin: float, ymin: float, scale: float, margin: int) -> Tuple[int, int]:
    x = int((p.x - xmin) * scale) + margin
    y = int((p.y - ymin) * scale) + margin
    return x, y


def _outer_edge_key(outer_edge: OuterEdge) -> tuple[tuple[int, int], ...]:
    return tuple((edge.i, edge.j) for edge in outer_edge.edges)


def _outer_edge_label_position(
    outer_edge: OuterEdge,
    xmin: float,
    ymin: float,
    scale: float,
    margin: int,
) -> tuple[int, int]:
    points = [edge.p1 for edge in outer_edge.edges] + [outer_edge.edges[-1].p2]
    mid_x = sum(point.x for point in points) / len(points)
    mid_y = sum(point.y for point in points) / len(points)
    return _to_img_coords(Point(mid_x, mid_y), xmin, ymin, scale, margin)


def _draw_outer_edge(
    draw: ImageDraw.ImageDraw,
    outer_edge: OuterEdge,
    xmin: float,
    ymin: float,
    scale: float,
    margin: int,
    color: tuple[int, int, int],
    width: int,
) -> None:
    for edge in outer_edge.edges:
        x1, y1 = _to_img_coords(edge.p1, xmin, ymin, scale, margin)
        x2, y2 = _to_img_coords(edge.p2, xmin, ymin, scale, margin)
        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

def render_and_show_puzzle_piece(piece: PuzzlePiece) -> None:
    """Render and display the puzzle piece using PIL."""
    img = render_puzzle_piece(piece, scale=0.5, margin=50)
    img.show(title="Puzzle Piece")

def render_puzzle_piece(
    piece: PuzzlePiece,
    scale: float = 1.0,
    margin: int = 40,
) -> Image.Image:
    """
    Render the puzzle piece to a new PIL image.

    - Polygon outline: black
    - Possible outer edges: colored
    - Selected outer edge: red
    - Points: small circles with index labels
    - Type text in the top left corner
    """
    xmin, xmax, ymin, ymax = _compute_bounds(piece)
    w = int((xmax - xmin) * scale) + 2 * margin
    h = int((ymax - ymin) * scale) + 2 * margin

    if w <= 0:
        w = 200
    if h <= 0:
        h = 200

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_small = ImageFont.truetype("arial.ttf", 14)
        font_big = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font_small = ImageFont.load_default()
        font_big = ImageFont.load_default()

    verts = piece.polygon.vertices
    n = len(verts)

    # ----- Draw full polygon outline (black) -----
    for i in range(n):
        p1 = verts[i]
        p2 = verts[(i + 1) % n]
        x1, y1 = _to_img_coords(p1, xmin, ymin, scale, margin)
        x2, y2 = _to_img_coords(p2, xmin, ymin, scale, margin)
        draw.line([(x1, y1), (x2, y2)], fill=(0, 0, 0), width=2)

    selected_outer_edge_key = _outer_edge_key(piece.outer_edge)

    # ----- Draw all possible outer edges (colored) -----
    for outer_edge_index, outer_edge in enumerate(piece.possible_outer_edges):
        color = OUTER_EDGE_COLORS[outer_edge_index % len(OUTER_EDGE_COLORS)]
        _draw_outer_edge(
            draw,
            outer_edge,
            xmin,
            ymin,
            scale,
            margin,
            color,
            width=3,
        )
        label_x, label_y = _outer_edge_label_position(
            outer_edge,
            xmin,
            ymin,
            scale,
            margin,
        )
        draw.text(
            (label_x + 4, label_y + 4),
            f"OE {outer_edge_index}: {outer_edge.type.value}",
            fill=color,
            font=font_small,
        )

    # ----- Highlight selected outer edge (red, thicker) -----
    for outer_edge in piece.possible_outer_edges:
        if _outer_edge_key(outer_edge) != selected_outer_edge_key:
            continue
        _draw_outer_edge(
            draw,
            outer_edge,
            xmin,
            ymin,
            scale,
            margin,
            (255, 0, 0),
            width=6,
        )
        break

    # ----- Draw points and indices -----
    r = 4
    for idx, p in enumerate(verts):
        x, y = _to_img_coords(p, xmin, ymin, scale, margin)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 0, 0), outline=None)
        draw.text((x + 6, y - 14), str(idx), fill=(0, 0, 255), font=font_small)

    # ----- Draw type text -----
    type_text = piece.type.value.upper()
    draw.text((10, 10), type_text, fill=(0, 128, 0), font=font_big)

    return img

def print_whole_puzzle_image(pieces: dict[int, PuzzlePiece]) -> Image.Image:
    """Renders and prints the full puzzle image from the pieces."""
    all_points = []
    for piece in pieces.values():
        all_points.extend(piece.polygon.vertices)

    # Determine bounding box
    min_x = min(p.x for p in all_points)
    min_y = min(p.y for p in all_points)
    max_x = max(p.x for p in all_points)
    max_y = max(p.y for p in all_points)

    width = int(math.ceil(max_x))
    height = int(math.ceil(max_y))

    print(min_x, min_y, max_x, max_y, width, height)

    # Transparent background
    img = Image.new("RGBA", (width, height), (255, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # Deterministic color per piece name
    def color_for_name(piece_id):
        # fixed seed based on name for stable colors
        rnd = random.Random(hash(piece_id) & 0xFFFFFFFF)
        r = rnd.randint(50, 230)
        g = rnd.randint(50, 230)
        b = rnd.randint(50, 230)
        return (r, g, b, 255)

    # Render each polygon onto the image
    for pid, piece in pieces.items():
        outline = color_for_name(pid)
        fill = (outline[0], outline[1], outline[2], 40)  # very light transparent fill

        # Filled polygon with colored border
        draw.polygon([(p.x, p.y) for p in piece.polygon.vertices], fill=fill, outline=outline)

        if (piece.polygon_before_expansion is not None):
            draw.polygon([(p.x, p.y) for p in piece.polygon_before_expansion.vertices], fill=None, outline=outline)

        cx, cy = piece.polygon.centroid().x, piece.polygon.centroid().y
        r = 5
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 255))

        label = (
            "Piece {}\n"
            "Rotation: {:.2f}\n"
            "Translation: ({:.2f}, {:.2f})\n"
            "Coords Relative to 0,0: ({:.2f}, {:.2f})"
        ).format(
            pid,
            piece.rotation,
            piece.translation[0], piece.translation[1],
            piece.polygon.centroid().x, piece.polygon.centroid().y
        )
        font = ImageFont.load_default(size=30)
        gap = 8  # pixels below centroid

        bbox = draw.multiline_textbbox((0, 0), label, font=font, spacing=4, align="center")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Position so the text block is centered horizontally under the centroid
        x = cx - text_w / 2
        y = cy + gap

        draw.multiline_text(
            (x, y),
            label,
            font=font,
            fill=(0, 0, 0, 255),
            spacing=4,
            align="center",
        )

    return img
