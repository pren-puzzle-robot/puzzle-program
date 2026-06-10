from __future__ import annotations

import json
import logging
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

import cv2
import numpy as np

from .exceptions import (
    ArucoMarkersError,
    CameraConnectionError,
)

logger = logging.getLogger(__name__)


class CameraController:
    """Captures images from a GoPro Hero 7 Black connected via Wi-Fi."""

    def __init__(
        self,
        gopro_base_url: str = "http://10.5.5.9",
        media_base_url: str = "http://10.5.5.9:8080",
        download_dir: str = "captures",
        calibration_file: str | None = None,
        capture_delay_seconds: float = 4.5,
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self.gopro_base_url = gopro_base_url.rstrip("/")
        self.media_base_url = media_base_url.rstrip("/")
        self.download_dir = Path(download_dir)
        self.calibration_file = (
            Path(calibration_file)
            if calibration_file is not None
            else Path(__file__).with_name("calibration.npz")
        )
        self.capture_delay_seconds = capture_delay_seconds
        self.request_timeout_seconds = request_timeout_seconds

    def _get_json(self, url: str) -> dict:
        logger.debug("Fetching JSON from %s", url)
        req = urllib.request.Request(url=url, method="GET")
        with urllib.request.urlopen(req, timeout=self.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def _send_get(self, url: str) -> None:
        logger.debug("Sending GET request to %s", url)
        req = urllib.request.Request(url=url, method="GET")
        with urllib.request.urlopen(req, timeout=self.request_timeout_seconds):
            pass

    def _try_get_json(self, urls: list[str]) -> dict:
        last_error: Exception | None = None
        for url in urls:
            try:
                return self._get_json(url)
            except Exception as exc:
                last_error = exc
                logger.debug("Request to %s failed: %s", url, exc)

        raise CameraConnectionError(f"All media list endpoints failed: {urls}") from last_error

    def _try_send_get(self, urls: list[str]) -> None:
        last_error: Exception | None = None
        for url in urls:
            try:
                self._send_get(url)
                return
            except Exception as exc:
                last_error = exc
                logger.debug("Request to %s failed: %s", url, exc)

        raise CameraConnectionError(f"All shutter endpoints failed: {urls}") from last_error

    def _set_zoom_percent(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise ValueError("zoom percent must be between 0 and 100")

        zoom_urls = [
            f"{self.gopro_base_url}/gp/gpControl/command/digital_zoom?range_pcnt={percent}"
        ]
        logger.info("Setting camera digital zoom to %d%%", percent)
        try:
            self._try_send_get(zoom_urls)
        except CameraConnectionError:
            logger.warning(
                "Camera did not accept digital zoom command; continuing without enforcing %d%% zoom",
                percent,
            )

    def _download_file(self, source_url: str, destination: Path) -> None:
        logger.debug("Downloading %s to %s", source_url, destination)
        req = urllib.request.Request(url=source_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout_seconds) as response:
                destination.write_bytes(response.read())
        except urllib.error.URLError as exc:
            raise CameraConnectionError(
                f"Failed to download captured image from {source_url}"
            ) from exc

    def _undistort_image(self, source: Path) -> Path:
        logger.info("Undistorting captured image using calibration %s", self.calibration_file)
        if not self.calibration_file.exists():
            raise FileNotFoundError(
                f"Calibration file not found: {self.calibration_file}"
            )

        data = np.load(self.calibration_file)
        camera_matrix = data["camera_matrix"]
        dist_coeffs = data["dist_coeffs"]

        image = cv2.imread(str(source))
        if image is None:
            raise RuntimeError(f"Unable to read captured image: {source}")

        undistorted = cv2.undistort(image, camera_matrix, dist_coeffs)
        destination = source.with_stem(f"{source.stem}_undistorted")
        if not cv2.imwrite(str(destination), undistorted):
            raise RuntimeError(f"Unable to write undistorted image: {destination}")

        logger.info("Undistorted image written to %s", destination)
        return destination

    def _detect_aruco_markers(
        self,
        image: np.ndarray,
        dictionary_name: str,
        required_marker_ids: tuple[int, ...] | None = None,
    ) -> tuple[object, list[np.ndarray], np.ndarray | None]:
        if not hasattr(cv2, "aruco"):
            raise RuntimeError("OpenCV ArUco module is not available")

        aruco = cv2.aruco
        dictionary_id = getattr(aruco, dictionary_name, None)
        if dictionary_id is None:
            raise ValueError(f"Unknown ArUco dictionary: {dictionary_name}")

        dictionary = aruco.getPredefinedDictionary(dictionary_id)
        required_ids = (
            set(required_marker_ids) if required_marker_ids is not None else None
        )
        attempts = (
            (None, "bgr", "base"),
            (1800, "bgr", "subpix"),
            (1800, "gray", "subpix"),
            (1800, "clahe", "const5"),
            (1800, "sharp", "const5"),
            (1800, "dark", "const5"),
            (2200, "clahe", "const3"),
        )

        detected_marker_corners: dict[int, np.ndarray] = {}
        detected_marker_ids: list[int] = []
        for max_dimension, preprocessing_name, parameter_profile in attempts:
            detection_image, scale = self._resize_for_aruco_detection(
                image,
                max_dimension,
            )
            prepared_image = self._prepare_aruco_detection_image(
                detection_image,
                preprocessing_name,
            )
            detector_parameters = self._create_aruco_detector_parameters(
                aruco,
                parameter_profile,
            )
            if hasattr(aruco, "ArucoDetector"):
                detector = aruco.ArucoDetector(dictionary, detector_parameters)
                corners, ids, _ = detector.detectMarkers(prepared_image)
            else:
                corners, ids, _ = aruco.detectMarkers(
                    prepared_image,
                    dictionary,
                    parameters=detector_parameters,
                )

            if ids is None:
                continue

            for marker_corner, marker_id in zip(corners, ids.flatten(), strict=False):
                detected_marker_id = int(marker_id)
                if required_ids is not None and detected_marker_id not in required_ids:
                    continue
                if detected_marker_id in detected_marker_corners:
                    continue

                original_scale_corner = marker_corner[0].astype(np.float32)
                if scale != 1.0:
                    original_scale_corner = original_scale_corner / scale
                detected_marker_corners[detected_marker_id] = original_scale_corner
                detected_marker_ids.append(detected_marker_id)

            if required_ids is not None and required_ids.issubset(
                detected_marker_corners
            ):
                break

        if not detected_marker_ids:
            return aruco, [], None

        merged_corners = [
            detected_marker_corners[marker_id].reshape((1, 4, 2)).astype(np.float32)
            for marker_id in detected_marker_ids
        ]
        merged_ids = np.array(
            [[marker_id] for marker_id in detected_marker_ids],
            dtype=np.int32,
        )
        return aruco, merged_corners, merged_ids

    @staticmethod
    def _create_aruco_detector_parameters(
        aruco: object,
        profile: str,
    ) -> object:
        detector_parameters = aruco.DetectorParameters()
        detector_parameters.adaptiveThreshWinSizeMin = 3
        detector_parameters.adaptiveThreshWinSizeMax = 41
        detector_parameters.adaptiveThreshWinSizeStep = 4

        if profile == "base":
            return detector_parameters

        detector_parameters.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
        detector_parameters.cornerRefinementMaxIterations = 50
        detector_parameters.cornerRefinementMinAccuracy = 0.03
        detector_parameters.errorCorrectionRate = 0.8
        detector_parameters.perspectiveRemovePixelPerCell = 8
        detector_parameters.minOtsuStdDev = 3.0
        detector_parameters.minDistanceToBorder = 1
        detector_parameters.minCornerDistanceRate = 0.02

        if profile == "const5":
            detector_parameters.adaptiveThreshConstant = 5
        elif profile == "const3":
            detector_parameters.adaptiveThreshConstant = 3
        elif profile != "subpix":
            raise ValueError(f"Unknown ArUco detector parameter profile: {profile}")

        return detector_parameters

    @staticmethod
    def _resize_for_aruco_detection(
        image: np.ndarray,
        max_dimension: int | None,
    ) -> tuple[np.ndarray, float]:
        if max_dimension is None:
            return image, 1.0

        height, width = image.shape[:2]
        largest_dimension = max(height, width)
        if largest_dimension <= max_dimension:
            return image, 1.0

        scale = max_dimension / largest_dimension
        resized = cv2.resize(
            image,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
        return resized, scale

    @staticmethod
    def _prepare_aruco_detection_image(
        image: np.ndarray,
        preprocessing_name: str,
    ) -> np.ndarray:
        if preprocessing_name == "bgr":
            return image

        gray = (
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            if image.ndim == 3
            else image.copy()
        )
        if preprocessing_name == "gray":
            return gray
        if preprocessing_name == "clahe":
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            return clahe.apply(gray)
        if preprocessing_name == "sharp":
            blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
            return cv2.addWeighted(gray, 1.8, blur, -0.8, 0)
        if preprocessing_name == "dark":
            return cv2.convertScaleAbs(gray, alpha=1.5, beta=-35)

        raise ValueError(f"Unknown ArUco preprocessing pass: {preprocessing_name}")

    @staticmethod
    def _marker_corners_by_id(
        corners: list[np.ndarray],
        ids: np.ndarray | None,
    ) -> dict[int, np.ndarray]:
        if ids is None:
            return {}

        detected_marker_corners: dict[int, np.ndarray] = {}
        for marker_corner, marker_id in zip(corners, ids.flatten(), strict=False):
            detected_marker_corners[int(marker_id)] = marker_corner[0]
        return detected_marker_corners

    @classmethod
    def _infer_missing_aruco_marker_corners(
        cls,
        detected_marker_corners: dict[int, np.ndarray],
        marker_ids: tuple[int, int, int, int],
        outer_corner_indices: tuple[int, int, int, int],
    ) -> tuple[dict[int, np.ndarray], set[int]]:
        missing_marker_ids = [
            marker_id for marker_id in marker_ids if marker_id not in detected_marker_corners
        ]
        if len(missing_marker_ids) != 1:
            return detected_marker_corners, set()

        missing_marker_id = missing_marker_ids[0]
        missing_index = marker_ids.index(missing_marker_id)
        outer_points: dict[int, np.ndarray] = {}
        for index, marker_id in enumerate(marker_ids):
            marker_corners = detected_marker_corners.get(marker_id)
            if marker_corners is not None:
                outer_points[index] = marker_corners[outer_corner_indices[index]]

        if len(outer_points) != 3:
            return detected_marker_corners, set()

        missing_outer_point = cls._infer_missing_outer_corner_from_marker_edges(
            detected_marker_corners,
            marker_ids,
            outer_corner_indices,
            missing_index,
            outer_points,
        )
        if missing_outer_point is None:
            missing_outer_point = cls._infer_missing_outer_corner_affine(
                missing_index,
                outer_points,
            )

        inferred_marker_corners = cls._synthetic_marker_corners_from_outer_corner(
            missing_outer_point,
            outer_corner_indices[missing_index],
            detected_marker_corners.values(),
        )
        inferred_marker_map = dict(detected_marker_corners)
        inferred_marker_map[missing_marker_id] = inferred_marker_corners
        return inferred_marker_map, {missing_marker_id}

    @classmethod
    def _infer_missing_outer_corner_from_marker_edges(
        cls,
        detected_marker_corners: dict[int, np.ndarray],
        marker_ids: tuple[int, int, int, int],
        outer_corner_indices: tuple[int, int, int, int],
        missing_index: int,
        outer_points: dict[int, np.ndarray],
    ) -> np.ndarray | None:
        previous_index = (missing_index - 1) % 4
        next_index = (missing_index + 1) % 4
        previous_previous_index = (missing_index - 2) % 4
        next_next_index = (missing_index + 2) % 4

        previous_marker_corners = detected_marker_corners[marker_ids[previous_index]]
        previous_marker_outer_index = outer_corner_indices[previous_index]
        previous_known_side_line = cls._choose_marker_edge_line_toward_point(
            previous_marker_corners,
            previous_marker_outer_index,
            outer_points[previous_previous_index],
        )
        previous_missing_side_line = cls._other_marker_edge_line(
            previous_marker_corners,
            previous_marker_outer_index,
            previous_known_side_line,
        )

        next_marker_corners = detected_marker_corners[marker_ids[next_index]]
        next_marker_outer_index = outer_corner_indices[next_index]
        next_known_side_line = cls._choose_marker_edge_line_toward_point(
            next_marker_corners,
            next_marker_outer_index,
            outer_points[next_next_index],
        )
        next_missing_side_line = cls._other_marker_edge_line(
            next_marker_corners,
            next_marker_outer_index,
            next_known_side_line,
        )

        missing_outer_point = cls._intersect_lines(
            previous_missing_side_line,
            next_missing_side_line,
        )
        if missing_outer_point is None:
            return None

        affine_outer_point = cls._infer_missing_outer_corner_affine(
            missing_index,
            outer_points,
        )
        known_side_lengths = [
            np.linalg.norm(
                outer_points[index] - outer_points[(index + 1) % 4]
            )
            for index in outer_points
            if (index + 1) % 4 in outer_points
        ]
        max_reasonable_error = (
            max(12.0, min(40.0, max(known_side_lengths) * 0.04))
            if known_side_lengths
            else 40.0
        )
        if (
            np.linalg.norm(missing_outer_point - affine_outer_point)
            > max_reasonable_error
        ):
            return None

        return missing_outer_point.astype(np.float32)

    @staticmethod
    def _infer_missing_outer_corner_affine(
        missing_index: int,
        outer_points: dict[int, np.ndarray],
    ) -> np.ndarray:
        if missing_index == 0:
            return outer_points[1] + outer_points[3] - outer_points[2]
        if missing_index == 1:
            return outer_points[0] + outer_points[2] - outer_points[3]
        if missing_index == 2:
            return outer_points[1] + outer_points[3] - outer_points[0]
        return outer_points[0] + outer_points[2] - outer_points[1]

    @classmethod
    def _choose_marker_edge_line_toward_point(
        cls,
        marker_corners: np.ndarray,
        outer_corner_index: int,
        target_point: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        candidate_lines = cls._outer_marker_edge_lines(
            marker_corners,
            outer_corner_index,
        )
        return min(
            candidate_lines,
            key=lambda line: cls._point_to_line_distance(target_point, line),
        )

    @classmethod
    def _other_marker_edge_line(
        cls,
        marker_corners: np.ndarray,
        outer_corner_index: int,
        known_line: tuple[np.ndarray, np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray]:
        candidate_lines = cls._outer_marker_edge_lines(
            marker_corners,
            outer_corner_index,
        )
        if np.array_equal(candidate_lines[0][1], known_line[1]):
            return candidate_lines[1]
        return candidate_lines[0]

    @staticmethod
    def _outer_marker_edge_lines(
        marker_corners: np.ndarray,
        outer_corner_index: int,
    ) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
        corners = np.asarray(marker_corners, dtype=np.float32)
        outer_corner = corners[outer_corner_index]
        previous_corner = corners[(outer_corner_index - 1) % 4]
        next_corner = corners[(outer_corner_index + 1) % 4]
        return (outer_corner, previous_corner), (outer_corner, next_corner)

    @staticmethod
    def _point_to_line_distance(
        point: np.ndarray,
        line: tuple[np.ndarray, np.ndarray],
    ) -> float:
        line_start, line_end = line
        line_vector = line_end - line_start
        line_length = np.linalg.norm(line_vector)
        if line_length == 0:
            return float("inf")
        return float(
            abs(CameraController._cross_2d(line_vector, point - line_start))
            / line_length
        )

    @staticmethod
    def _intersect_lines(
        first_line: tuple[np.ndarray, np.ndarray],
        second_line: tuple[np.ndarray, np.ndarray],
    ) -> np.ndarray | None:
        first_start, first_end = first_line
        second_start, second_end = second_line
        first_direction = first_end - first_start
        second_direction = second_end - second_start
        denominator = CameraController._cross_2d(
            first_direction,
            second_direction,
        )
        if abs(denominator) < 1e-6:
            return None

        offset = second_start - first_start
        factor = CameraController._cross_2d(offset, second_direction) / denominator
        return first_start + factor * first_direction

    @staticmethod
    def _cross_2d(first_vector: np.ndarray, second_vector: np.ndarray) -> float:
        return float(
            first_vector[0] * second_vector[1]
            - first_vector[1] * second_vector[0]
        )

    @staticmethod
    def _synthetic_marker_corners_from_outer_corner(
        outer_point: np.ndarray,
        outer_corner_index: int,
        known_marker_corners: object,
    ) -> np.ndarray:
        right_vectors: list[np.ndarray] = []
        down_vectors: list[np.ndarray] = []
        for marker_corners in known_marker_corners:
            corners = np.asarray(marker_corners, dtype=np.float32)
            right_vectors.extend((corners[1] - corners[0], corners[2] - corners[3]))
            down_vectors.extend((corners[3] - corners[0], corners[2] - corners[1]))

        right_vector = np.mean(np.array(right_vectors), axis=0)
        down_vector = np.mean(np.array(down_vectors), axis=0)
        outer = np.asarray(outer_point, dtype=np.float32)

        if outer_corner_index == 0:
            top_left = outer
            top_right = outer + right_vector
            bottom_right = outer + right_vector + down_vector
            bottom_left = outer + down_vector
        elif outer_corner_index == 1:
            top_left = outer - right_vector
            top_right = outer
            bottom_right = outer + down_vector
            bottom_left = outer - right_vector + down_vector
        elif outer_corner_index == 2:
            top_left = outer - right_vector - down_vector
            top_right = outer - down_vector
            bottom_right = outer
            bottom_left = outer - right_vector
        else:
            top_left = outer - down_vector
            top_right = outer + right_vector - down_vector
            bottom_right = outer + right_vector
            bottom_left = outer

        return np.array(
            [top_left, top_right, bottom_right, bottom_left],
            dtype=np.float32,
        )

    def mark_aruco_markers(
        self,
        source: str | Path,
        destination: str | Path | None = None,
        dictionary_name: str = "DICT_4X4_50",
    ) -> str:
        logger.info("Marking ArUco markers in image %s", source)
        source_path = Path(source)
        image = cv2.imread(str(source_path))
        if image is None:
            raise RuntimeError(f"Unable to read image for marker annotation: {source_path}")

        aruco, corners, ids = self._detect_aruco_markers(image, dictionary_name)
        annotated = image.copy()

        if ids is not None:
            aruco.drawDetectedMarkers(annotated, corners, ids)

            for marker_corner, marker_id in zip(corners, ids.flatten(), strict=False):
                center = marker_corner[0].mean(axis=0)
                center_point = tuple(np.rint(center).astype(int))
                cv2.circle(annotated, center_point, 8, (0, 0, 255), -1)
                cv2.putText(
                    annotated,
                    f"id={int(marker_id)}",
                    (center_point[0] + 10, center_point[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )

        if destination is not None:
            output_path = Path(destination) / f"{source_path.stem}_aruco_marked{source_path.suffix}"
        else:
            output_path = source_path.with_name(f"{source_path.stem}_aruco_marked{source_path.suffix}")

        if not cv2.imwrite(str(output_path), annotated):
            raise RuntimeError(f"Unable to write annotated image: {output_path}")

        resolved_output_path = str(output_path.resolve())
        logger.info(
            "Annotated image written to %s with %d markers",
            resolved_output_path,
            0 if ids is None else len(ids),
        )
        return resolved_output_path

    def flatten_image_with_aruco(
        self,
        source: str | Path,
        marker_ids: tuple[int, int, int, int] = (0, 1, 2, 3),
        dictionary_name: str = "DICT_4X4_50",
        output_size: tuple[int, int] | None = None,
        corner_offset_percentages: tuple[
            tuple[float, float],
            tuple[float, float],
            tuple[float, float],
            tuple[float, float],
        ] = ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
    ) -> str:
        logger.info("Flattening image %s using ArUco markers %s", source, marker_ids)
        source_path = Path(source)
        image = cv2.imread(str(source_path))
        if image is None:
            raise RuntimeError(f"Unable to read image for flattening: {source_path}")

        _, corners, ids = self._detect_aruco_markers(
            image,
            dictionary_name,
            required_marker_ids=marker_ids,
        )

        if ids is None:
            raise ArucoMarkersError("No ArUco markers detected in image")

        detected_marker_corners = self._marker_corners_by_id(corners, ids)

        # OpenCV returns ArUco corners in marker order:
        # top-left, top-right, bottom-right, bottom-left.
        # The markers are passed in rectangle order, so pick the outer corner of
        # each marker instead of the marker center.
        outer_corner_indices = (3, 0, 2, 2)
        detected_marker_corners, inferred_marker_ids = (
            self._infer_missing_aruco_marker_corners(
                detected_marker_corners,
                marker_ids,
                outer_corner_indices,
            )
        )
        if inferred_marker_ids:
            logger.warning(
                "Inferred missing ArUco marker corners from geometry: %s",
                sorted(inferred_marker_ids),
            )

        missing_marker_ids = [
            marker_id for marker_id in marker_ids if marker_id not in detected_marker_corners
        ]
        if missing_marker_ids:
            raise ArucoMarkersError(
                f"Missing required ArUco markers: {missing_marker_ids}"
            )

        source_points = np.array(
            [
                detected_marker_corners[marker_id][corner_index]
                for marker_id, corner_index in zip(marker_ids, outer_corner_indices, strict=True)
            ],
            dtype=np.float32,
        )
        labels = ("top-left", "top-right", "bottom-right", "bottom-left")

        offset_percentages = np.array(corner_offset_percentages, dtype=np.float32)
        if offset_percentages.shape != (4, 2):
            raise ValueError(
                "corner_offset_percentages must contain four (dx, dy) percentage pairs"
            )
        offset_points = np.zeros((4, 2), dtype=np.float32)
        for index in range(4):
            current_point = source_points[index]
            next_point = source_points[(index + 1) % 4]
            previous_point = source_points[(index - 1) % 4]
            next_vector = next_point - current_point
            previous_vector = previous_point - current_point
            offset_points[index] = (
                next_vector * (offset_percentages[index, 0] / 100.0)
                + previous_vector * (offset_percentages[index, 1] / 100.0)
            )

        adjusted_source_points = source_points + offset_points

        debug_image = image.copy()
        detected_polygon_points = np.rint(source_points).astype(np.int32).reshape((-1, 1, 2))
        adjusted_polygon_points = (
            np.rint(adjusted_source_points).astype(np.int32).reshape((-1, 1, 2))
        )
        cv2.polylines(debug_image, [detected_polygon_points], True, (255, 0, 0), 2, cv2.LINE_AA)
        cv2.polylines(debug_image, [adjusted_polygon_points], True, (0, 255, 0), 3, cv2.LINE_AA)
        for label, detected_point, adjusted_point, offset, percentage in zip(
            labels,
            np.rint(source_points).astype(np.int32),
            np.rint(adjusted_source_points).astype(np.int32),
            np.rint(offset_points).astype(np.int32),
            offset_percentages,
            strict=True,
        ):
            detected_point_tuple = tuple(detected_point)
            adjusted_point_tuple = tuple(adjusted_point)
            cv2.circle(debug_image, detected_point_tuple, 4, (255, 0, 0), -1)
            cv2.circle(debug_image, adjusted_point_tuple, 4, (0, 0, 255), -1)
            cv2.line(
                debug_image,
                detected_point_tuple,
                adjusted_point_tuple,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                debug_image,
                (
                    f"{label} dx={int(offset[0])} dy={int(offset[1])} "
                    f"(next={percentage[0]:.2f}%, prev={percentage[1]:.2f}%)"
                ),
                (adjusted_point_tuple[0] + 20, adjusted_point_tuple[1] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        if output_size is None:
            adjusted_width_top = np.linalg.norm(adjusted_source_points[1] - adjusted_source_points[0])
            adjusted_width_bottom = np.linalg.norm(
                adjusted_source_points[2] - adjusted_source_points[3]
            )
            adjusted_height_right = np.linalg.norm(
                adjusted_source_points[2] - adjusted_source_points[1]
            )
            adjusted_height_left = np.linalg.norm(
                adjusted_source_points[3] - adjusted_source_points[0]
            )
            width = max(1, int(round(max(adjusted_width_top, adjusted_width_bottom))))
            height = max(1, int(round(max(adjusted_height_left, adjusted_height_right))))
        else:
            width, height = output_size
            if width <= 0 or height <= 0:
                raise ValueError("output_size must contain positive dimensions")

        destination_points = np.array(
            [
                [0.0, 0.0],
                [width - 1.0, 0.0],
                [width - 1.0, height - 1.0],
                [0.0, height - 1.0],
            ],
            dtype=np.float32,
        )

        perspective_transform = cv2.getPerspectiveTransform(
            adjusted_source_points,
            destination_points,
        )
        flattened = cv2.warpPerspective(image, perspective_transform, (width, height))

        destination = source_path.with_stem(f"{source_path.stem}_flattened")
        if not cv2.imwrite(str(destination), flattened):
            raise RuntimeError(f"Unable to write flattened image: {destination}")

        debug_destination = source_path.with_stem(f"{source_path.stem}_flattened_debug")
        if not cv2.imwrite(str(debug_destination), debug_image):
            raise RuntimeError(f"Unable to write flattening debug image: {debug_destination}")

        resolved_destination = str(destination.resolve())
        logger.info("Flattened image written to %s", resolved_destination)
        logger.info("Flattening debug image written to %s", debug_destination.resolve())
        return resolved_destination

    def capture_frame(self) -> str:
        """
        Trigger a GoPro photo capture, download the latest image, and return local path.
        """
        mode_urls = [f"{self.gopro_base_url}/gp/gpControl/command/mode?p=1"]
        sub_mode_urls = [
            f"{self.gopro_base_url}/gp/gpControl/command/sub_mode?mode=1&sub_mode=0"
        ]
        shutter_urls = [
            f"{self.gopro_base_url}/gp/gpControl/command/shutter?p=1",
            f"{self.gopro_base_url}/gopro/camera/shutter/start",
        ]
        logger.info("Setting camera mode to photo")
        self._try_send_get(mode_urls)

        logger.info("Setting camera sub-mode to single photo")
        self._try_send_get(sub_mode_urls)

        self._set_zoom_percent(100)

        logger.info("Triggering camera shutter")
        self._try_send_get(shutter_urls)

        logger.debug(
            "Waiting %.2f seconds for camera media to become available",
            self.capture_delay_seconds,
        )
        time.sleep(self.capture_delay_seconds)

        media_list_urls = [
            f"{self.gopro_base_url}/gp/gpMediaList",
            f"{self.gopro_base_url}/gopro/media/list",
        ]
        media = self._try_get_json(media_list_urls)
        folders = media.get("media", [])
        if not folders:
            raise CameraConnectionError("GoPro media list is empty; no image captured.")

        latest_folder = folders[-1]
        folder_name = latest_folder.get("d")
        files = latest_folder.get("fs", [])
        if not folder_name or not files:
            raise CameraConnectionError("GoPro media folder is missing files.")

        latest_file = files[-1].get("n")
        if not latest_file:
            raise CameraConnectionError("GoPro latest media item has no filename.")

        encoded_folder = urllib.parse.quote(folder_name)
        encoded_file = urllib.parse.quote(latest_file)
        media_url = f"{self.media_base_url}/videos/DCIM/{encoded_folder}/{encoded_file}"

        self.download_dir.mkdir(parents=True, exist_ok=True)
        destination = self.download_dir / latest_file
        self._download_file(source_url=media_url, destination=destination)
        logger.info("Captured image downloaded to %s", destination.resolve())

        # undistorted_destination = self._undistort_image(destination)
        # resolved_destination = str(undistorted_destination.resolve())
        # logger.info("Returning undistorted image at %s", resolved_destination)

        flattened_destination = self.flatten_image_with_aruco(
            destination,
            corner_offset_percentages=(
                (0.0, 0.0),
                (1.0, 0.2),
                (0.1, 1.6),
                (1.7, 0.2),
            ),
        )
        logger.info("Returning flattened image at %s", flattened_destination)
        return flattened_destination
