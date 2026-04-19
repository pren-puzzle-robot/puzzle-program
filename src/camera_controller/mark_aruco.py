from __future__ import annotations

import argparse

from camera_controller import CameraController


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect and mark all ArUco markers in an image."
    )
    parser.add_argument("image", help="path to the input image")
    parser.add_argument(
        "--output",
        default=None,
        help="optional path for the annotated output image",
    )
    parser.add_argument(
        "--dictionary",
        default="DICT_4X4_50",
        help="OpenCV ArUco dictionary name",
    )
    args = parser.parse_args()

    controller = CameraController()
    result = controller.mark_aruco_markers(
        source=args.image,
        destination=args.output,
        dictionary_name=args.dictionary,
    )
    print(result)


if __name__ == "__main__":
    main()
