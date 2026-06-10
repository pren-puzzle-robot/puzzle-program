from __future__ import annotations

import argparse
from pathlib import Path
import statistics
import time

import cv2
import numpy as np

from camera_controller import CameraController


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
OUTER_CORNER_INDICES = (3, 0, 2, 2)


GENERATED_NAME_PARTS = ("_aruco_marked", "_flattened")


def _iter_image_paths(image_dir: Path, include_generated: bool) -> list[Path]:
    return sorted(
        path
        for path in image_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and (
            include_generated
            or not any(name_part in path.stem for name_part in GENERATED_NAME_PARTS)
        )
    )


def _detect_single_pass_marker_ids(
    image,
    dictionary_name: str,
    marker_ids: tuple[int, ...],
) -> set[int]:
    aruco = cv2.aruco
    dictionary_id = getattr(aruco, dictionary_name, None)
    if dictionary_id is None:
        raise ValueError(f"Unknown ArUco dictionary: {dictionary_name}")

    dictionary = aruco.getPredefinedDictionary(dictionary_id)
    detector_parameters = aruco.DetectorParameters()
    detector_parameters.adaptiveThreshWinSizeMin = 3
    detector_parameters.adaptiveThreshWinSizeMax = 41
    detector_parameters.adaptiveThreshWinSizeStep = 4
    if hasattr(aruco, "ArucoDetector"):
        detector = aruco.ArucoDetector(dictionary, detector_parameters)
        _, ids, _ = detector.detectMarkers(image)
    else:
        _, ids, _ = aruco.detectMarkers(
            image,
            dictionary,
            parameters=detector_parameters,
        )

    if ids is None:
        return set()
    required_ids = set(marker_ids)
    return {int(marker_id) for marker_id in ids.flatten()} & required_ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark robust ArUco detection over a directory of images."
    )
    parser.add_argument(
        "image_dir",
        nargs="?",
        default=str(Path.cwd().parent / "inputs"),
        help="directory containing benchmark images; defaults to ../inputs",
    )
    parser.add_argument(
        "--marker-ids",
        type=int,
        nargs=4,
        metavar=("A", "B", "C", "D"),
        default=(0, 1, 2, 3),
        help="required marker IDs in rectangle order",
    )
    parser.add_argument(
        "--dictionary",
        default="DICT_4X4_50",
        help="OpenCV ArUco dictionary name",
    )
    parser.add_argument(
        "--no-infer",
        action="store_true",
        help="disable one-missing-marker geometry recovery",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only failures and the summary",
    )
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="include generated *_flattened* and *_aruco_marked* images",
    )
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    if not image_dir.is_dir():
        raise SystemExit(f"Image directory not found: {image_dir}")

    image_paths = _iter_image_paths(image_dir, args.include_generated)
    if not image_paths:
        raise SystemExit(f"No benchmark images found in: {image_dir}")

    marker_ids = tuple(args.marker_ids)
    required_ids = set(marker_ids)
    controller = CameraController()

    baseline_successes = 0
    robust_detected_successes = 0
    inferred_successes = 0
    failures = 0
    inference_errors: list[float] = []
    started_at = time.perf_counter()

    if not args.quiet:
        print(
            "image,status,baseline_found,robust_detected,inferred,missing,elapsed_ms"
        )

    for image_path in image_paths:
        image = cv2.imread(str(image_path))
        if image is None:
            failures += 1
            print(f"{image_path.name},READ_ERROR,,,,,0.0")
            continue

        image_started_at = time.perf_counter()
        baseline_found = _detect_single_pass_marker_ids(
            image,
            args.dictionary,
            marker_ids,
        )
        if required_ids <= baseline_found:
            baseline_successes += 1

        _, corners, ids = controller._detect_aruco_markers(
            image,
            args.dictionary,
            required_marker_ids=marker_ids,
        )
        detected_marker_corners = controller._marker_corners_by_id(corners, ids)
        robust_detected_ids = set(detected_marker_corners)
        if required_ids <= robust_detected_ids:
            robust_detected_successes += 1
            for marker_id in marker_ids:
                missing_index = marker_ids.index(marker_id)
                detected_without_marker = {
                    current_marker_id: current_marker_corners
                    for current_marker_id, current_marker_corners in detected_marker_corners.items()
                    if current_marker_id != marker_id
                }
                inferred_marker_corners, inferred_marker_ids = (
                    controller._infer_missing_aruco_marker_corners(
                        detected_without_marker,
                        marker_ids,
                        OUTER_CORNER_INDICES,
                    )
                )
                if marker_id not in inferred_marker_ids:
                    continue

                outer_corner_index = OUTER_CORNER_INDICES[missing_index]
                actual_outer_corner = detected_marker_corners[marker_id][
                    outer_corner_index
                ]
                inferred_outer_corner = inferred_marker_corners[marker_id][
                    outer_corner_index
                ]
                inference_errors.append(
                    float(np.linalg.norm(inferred_outer_corner - actual_outer_corner))
                )

        inferred_ids: set[int] = set()
        final_marker_corners = detected_marker_corners
        if not args.no_infer:
            final_marker_corners, inferred_ids = (
                controller._infer_missing_aruco_marker_corners(
                    detected_marker_corners,
                    marker_ids,
                    OUTER_CORNER_INDICES,
                )
            )

        final_ids = set(final_marker_corners)
        missing_ids = required_ids - final_ids
        if missing_ids:
            failures += 1
            status = "MISSING"
        elif inferred_ids:
            inferred_successes += 1
            status = "INFERRED"
        else:
            status = "OK"

        elapsed_ms = (time.perf_counter() - image_started_at) * 1000
        if not args.quiet or status == "MISSING":
            print(
                f"{image_path.name},{status},"
                f"{sorted(baseline_found)},"
                f"{sorted(robust_detected_ids)},"
                f"{sorted(inferred_ids)},"
                f"{sorted(missing_ids)},"
                f"{elapsed_ms:.1f}"
            )

    elapsed_seconds = time.perf_counter() - started_at
    print()
    print(f"Images: {len(image_paths)}")
    print(f"Single-pass all markers: {baseline_successes}/{len(image_paths)}")
    print(f"Robust decoded all markers: {robust_detected_successes}/{len(image_paths)}")
    print(f"Recovered by geometry: {inferred_successes}/{len(image_paths)}")
    print(f"Failures after recovery: {failures}/{len(image_paths)}")
    if inference_errors:
        print(
            "Leave-one-out inference error: "
            f"mean={statistics.fmean(inference_errors):.1f}px, "
            f"median={statistics.median(inference_errors):.1f}px, "
            f"max={max(inference_errors):.1f}px, "
            f"samples={len(inference_errors)}"
        )
    print(f"Elapsed: {elapsed_seconds:.1f}s")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
