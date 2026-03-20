from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MicrocontrollerInterface:
    """Sends mapped coordinates to a microcontroller."""

    def wait_for_start_command(self) -> None:
        """
        Wait for an external start trigger from the microcontroller.
        Stub implementation starts immediately.
        """
        logger.info("No start command transport configured; starting immediately")

    def send_path(self, machine_points: list[dict[str, object]]) -> str:
        """
        Send the planned path to the microcontroller.
        Replace this stub with serial/CAN/UART communication logic.
        """
        logger.info("Sending %d machine placements to microcontroller", len(machine_points))
        logger.debug("Machine path payload: %s", machine_points)
        result = f"sent_{len(machine_points)}_points"
        logger.info("Microcontroller send completed with result=%s", result)
        return result
