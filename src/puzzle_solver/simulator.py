"""Main simulator module. Orchestrates the simulation process."""

import argparse
import logging
import os
import cv2 as cv

from .pull_pieces import pull_pieces
from .corners import detect_corners
from .component import PuzzlePiece, Point
from .utilities.draw_puzzle_piece import print_whole_puzzle_image
from .utilities import Solver
from .match import Match
from .greedy import Greedy

logger = logging.getLogger(__name__)


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
        default=200000,
        help="minimum contour area to keep",
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
        min_area=args.min_area,
        threshold_value=args.threshold,
    )

    # Step 2: Analyze pieces and detect corners
    corners = detect_corners(piece_images, args.outdir)
    logger.info("Detected corners for %d pieces, saved to %s", len(corners), args.outdir)

    # Step 3: create PuzzlePiece objects, analyze edges, etc.
    puzzle_pieces = {}
    for i, (filename, corner_list) in enumerate(corners):
        points = [Point(x=float(x), y=float(y)) for x, y in corner_list]
        piece = PuzzlePiece(points)
        puzzle_pieces[i] = piece
        logger.debug("Created PuzzlePiece from %s: %s", filename, piece)

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
            logger.warning("Failed to delete %s. Reason: %s", file_path, e)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
