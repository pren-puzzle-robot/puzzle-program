"""Main simulator module. Orchestrates the simulation process."""

import argparse
import os
import cv2 as cv

from pull_pieces import pull_pieces
from corners import detect_corners
from component import PuzzlePiece, Point
from utilities.draw_puzzle_piece import print_whole_puzzle_image
from utilities import Solver
from match import Match
from greedy import Greedy


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
    args = ap.parse_args()

    ensure_out_dir(args.outdir)

    img = cv.imread(args.image)
    if img is None:
        raise SystemExit(f"Could not read image: {args.image}")

    # Step 1: Isolate puzzle pieces from the image
    piece_images = pull_pieces(img, args.outdir)

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
