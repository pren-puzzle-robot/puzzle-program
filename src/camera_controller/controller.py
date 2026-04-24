from __future__ import annotations

import json
import logging
from pathlib import Path
import time
import urllib.parse
import urllib.request

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraController:
    """Captures images from a GoPro Hero 7 Black connected via Wi-Fi."""

    def __init__(
        self,
        gopro_base_url: str = "http://10.5.5.9",
        media_base_url: str = "http://10.5.5.9:8080",
        download_dir: str = "captures",
        calibration_file: str | None = None,
        capture_delay_seconds: float = 7.5,
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

        raise RuntimeError(f"All media list endpoints failed: {urls}") from last_error

    def _try_send_get(self, urls: list[str]) -> None:
        last_error: Exception | None = None
        for url in urls:
            try:
                self._send_get(url)
                return
            except Exception as exc:
                last_error = exc
                logger.debug("Request to %s failed: %s", url, exc)

        raise RuntimeError(f"All shutter endpoints failed: {urls}") from last_error

    def _download_file(self, source_url: str, destination: Path) -> None:
        logger.debug("Downloading %s to %s", source_url, destination)
        req = urllib.request.Request(url=source_url, method="GET")
        with urllib.request.urlopen(req, timeout=self.request_timeout_seconds) as response:
            destination.write_bytes(response.read())

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
    ) -> tuple[object, list[np.ndarray], np.ndarray | None]:
        if not hasattr(cv2, "aruco"):
            raise RuntimeError("OpenCV ArUco module is not available")

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
            corners, ids, _ = detector.detectMarkers(image)
        else:
            corners, ids, _ = aruco.detectMarkers(
                image,
                dictionary,
                parameters=detector_parameters,
            )

        return aruco, corners, ids

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
    ) -> str:
        logger.info("Flattening image %s using ArUco markers %s", source, marker_ids)
        source_path = Path(source)
        image = cv2.imread(str(source_path))
        if image is None:
            raise RuntimeError(f"Unable to read image for flattening: {source_path}")

        _, corners, ids = self._detect_aruco_markers(image, dictionary_name)

        if ids is None:
            raise RuntimeError("No ArUco markers detected in image")

        detected_marker_corners: dict[int, np.ndarray] = {}
        for marker_corner, marker_id in zip(corners, ids.flatten(), strict=False):
            detected_marker_corners[int(marker_id)] = marker_corner[0]

        missing_marker_ids = [
            marker_id for marker_id in marker_ids if marker_id not in detected_marker_corners
        ]
        if missing_marker_ids:
            raise RuntimeError(f"Missing required ArUco markers: {missing_marker_ids}")

        # OpenCV returns ArUco corners in marker order:
        # top-left, top-right, bottom-right, bottom-left.
        # The markers are passed in rectangle order, so pick the outer corner of
        # each marker instead of the marker center.
        outer_corner_indices = (3, 0, 2, 2)
        source_points = np.array(
            [
                detected_marker_corners[marker_id][corner_index]
                for marker_id, corner_index in zip(marker_ids, outer_corner_indices, strict=True)
            ],
            dtype=np.float32,
        )

        if output_size is None:
            width_top = np.linalg.norm(source_points[1] - source_points[0])
            width_bottom = np.linalg.norm(source_points[2] - source_points[3])
            height_right = np.linalg.norm(source_points[2] - source_points[1])
            height_left = np.linalg.norm(source_points[3] - source_points[0])
            width = max(1, int(round(max(width_top, width_bottom))))
            height = max(1, int(round(max(height_left, height_right))))
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
            source_points,
            destination_points,
        )
        flattened = cv2.warpPerspective(image, perspective_transform, (width, height))

        destination = source_path.with_stem(f"{source_path.stem}_flattened")
        if not cv2.imwrite(str(destination), flattened):
            raise RuntimeError(f"Unable to write flattened image: {destination}")

        resolved_destination = str(destination.resolve())
        logger.info("Flattened image written to %s", resolved_destination)
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
            raise RuntimeError("GoPro media list is empty; no image captured.")

        latest_folder = folders[-1]
        folder_name = latest_folder.get("d")
        files = latest_folder.get("fs", [])
        if not folder_name or not files:
            raise RuntimeError("GoPro media folder is missing files.")

        latest_file = files[-1].get("n")
        if not latest_file:
            raise RuntimeError("GoPro latest media item has no filename.")

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

        flattened_destination = self.flatten_image_with_aruco(destination)
        logger.info("Returning flattened image at %s", flattened_destination)
        return flattened_destination
