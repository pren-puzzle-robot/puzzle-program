from __future__ import annotations

import math
from typing import Tuple
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..component.puzzle_piece import PuzzlePiece
from ..component.point import Point



def _compute_bounds(piece: PuzzlePiece) -> Tuple[float, float, float, float]:
    verts = piece.polygon.vertices
    xs = [p.x for p in verts]
    ys = [p.y for p in verts]
    return min(xs), max(xs), min(ys), max(ys)

def _to_img_coords(p: Point, xmin: float, ymin: float, scale: float, margin: int) -> Tuple[int, int]:
    x = int((p.x - xmin) * scale) + margin
    y = int((p.y - ymin) * scale) + margin
    return x, y

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
    - Outer edges: red
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

    # ----- Highlight outer edges (red, thicker) -----
    for e in piece.outer_edge.edges:
        x1, y1 = _to_img_coords(e.p1, xmin, ymin, scale, margin)
        x2, y2 = _to_img_coords(e.p2, xmin, ymin, scale, margin)
        draw.line([(x1, y1), (x2, y2)], fill=(255, 0, 0), width=4)

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
