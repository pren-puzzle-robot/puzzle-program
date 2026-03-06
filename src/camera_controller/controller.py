from __future__ import annotations

import json
from pathlib import Path
import time
import urllib.parse
import urllib.request


class CameraController:
    """Captures images from a GoPro connected via Wi-Fi."""

    def __init__(
        self,
        gopro_base_url: str = "http://10.5.5.9",
        media_base_url: str = "http://10.5.5.9:8080",
        download_dir: str = "captures",
        capture_delay_seconds: float = 1.5,
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self.gopro_base_url = gopro_base_url.rstrip("/")
        self.media_base_url = media_base_url.rstrip("/")
        self.download_dir = Path(download_dir)
        self.capture_delay_seconds = capture_delay_seconds
        self.request_timeout_seconds = request_timeout_seconds

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(url=url, method="GET")
        with urllib.request.urlopen(req, timeout=self.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def _download_file(self, source_url: str, destination: Path) -> None:
        req = urllib.request.Request(url=source_url, method="GET")
        with urllib.request.urlopen(req, timeout=self.request_timeout_seconds) as response:
            destination.write_bytes(response.read())

    def capture_frame(self) -> str:
        """
        Trigger a GoPro photo capture, download the latest image, and return local path.
        """
        shutter_url = f"{self.gopro_base_url}/gopro/camera/shutter/start"
        req = urllib.request.Request(url=shutter_url, method="GET")
        with urllib.request.urlopen(req, timeout=self.request_timeout_seconds):
            pass

        time.sleep(self.capture_delay_seconds)

        media_list_url = f"{self.gopro_base_url}/gopro/media/list"
        media = self._get_json(media_list_url)
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
        return str(destination.resolve())
