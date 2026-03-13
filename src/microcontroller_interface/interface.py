from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MicrocontrollerInterface:
    """Sends mapped coordinates to a microcontroller."""

    def send_path(self, machine_points: list[tuple[float, float]]) -> str:
        """
        Send the planned path to the microcontroller.
        Replace this stub with serial/CAN/UART communication logic.
        """
        logger.info("Sending %d machine points to microcontroller", len(machine_points))
        logger.debug("Machine path payload: %s", machine_points)
        result = f"sent_{len(machine_points)}_points"
        logger.info("Microcontroller send completed with result=%s", result)
        return result
