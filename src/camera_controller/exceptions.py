from __future__ import annotations


class CameraControllerError(RuntimeError):
    """Base class for camera controller failures."""


class CameraConnectionError(CameraControllerError):
    """Raised when the camera cannot be reached over the network."""


class ArucoMarkersError(CameraControllerError):
    """Raised when required ArUco markers are missing or not detected."""
