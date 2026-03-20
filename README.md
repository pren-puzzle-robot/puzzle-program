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

## Configuration

The orchestrator is configured through environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `PUZZLE_LOG_LEVEL` | `DEBUG` | Python logging level used by `puzzle_orchestrator` (for example `DEBUG`, `INFO`, `WARNING`). |
| `PUZZLE_MICROCONTROLLER_TRANSPORT` | `uart` | Microcontroller backend. Supported values: `uart`, `stub`. `stub` skips real UART communication. |
| `PUZZLE_UART_PORT` | `/dev/serial0` | UART device path (for example `COM3` on Windows). |
| `PUZZLE_UART_BAUDRATE` | `57600` | UART baud rate. Must match microcontroller firmware configuration. |
| `PUZZLE_UART_TIMEOUT_SECONDS` | `0.2` | Serial read timeout used for low-level byte reads. |
| `PUZZLE_UART_ACK_TIMEOUT_SECONDS` | `2.0` | Maximum time to wait for `ACK` (`A`) after sending a command. |
| `PUZZLE_UART_DONE_TIMEOUT_SECONDS` | `30.0` | Maximum time to wait for `done` (`D`) before sending the next command. |

## Microcontroller Protocol Notes

- Execution starts only after receiving start command `S`.
- Every sent command must receive `ACK` (`A`).
- Next command is sent only after receiving `done` (`D`).
- Any `error` (`E`) aborts execution immediately.

## Uart Interface
Baudrate von Microcontroller: 57600
Port: /dev/serial0

GPIO Pins: Send 8 (GPIO14), Recieve 10 (GPIO15)
