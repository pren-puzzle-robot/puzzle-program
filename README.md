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

```bash
export PYTHONPATH="src"
python -m puzzle_orchestrator
```

## Configuration

The orchestrator is configured through `config.ini` in the repository root,
one level above the `src` folder.

| Section | Key | Default | Description |
| --- | --- | --- | --- |
| `logging` | `level` | `DEBUG` | Python logging level used by `puzzle_orchestrator`, for example `DEBUG`, `INFO`, or `WARNING`. |
| `runtime` | `loop` | `false` | If `true`, the orchestrator runs continuously and starts a new cycle after each completed or failed run. If `false`, it performs exactly one run and then exits. |
| `audio` | `enabled` | `false` | Enables audio playback. |
| `audio` | `ready`, `start`, `in_progress_loop`, `success`, `camera_error`, `solver_error`, `coordinate_mapper_error`, `microcontroller_error`, `unexpected_error` | empty | Optional audio file paths. `ready` plays once when the program starts. `start` plays once asynchronously after the microcontroller start command is received. `in_progress_loop` starts after `start` finishes and repeats until the run ends. Relative paths are resolved from the folder containing `config.ini`. |
| `audio.error_sounds` | `<stage>.<ExceptionType>`, `<stage>.default`, `<ExceptionType>`, `default` | empty | Optional fine-grained sound rules. Matching order is `stage.ExceptionType`, then `stage.default`, then `ExceptionType`, then `default`. Exception inheritance is respected, so e.g. `TimeoutError` also matches `OSError` and `Exception` fallbacks. |
| `microcontroller` | `transport` | `stub` | Microcontroller backend. Supported values: `uart`, `stub`. `stub` skips real UART communication. |
| `uart` | `port` | `/dev/serial0` | UART device path, for example `COM3` on Windows. |
| `uart` | `baudrate` | `57600` | UART baud rate. Must match microcontroller firmware configuration. |
| `uart` | `timeout_seconds` | `0.2` | Serial read timeout used for low-level byte reads. |
| `uart` | `ack_timeout_seconds` | `1.0` | Maximum time to wait for `ACK` (`A`) after sending a command. |
| `uart` | `done_timeout_seconds` | `30.0` | Maximum time to wait for `done` (`D`) before sending the next command. |
| `uart` | `wait_for_start` | `false` | If set to `true`, the UART interface waits for the microcontroller start signal before execution begins. |
| `camera` | `transport` | `mock` | Camera backend. Supported values: `gopro`, `mock`. |
| `camera` | `mock_image` | `data/with_aruco2_flattened.JPG` | Image path used when `camera.transport = mock`. Relative paths are resolved from the folder containing `config.ini`. |
| `coordinate_mapper` | `scale_x`, `scale_y` | `1.0`, `1.0` | Fixed machine-units-per-solver-unit scales used when `auto_calculate_scale = false`. |
| `coordinate_mapper` | `auto_calculate_scale` | `false` | If `true`, derive `scale_x` and `scale_y` from the captured frame size and configured base-plate dimensions instead of using `scale_x` and `scale_y` directly. |
| `coordinate_mapper` | `base_plate_width_mm`, `base_plate_height_mm` | empty | Physical size of the captured base plate in millimeters. Required when `auto_calculate_scale = true`. |
| `coordinate_mapper` | `steps_per_mm` | `80.0` | Machine conversion factor used for auto-calculated scales. |
| `coordinate_mapper.start` | `x_min`, `y_min` | `0.0`, `0.0` | Machine-space offset where solver `start` coordinate `(0, 0)` is placed.  |
| `coordinate_mapper.end` | `x_min`, `y_min` | `0.0`, `0.0` | Machine-space offset where solver `end` coordinate `(0, 0)` is placed. |
| `solver` | `algorithm` | `fast` | Algorithm to use for solving the puzzle. Supported values: `fast`, `greedy`, `brute_force`, `edge_walk`, `corner_walk`. `brute_force` combines detected outer edges into a closed rectangular boundary and scores layouts whose short-to-long side ratio is close to `1:sqrt(2)`. `edge_walk` walks a cursor around a derived A5-style frame and recursively places pieces by high-ranked straight outer edges; it keeps a small piece gap, allows small temporary placement overlap, tightens final overlap and frame overflow tolerance, and falls back to `brute_force` if no complete frame-walk placement is found. `corner_walk` builds an A5-ratio frame from the total piece area, tries detected corner-piece candidates in every frame corner, fits all pieces inside the frame, places two remaining pieces on frame-side gaps for six-piece puzzles, and returns the lowest-overlap layout it finds. |
| `solver` | `min_area` | `60000` | Minimum contour area passed to `PuzzleSolver`. |
| `solver` | `threshold` | `none` | `0` - `255`, `none`, or `otsu`. Set to `none` or `otsu` to use Otsu thresholding. |
| `solver` | `piece_margin` | `0.0` | Non-negative outward margin added to each detected piece polygon when the `PuzzlePiece` is created. The buffered outline becomes the actual shape used for edge analysis and solving. |
| `solver` | `corner_simplify_frac` | `0.001` | Fraction of the piece perimeter used as polygon simplification tolerance during corner detection. Lower values keep more points; higher values simplify more aggressively. |

For local testing without hardware, set `camera.transport = mock` and
`microcontroller.transport = stub` in `config.ini`.

Example audio configuration:

```ini
[audio]
enabled = true
ready = sounds/ready.wav
start = sounds/start.wav
in_progress_loop = sounds/in_progress_loop.wav
success = sounds/happy_wheels_victory.wav
camera_error = sounds/camera_error.wav
solver_error = sounds/solver_error.wav
coordinate_mapper_error = sounds/coordinate_mapper_error.wav
microcontroller_error = sounds/microcontroller_error.wav
unexpected_error = sounds/unexpected_error.wav
```

Example with different sounds for specific errors:

```ini
[audio.error_sounds]
camera.CameraConnectionError = sounds/gopro_connection_error.wav
camera.ArucoMarkersError = sounds/aruco_not_found.wav
microcontroller.TimeoutError = sounds/microcontroller_connection_timeout.wav
```

The coordinate mapper uses:
`machine_x = x_min + solver_x * scale_x`
and
`machine_y = y_min + solver_y * scale_y`
with separate `x_min` and `y_min` offsets for `start` and `end`.
Target rotation is normalized from solver radians into the range `0` to `<1600`,
where `1600` represents one full turn.

If `auto_calculate_scale = true`, the scales are calculated from the captured frame dimensions:
`scale_x = (base_plate_width_mm * steps_per_mm) / frame_width_px`
`scale_y = (base_plate_height_mm * steps_per_mm) / frame_height_px`

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

## Auto Start
[Source](https://chatgpt.com/g/g-p-68f68d8f44a88191a5cd2a513eda9ccf/c/6a1587f9-4214-8331-a59b-d4fc86123a80)
