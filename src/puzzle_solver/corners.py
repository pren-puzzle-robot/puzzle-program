import cv2
import numpy as np
import sys, os, json
from math import acos, degrees
from glob import glob
import re

def filter_by_turn_angle(pts, min_turn_deg=45.0):
    """
    Keep only points where the contour direction changes by at least `min_turn_deg`.

    - pts: Nx1x2 contour from approxPolyDP
    - min_turn_deg: minimum change between incoming and outgoing edge (in degrees)
      Example: 45 => only corners with direction change >= 45 degrees.
    """
    pts = np.asarray(pts, dtype=np.int32)
    if len(pts) <= 3:
        return pts

    keep = []
    n = len(pts)

    for i in range(n):
        p_prev = pts[(i - 1) % n][0]
        p_cur  = pts[i][0]
        p_next = pts[(i + 1) % n][0]

        v1 = p_prev - p_cur
        v2 = p_next - p_cur

        # Skip degenerate vectors (duplicate or very close points)
        if np.allclose(v1, 0) or np.allclose(v2, 0):
            continue

        denom = (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)
        c = np.dot(v1, v2) / denom
        c = np.clip(c, -1.0, 1.0)

        ang = degrees(acos(c)) # interior angle in [0, 180]
        turn = 180.0 - ang # 0 = straight, bigger = sharper corner

        if turn >= min_turn_deg:
            keep.append([p_cur])

    if not keep:
        # If everything got filtered out (e.g. almost perfect circle),
        # fall back to the original pts so you still see something.
        return pts

    return np.array(keep, dtype=np.int32)

def group_close_points(pts, min_dist=10):
    """
    Group points that lie closer than `min_dist` pixels and replace each
    group with a single averaged point.

    - pts: Nx1x2 or Nx2 array of points
    - min_dist: distance threshold for grouping
    """
    pts = np.asarray(pts, dtype=np.float32)
    if pts.ndim == 3:   # (N, 1, 2) from OpenCV contours
        pts2 = pts[:, 0, :]  # -> (N, 2)
    else:
        pts2 = pts

    n = len(pts2)
    if n == 0:
        return pts

    used = np.zeros(n, dtype=bool)
    new_points = []

    for i in range(n):
        if used[i]:
            continue

        # Start new group with point i
        group = [pts2[i]]
        used[i] = True

        # Collect all points close to point i
        for j in range(i + 1, n):
            if used[j]:
                continue
            d = np.linalg.norm(pts2[j] - pts2[i])
            if d < min_dist:
                group.append(pts2[j])
                used[j] = True

        # Average coordinates in this group
        mean_pt = np.mean(group, axis=0)
        new_points.append(mean_pt)

    new_points = np.round(np.array(new_points)).astype(np.int32)
    # Return in contour format (N,1,2)
    return new_points.reshape(-1, 1, 2)


def detect_corners_for_piece(
    image_path,
    approx_frac=0.002,
    min_turn_deg=30.0,
    min_corner_dist=10  # minimal distance between corners in pixels
):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        print(f"Error: could not open {image_path}")
        return None

    _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        print(f"No contour found in {image_path}")
        return None

    cnt = max(cnts, key=cv2.contourArea)

    eps = approx_frac * cv2.arcLength(cnt, True)
    poly = cv2.approxPolyDP(cnt, eps, True)

    # 1) Group corners that are too close to each other
    corners = group_close_points(poly, min_dist=min_corner_dist)

    # 2) Keep only strong turns
    corners = filter_by_turn_angle(corners, min_turn_deg=min_turn_deg)

    return corners

def print_debug_image(image_path: str, corners: np.ndarray, output_path: str) -> None:
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    color_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(color_img, [corners], -1, (0, 255, 255), 2)

    for i, p in enumerate(corners):
        x, y = p[0]
        cv2.circle(color_img, (x, y), 6, (0, 0, 255), -1)
        cv2.putText(color_img, str(i), (x + 8, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    cv2.imwrite(output_path, color_img)

def detect_corners(images: list[str], out_path: str) -> dict[str, list[tuple[int, int]]]:
    corners_per_piece = []
    for image_path in images:
        filename = os.path.basename(image_path)
        name, ext = os.path.splitext(filename)
        corners = detect_corners_for_piece(
            image_path
        )

        output_image = os.path.join(out_path, f"{name}_corners{ext}")
        print_debug_image(image_path, corners, output_image)

        corners_per_piece.append((filename, [(int(p[0][0]), int(p[0][1])) for p in corners]))
    
    with open(os.path.join(out_path, "corners.json"), "w", encoding="utf-8") as f:
        json.dump(corners_per_piece, f, indent=2)
        
    return corners_per_piece

if __name__ == "__main__":
    # Default folder: current or specified
    src_folder = sys.argv[1] if len(sys.argv) >= 2 else "../output"
    output_json = os.path.join(src_folder, "corners.json")

    approx_frac = 0.002   # bigger = more simplification
    min_turn_deg = 30.0   # bigger = fewer corners, only sharp ones

    print(f"Scanning folder: {src_folder}")
    images = [
        f for f in glob(os.path.join(src_folder, "piece_*.png"))
        if re.fullmatch(r".*piece_\d+\.png", f)
    ]
    results = []

    if not images:
        print("No piece_*.png files found.")
        sys.exit(1)

    for img_path in images:
        filename = os.path.basename(img_path)
        name, ext = os.path.splitext(filename)
        out_filename= f"{name}_corners{ext}"
        corners = detect_corners_for_piece(
            img_path,
            approx_frac=approx_frac,
            min_turn_deg=min_turn_deg
        )
        if corners is not None:
            results.append((filename, [(int(p[0][0]), int(p[0][1])) for p in corners]))

        print_debug_image(
            img_path,
            corners,
            os.path.join(src_folder, out_filename)
        )

    # Save all results to JSON
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved all corners to {output_json}")
