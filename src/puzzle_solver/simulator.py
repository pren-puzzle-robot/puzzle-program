"""Command-line entry point for the Shapely-based puzzle solver."""

from __future__ import annotations

import argparse
import logging

from .solver import PuzzleSolver

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate puzzle solving from an image")
    parser.add_argument("--image", required=True, help="Path to the input image")
    parser.add_argument("--outdir", default="./output", help="Folder for debug output")
    parser.add_argument(
        "--variant",
        default="fast",
        help="Packing quality hint. Use 'quality' for more rotation candidates.",
    )
    parser.add_argument(
        "--min_area",
        type=int,
        default=60000,
        help="Minimum contour area to keep",
    )
    parser.add_argument(
        "--threshold",
        default=None,
        help="Fixed grayscale threshold; use 'none' or 'otsu' for automatic selection",
    )
    parser.add_argument(
        "--clearance",
        type=float,
        default=0.0,
        help="Minimum spacing between packed polygons in pixels",
    )
    parser.add_argument(
        "--max_overlap_ratio",
        type=float,
        default=0.08,
        help="Allowed overlap per piece as a fraction of polygon area",
    )
    parser.add_argument(
        "--max_empty_ratio",
        type=float,
        default=0.10,
        help="Preferred maximum empty area inside the solution bounding box",
    )
    args = parser.parse_args()

    solver = PuzzleSolver(
        output_dir=args.outdir,
        variant=args.variant,
        min_area=args.min_area,
        threshold_value=args.threshold,
        clearance=args.clearance,
        max_overlap_ratio=args.max_overlap_ratio,
        max_empty_ratio=args.max_empty_ratio,
    )
    placements = solver.solve(args.image)
    logger.info("Produced %d placements", len(placements))
    for placement in placements:
        print(placement)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
