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
cd src
python -m puzzle_orchestrator
```

If you want to set one variable for the current PowerShell session, use:

```powershell
$env:VARIABLE_NAME = "value"
```

Example:

```powershell
$env:PUZZLE_CAMERA_TRANSPORT = "mock"
```

If you want to set one variable for the current Bash session, use:

```bash
export VARIABLE_NAME="value"
```

Example:

```bash
export PUZZLE_CAMERA_TRANSPORT="mock"
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
| `PUZZLE_UART_ACK_TIMEOUT_SECONDS` | `1.0` | Maximum time to wait for `ACK` (`A`) after sending a command. |
| `PUZZLE_UART_DONE_TIMEOUT_SECONDS` | `30.0` | Maximum time to wait for `done` (`D`) before sending the next command. |
| `PUZZLE_UART_WAIT_FOR_START` | `false` | If set to `true`, `1`, or `yes`, the UART interface waits for the microcontroller start signal before execution begins. |
| `PUZZLE_CAMERA_TRANSPORT` | `gopro` | Camera backend. Supported values: `gopro`, `mock`. |
| `PUZZLE_MOCK_CAMERA_IMAGE` | `./data/with_aruco2_flattened.JPG` | Image path used when `PUZZLE_CAMERA_TRANSPORT=mock`. This path is relative to the current working directory unless you provide an absolute path. |

### Root folder setup

To run from the repository root, this is the one extra variable you have to set:

```powershell
$env:PYTHONPATH = "src"
```

Recommended example for local testing from the root folder:

```powershell
$env:PYTHONPATH = "src"
$env:PUZZLE_CAMERA_TRANSPORT = "mock"
$env:PUZZLE_MICROCONTROLLER_TRANSPORT = "stub"
python -m puzzle_orchestrator
```

Example for Bash
```bash
export PYTHONPATH="src"
export PUZZLE_CAMERA_TRANSPORT="mock"
python -m puzzle_orchestrator
```

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
