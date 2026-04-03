from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MockCameraController:
    """Returns a fixed local image instead of triggering a physical camera."""

    def __init__(self, image_path: str | Path = Path("data") / "with_aruco2_flattened.JPG") -> None:
        self.image_path = Path(image_path)

    def capture_frame(self) -> str:
        resolved_path = self.image_path.resolve()
        if not resolved_path.exists():
            raise FileNotFoundError(f"Mock camera image not found: {resolved_path}")

        logger.info("Returning mock camera image at %s", resolved_path)
        return str(resolved_path)
