from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2

from puzzle_models import MachinePlacement, SolverPlacement

logger = logging.getLogger(__name__)

FULL_TURN_UNITS = 1600.0


@dataclass(frozen=True)
class CoordinateOffset:
    x_min: float
    y_min: float


class CoordinateMapper:
    """Maps puzzle-grid coordinates to machine coordinates."""

    def __init__(
        self,
        scale_x: float,
        scale_y: float,
        start_offset: CoordinateOffset,
        end_offset: CoordinateOffset,
        auto_calculate_scale: bool = False,
        base_plate_width_mm: float | None = None,
        base_plate_height_mm: float | None = None,
        steps_per_mm: float = 80.0,
    ) -> None:
        self.scale_x = float(scale_x)
        self.scale_y = float(scale_y)
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.auto_calculate_scale = bool(auto_calculate_scale)
        self.base_plate_width_mm = (
            None if base_plate_width_mm is None else float(base_plate_width_mm)
        )
        self.base_plate_height_mm = (
            None if base_plate_height_mm is None else float(base_plate_height_mm)
        )
        self.steps_per_mm = float(steps_per_mm)

    def map_to_machine(
        self,
        placements: list[SolverPlacement],
        frame: str | None = None,
    ) -> list[MachinePlacement]:
        scale_x, scale_y = self._resolve_scales(frame)
        logger.info("Mapping %d solver placements to machine coordinates", len(placements))
        machine_points = [
            MachinePlacement(
                piece_id=placement.piece_id,
                start=self._map_point(placement.start, self.start_offset, scale_x, scale_y),
                end=self._map_point(placement.end, self.end_offset, scale_x, scale_y),
                rotation=self._map_rotation(placement.rotation),
            )
            for placement in placements
        ]
        logger.debug("Mapped machine placements: %s", machine_points)
        return machine_points

    def _resolve_scales(self, frame: str | None) -> tuple[float, float]:
        if not self.auto_calculate_scale:
            return self.scale_x, self.scale_y

        if frame is None:
            raise ValueError("frame is required when coordinate_mapper.auto_calculate_scale is enabled")
        if self.base_plate_width_mm is None or self.base_plate_height_mm is None:
            raise ValueError(
                "base_plate_width_mm and base_plate_height_mm must be configured "
                "when coordinate_mapper.auto_calculate_scale is enabled"
            )
        if self.base_plate_width_mm <= 0 or self.base_plate_height_mm <= 0:
            raise ValueError("Configured base-plate dimensions must be greater than zero")
        if self.steps_per_mm <= 0:
            raise ValueError("steps_per_mm must be greater than zero")

        image = cv2.imread(frame)
        if image is None:
            raise FileNotFoundError(f"Unable to read frame for scale calculation: {frame}")

        frame_height_px, frame_width_px = image.shape[:2]
        if frame_width_px <= 0 or frame_height_px <= 0:
            raise ValueError(f"Captured frame has invalid dimensions: {frame_width_px}x{frame_height_px}")

        scale_x = self.base_plate_width_mm * self.steps_per_mm / frame_width_px
        scale_y = self.base_plate_height_mm * self.steps_per_mm / frame_height_px
        logger.info(
            "Calculated coordinate mapper scales from frame %s: width=%dpx height=%dpx -> scale_x=%.6f scale_y=%.6f",
            frame,
            frame_width_px,
            frame_height_px,
            scale_x,
            scale_y,
        )
        return scale_x, scale_y

    def _map_point(
        self,
        point: tuple[float, float],
        offset: CoordinateOffset,
        scale_x: float,
        scale_y: float,
    ) -> tuple[float, float]:
        return (
            offset.x_min - float(point[1]) * scale_y,
            offset.y_min + float(point[0]) * scale_x,

        )

    @staticmethod
    def _map_rotation(rotation_radians: float) -> float:
        normalized_radians = float(rotation_radians) % (2.0 * math.pi)
        return normalized_radians * (FULL_TURN_UNITS / (2.0 * math.pi))
