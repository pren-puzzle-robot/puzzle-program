# puzzle-program

Python project scaffold for puzzle orchestration.

## Structure

- `src/puzzle_orchestrator`: master `PuzzleOrchestrator` package
- `src/camera_controller`: `CameraController` package
- `src/puzzle_solver`: `PuzzleSolver` package
- `src/coordinate_mapper`: `CoordinateMapper` package
- `src/microcontroller_interface`: `MicrocontrollerInterface` package

## Run

```bash
python -m puzzle_orchestrator
```

## Uart Interface
Baudrate von Microcontroller: 57600
Port: /dev/serial0

GPIO Pins: Send 8 (GPIO14), Recieve 10 (GPIO15)