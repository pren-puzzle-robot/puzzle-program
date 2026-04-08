"""Main simulator module. Orchestrates the simulation process."""

import argparse
import os
import cv2 as cv

from .pull_pieces import pull_pieces
from .corners import detect_corners
from .component import PuzzlePiece, Point
from .utilities.draw_puzzle_piece import print_whole_puzzle_image
from .utilities import Solver
from .match import Match
from .greedy import Greedy


def _resolve_min_area(value: int | None) -> int:
    if value is not None:
        return value

    raw_value = os.getenv("PUZZLE_SOLVER_MIN_AREA")
    if raw_value is None:
        return 200000

    try:
        return int(raw_value)
    except ValueError as exc:
        raise SystemExit("PUZZLE_SOLVER_MIN_AREA must be an integer") from exc


def _resolve_threshold(value: str | None) -> int | None:
    if value is not None:
        normalized = value.strip().lower()
        if normalized in {"", "none", "otsu"}:
            return None

        try:
            threshold_value = int(value)
        except ValueError as exc:
            raise SystemExit("--threshold must be an integer, 'none', or 'otsu'") from exc

        if not 0 <= threshold_value <= 255:
            raise SystemExit("--threshold must be between 0 and 255")
        return threshold_value

    raw_value = os.getenv("PUZZLE_SOLVER_THRESHOLD")
    if raw_value is None:
        return 140

    normalized = raw_value.strip().lower()
    if normalized in {"", "none", "otsu"}:
        return None

    try:
        threshold_value = int(raw_value)
    except ValueError as exc:
        raise SystemExit(
            "PUZZLE_SOLVER_THRESHOLD must be an integer, 'none', or 'otsu'"
        ) from exc

    if not 0 <= threshold_value <= 255:
        raise SystemExit("PUZZLE_SOLVER_THRESHOLD must be between 0 and 255")

    return threshold_value


def main():
    ap = argparse.ArgumentParser(description="Simulate puzzle assembly process")
    ap.add_argument("--image", required=True, help="path to input image")
    ap.add_argument("--outdir", default="./output", help="folder to save results")
    ap.add_argument(
        "--variant",
        required=False,
        default="fast",
        help="variant of algorithm to be used (e.i. fast or greedy)",
    )
    ap.add_argument(
        "--min_area",
        type=int,
        default=None,
        help="minimum contour area to keep; defaults to PUZZLE_SOLVER_MIN_AREA or 200000",
    )
    ap.add_argument(
        "--threshold",
        type=str,
        default=None,
        help="fixed grayscale threshold; use 'none' or 'otsu' for Otsu thresholding",
    )
    args = ap.parse_args()

    ensure_out_dir(args.outdir)

    img = cv.imread(args.image)
    if img is None:
        raise SystemExit(f"Could not read image: {args.image}")

    # Step 1: Isolate puzzle pieces from the image
    piece_images = pull_pieces(
        img,
        args.outdir,
        min_area=_resolve_min_area(args.min_area),
        threshold_value=_resolve_threshold(args.threshold),
    )

    # Step 2: Analyze pieces and detect corners
    corners = detect_corners(piece_images, args.outdir)
    print(f"Detected corners for {len(corners)} pieces, saved to {args.outdir}")

    # Step 3: create PuzzlePiece objects, analyze edges, etc.
    puzzle_pieces = {}
    for i, (filename, corner_list) in enumerate(corners):
        points = [Point(x=float(x), y=float(y)) for x, y in corner_list]
        piece = PuzzlePiece(points)
        puzzle_pieces[i] = piece
        print(f"Created PuzzlePiece from {filename}: {piece}")

    # Step 4: Solve the puzzle
    solver: Solver

    if args.variant == "fast":
        solver = Match()
    elif args.variant == "greedy":
        solver = Greedy(puzzle_pieces)
    else:
        solver = Match()

    solver.solve(puzzle_pieces)

    solved = print_whole_puzzle_image(puzzle_pieces)
    solved.show()


def ensure_out_dir(outdir: str) -> None:
    """Ensure the output directory exists."""
    os.makedirs(outdir, exist_ok=True)

    # delete all files in the output directory
    for filename in os.listdir(outdir):
        file_path = os.path.join(outdir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")


if __name__ == "__main__":
    main()
