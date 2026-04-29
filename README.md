# puzzle-program

Python project scaffold for puzzle orchestration.

## Structure

- `src/puzzle_orchestrator`: master `PuzzleOrchestrator` package
- `src/camera_controller`: `CameraController` package
- `src/puzzle_solver`: `PuzzleSolver` package
- `src/coordinate_mapper`: `CoordinateMapper` package
- `src/microcontroller_interface`: `MicrocontrollerInterface` package
- `src/puzzle_models`: Shared Models for other packages

## Run

```powershell
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m puzzle_orchestrator
```

## Configuration

The orchestrator is configured through `config.ini` in the repository root,
one level above the `src` folder.

| Section | Key | Default | Description |
| --- | --- | --- | --- |
| `logging` | `level` | `DEBUG` | Python logging level used by `puzzle_orchestrator`, for example `DEBUG`, `INFO`, or `WARNING`. |
| `microcontroller` | `transport` | `stub` | Microcontroller backend. Supported values: `uart`, `stub`. `stub` skips real UART communication. |
| `uart` | `port` | `/dev/serial0` | UART device path, for example `COM3` on Windows. |
| `uart` | `baudrate` | `57600` | UART baud rate. Must match microcontroller firmware configuration. |
| `uart` | `timeout_seconds` | `0.2` | Serial read timeout used for low-level byte reads. |
| `uart` | `ack_timeout_seconds` | `1.0` | Maximum time to wait for `ACK` (`A`) after sending a command. |
| `uart` | `done_timeout_seconds` | `30.0` | Maximum time to wait for `done` (`D`) before sending the next command. |
| `uart` | `wait_for_start` | `false` | If set to `true`, the UART interface waits for the microcontroller start signal before execution begins. |
| `camera` | `transport` | `mock` | Camera backend. Supported values: `gopro`, `mock`. |
| `camera` | `mock_image` | `data/with_aruco2_flattened.JPG` | Image path used when `camera.transport = mock`. Relative paths are resolved from the folder containing `config.ini`. |
| `solver` | `algorithm` | `fast` | Algorithm to use for solving the puzzle. |
| `solver` | `min_area` | `60000` | Minimum contour area passed to `PuzzleSolver`. |
| `solver` | `threshold` | `none` | `0` - `255`, `none`, or `otsu`. Set to `none` or `otsu` to use Otsu thresholding. |

For local testing without hardware, set `camera.transport = mock` and
`microcontroller.transport = stub` in `config.ini`.

## Microcontroller Protocol Notes

- Execution starts only after receiving start command `S`.
- Every sent command must receive `ACK` (`A`).
- Next command is sent only after receiving `done` (`D`).
- Any `error` (`E`) aborts execution immediately.

## RaspberryPi Config
To cmdline.txt add:
```
ip=192.168.50.2::192.168.50.1:255.255.255.0::eth0:off
```

Connect via SSH.
Enable VNC using `sudo raspi-config`

The Puzzle Programs needs OpenCV installed on the RaspberryPi. Install with
```
ip route
sudo ip route del default
sudo apt update
sudo apt upgrade
sudo apt install python3-opencv -y
sudo apt install python3-shapely
```

To allow access to /dev/serial0:
- `sudo raspi-config`
- Interface Options
- Serial Port
- Disable Login Shell
- Enable Serial Port
- `ls -l /dev/ttyS0` should print `rw` for group

## IP Adresses
RaspberryPi: 192.168.50.2
GoPro: 10.5.5.9

## Uart Interface
Baudrate von Microcontroller: 57600
Port: /dev/serial0

GPIO Pins (Default): Send 8 (GPIO14), Recieve 10 (GPIO15)
