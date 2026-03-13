from __future__ import annotations

import json
import logging
from pathlib import Path
import time
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class CameraController:
    """Captures images from a GoPro Hero 7 Black connected via Wi-Fi."""

    def __init__(
        self,
        gopro_base_url: str = "http://10.5.5.9",
        media_base_url: str = "http://10.5.5.9:8080",
        download_dir: str = "captures",
        capture_delay_seconds: float = 5.5,
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self.gopro_base_url = gopro_base_url.rstrip("/")
        self.media_base_url = media_base_url.rstrip("/")
        self.download_dir = Path(download_dir)
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
        resolved_destination = str(destination.resolve())
        logger.info("Captured image downloaded to %s", resolved_destination)
        return resolved_destination
