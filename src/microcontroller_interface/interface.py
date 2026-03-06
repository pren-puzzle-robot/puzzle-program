from __future__ import annotations


class MicrocontrollerInterface:
    """Sends mapped coordinates to a microcontroller."""

    def send_path(self, machine_points: list[tuple[float, float]]) -> str:
        """
        Send the planned path to the microcontroller.
        Replace this stub with serial/CAN/UART communication logic.
        """
        return f"sent_{len(machine_points)}_points"
