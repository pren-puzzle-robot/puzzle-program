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
    args = parser.parse_args()

    output_size = None
    if args.width is not None or args.height is not None:
        if args.width is None or args.height is None:
            raise SystemExit("Both --width and --height are required together.")
        output_size = (args.width, args.height)

    controller = CameraController()
    result = controller.flatten_image_with_aruco(
        source=args.image,
        marker_ids=tuple(args.marker_ids),
        dictionary_name=args.dictionary,
        output_size=output_size,
    )
    print(result)


if __name__ == "__main__":
    main()
