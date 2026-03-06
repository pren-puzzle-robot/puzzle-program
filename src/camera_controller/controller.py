from __future__ import annotations


class CameraController:
    """Handles image capture from a camera source."""

    def __init__(self, camera_id: int = 0) -> None:
        self.camera_id = camera_id

    def capture_frame(self) -> str:
        """
        Capture one frame and return a placeholder frame reference.
        Replace this with actual camera integration logic.
        """
        return f"frame_from_camera_{self.camera_id}"
