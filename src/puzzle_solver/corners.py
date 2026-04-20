from __future__ import annotations

import json
import logging
import os
import re
import sys
from glob import glob
from math import acos, degrees

import cv2
import numpy as np
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry.polygon import orient

logger = logging.getLogger(__name__)


def _turn_angle_deg(prev_point: np.ndarray, point: np.ndarray, next_point: np.ndarray) -> float:
    incoming = prev_point - point
    outgoing = next_point - point

    if np.allclose(incoming, 0) or np.allclose(outgoing, 0):
        return 0.0

    denom = np.linalg.norm(incoming) * np.linalg.norm(outgoing)
    if denom <= 1e-9:
        return 0.0

    cosine = np.clip(float(np.dot(incoming, outgoing) / denom), -1.0, 1.0)
    interior = degrees(acos(cosine))
    return 180.0 - interior


def _largest_piece_contour(binary_image: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def _contour_to_polygon(contour: np.ndarray) -> ShapelyPolygon | None:
    points = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
    if len(points) < 3:
        return None

    polygon = ShapelyPolygon(points)
    if polygon.is_empty:
        return None

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty:
        return None

    if isinstance(polygon, MultiPolygon):
        polygon = max(polygon.geoms, key=lambda geom: geom.area)

    if not isinstance(polygon, ShapelyPolygon) or polygon.area <= 0:
        return None

    return orient(polygon, sign=1.0)


def _simplify_piece_polygon(
    polygon: ShapelyPolygon,
    approx_frac: float,
    min_corner_dist: float,
) -> ShapelyPolygon:
    perimeter = polygon.length
    tolerance = max(perimeter * approx_frac, min_corner_dist * 0.25, 1.0)
    
    simplified = polygon.simplify(tolerance, preserve_topology=True)
    if simplified.is_empty:
        return polygon

    if not simplified.is_valid:
        simplified = simplified.buffer(0)

    if isinstance(simplified, MultiPolygon):
        simplified = max(simplified.geoms, key=lambda geom: geom.area)

    if not isinstance(simplified, ShapelyPolygon) or simplified.area <= 0:
        return polygon

    return orient(simplified, sign=1.0)


def _prune_vertices(
    vertices: np.ndarray,
    min_turn_deg: float,
    min_corner_dist: float,
) -> np.ndarray:
    if len(vertices) <= 3:
        return vertices

    filtered: list[np.ndarray] = []
    for index, point in enumerate(vertices):
        prev_point = vertices[(index - 1) % len(vertices)]
        next_point = vertices[(index + 1) % len(vertices)]

        prev_len = np.linalg.norm(point - prev_point)
        next_len = np.linalg.norm(next_point - point)
        turn_angle = _turn_angle_deg(prev_point, point, next_point)

        if prev_len < min_corner_dist * 0.5 and next_len < min_corner_dist * 0.5:
            continue
        if turn_angle < min_turn_deg and min(prev_len, next_len) < min_corner_dist:
            continue

        filtered.append(point)

    if len(filtered) < 3:
        return vertices

    filtered_array = np.asarray(filtered, dtype=np.float64)

    changed = True
    while changed and len(filtered_array) > 3:
        changed = False
        for index in range(len(filtered_array)):
            point = filtered_array[index]
            next_point = filtered_array[(index + 1) % len(filtered_array)]
            if np.linalg.norm(next_point - point) >= min_corner_dist:
                continue

            prev_point = filtered_array[(index - 1) % len(filtered_array)]
            after_next = filtered_array[(index + 2) % len(filtered_array)]
            current_turn = _turn_angle_deg(prev_point, point, next_point)
            next_turn = _turn_angle_deg(point, next_point, after_next)

            drop_index = index if current_turn <= next_turn else (index + 1) % len(filtered_array)
            filtered_array = np.delete(filtered_array, drop_index, axis=0)
            changed = True
            break

    return filtered_array


def detect_corners_for_piece(
    image_path: str,
    approx_frac: float = 0.002,
    min_turn_deg: float = 30.0,
    min_corner_dist: int = 40,
) -> np.ndarray | None:
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        logger.error("Could not open %s", image_path)
        return None

    _, binary_image = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contour = _largest_piece_contour(binary_image)
    if contour is None:
        logger.warning("No contour found in %s", image_path)
        return None

    polygon = _contour_to_polygon(contour)
    if polygon is None:
        logger.warning("Could not construct polygon for %s", image_path)
        return None

    polygon = _simplify_piece_polygon(
        polygon,
        approx_frac=approx_frac,
        min_corner_dist=float(min_corner_dist),
    )

    vertices = np.asarray(polygon.exterior.coords[:-1], dtype=np.float64)
    vertices = _prune_vertices(
        vertices,
        min_turn_deg=min_turn_deg,
        min_corner_dist=float(min_corner_dist),
    )

    if len(vertices) < 3:
        logger.warning("Corner detection produced fewer than 3 vertices for %s", image_path)
        return None

    return np.rint(vertices).astype(np.int32).reshape(-1, 1, 2)


def print_debug_image(image_path: str, corners: np.ndarray | None, output_path: str) -> None:
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        logger.error("Could not open %s for debug output", image_path)
        return

    color_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    if corners is not None and len(corners) >= 2:
        cv2.polylines(color_img, [corners], True, (0, 255, 255), 2)

    if corners is not None:
        for i, point in enumerate(corners):
            x, y = point[0]
            cv2.circle(color_img, (x, y), 6, (0, 0, 255), -1)
            cv2.putText(
                color_img,
                str(i),
                (x + 8, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 0),
                2,
            )

    cv2.imwrite(output_path, color_img)


def _corners_to_pairs(corners: np.ndarray) -> list[tuple[int, int]]:
    return [(int(point[0][0]), int(point[0][1])) for point in corners][::-1]


def detect_corners(images: list[str], out_path: str) -> list[tuple[str, list[tuple[int, int]]]]:
    corners_per_piece: list[tuple[str, list[tuple[int, int]]]] = []
    for image_path in images:
        filename = os.path.basename(image_path)
        name, ext = os.path.splitext(filename)
        corners = detect_corners_for_piece(image_path)

        output_image = os.path.join(out_path, f"{name}_corners{ext}")
        print_debug_image(image_path, corners, output_image)

        if corners is None:
            continue

        corners_per_piece.append((filename, _corners_to_pairs(corners)))

    with open(os.path.join(out_path, "corners.json"), "w", encoding="utf-8") as file:
        json.dump(corners_per_piece, file, indent=2)

    return corners_per_piece


if __name__ == "__main__":
    src_folder = sys.argv[1] if len(sys.argv) >= 2 else "../output"
    output_json = os.path.join(src_folder, "corners.json")

    approx_frac = 0.002   # bigger = more simplification
    min_turn_deg = 30.0   # bigger = fewer corners, only sharp ones

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Scanning folder: %s", src_folder)
    images = [
        path
        for path in glob(os.path.join(src_folder, "piece_*.png"))
        if re.fullmatch(r".*piece_\d+\.png", path)
    ]
    results: list[tuple[str, list[tuple[int, int]]]] = []

    if not images:
        logger.error("No piece_*.png files found.")
        sys.exit(1)

    for image_path in images:
        filename = os.path.basename(image_path)
        name, ext = os.path.splitext(filename)
        output_image = os.path.join(src_folder, f"{name}_corners{ext}")

        corners = detect_corners_for_piece(
            image_path,
            approx_frac=approx_frac,
            min_turn_deg=min_turn_deg,
        )
        if corners is not None:
            results.append((filename, _corners_to_pairs(corners)))

        print_debug_image(image_path, corners, output_image)

    with open(output_json, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)
    logger.info("Saved all corners to %s", output_json)
