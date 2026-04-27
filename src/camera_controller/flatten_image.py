from __future__ import annotations

import argparse

from camera_controller import CameraController


def main() -> None:
    parser = argparse.ArgumentParser(description="Flatten an image using ArUco markers.")
    parser.add_argument("image", help="path to the input image")
    parser.add_argument(
        "--marker-ids",
        type=int,
        nargs=4,
        metavar=("TOP_LEFT", "TOP_RIGHT", "BOTTOM_RIGHT", "BOTTOM_LEFT"),
        default=(0, 1, 2, 3),
        help="marker IDs in rectangle order",
    )
    parser.add_argument(
        "--dictionary",
        default="DICT_4X4_50",
        help="OpenCV ArUco dictionary name",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="optional output width in pixels",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="optional output height in pixels",
    )
    parser.add_argument(
        "--corner-offsets-percent",
        type=float,
        nargs=8,
        metavar=(
            "TL_NEXT_PCT",
            "TL_PREV_PCT",
            "TR_NEXT_PCT",
            "TR_PREV_PCT",
            "BR_NEXT_PCT",
            "BR_PREV_PCT",
            "BL_NEXT_PCT",
            "BL_PREV_PCT",
        ),
        default=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        help=(
            "manual per-corner offsets in percent along local edges: "
            "for each corner, first toward the next corner, then toward the previous corner; "
            "corners are ordered top-left, top-right, bottom-right, bottom-left"
        ),
    )
    args = parser.parse_args()

    output_size = None
    if args.width is not None or args.height is not None:
        if args.width is None or args.height is None:
            raise SystemExit("Both --width and --height are required together.")
        output_size = (args.width, args.height)
    corner_offset_percentages = tuple(
        (args.corner_offsets_percent[index], args.corner_offsets_percent[index + 1])
        for index in range(0, len(args.corner_offsets_percent), 2)
    )

    controller = CameraController()
    result = controller.flatten_image_with_aruco(
        source=args.image,
        marker_ids=tuple(args.marker_ids),
        dictionary_name=args.dictionary,
        output_size=output_size,
        corner_offset_percentages=corner_offset_percentages,
    )
    print(result)


if __name__ == "__main__":
    main()
