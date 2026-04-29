from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.ini"


@dataclass(frozen=True)
class LoggingConfig:
    level: str


@dataclass(frozen=True)
class MicrocontrollerConfig:
    transport: str


@dataclass(frozen=True)
class UartConfig:
    port: str
    baudrate: int
    timeout_seconds: float
    ack_timeout_seconds: float
    done_timeout_seconds: float
    wait_for_start: bool


@dataclass(frozen=True)
class CameraConfig:
    transport: str
    mock_image: Path


@dataclass(frozen=True)
class CoordinateOffsetConfig:
    x_min: float
    y_min: float


@dataclass(frozen=True)
class CoordinateMapperConfig:
    scale_x: float
    scale_y: float
    start: CoordinateOffsetConfig
    end: CoordinateOffsetConfig


@dataclass(frozen=True)
class SolverConfig:
    algorithm: str
    min_area: int
    threshold_value: str | None


@dataclass(frozen=True)
class AppConfig:
    logging: LoggingConfig
    microcontroller: MicrocontrollerConfig
    uart: UartConfig
    camera: CameraConfig
    coordinate_mapper: CoordinateMapperConfig
    solver: SolverConfig


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    config_path = config_path.resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    parser = ConfigParser()
    parser.read_dict(
        {
            "logging": {"level": "DEBUG"},
            "microcontroller": {"transport": "uart"},
            "uart": {
                "port": "/dev/serial0",
                "baudrate": "57600",
                "timeout_seconds": "0.2",
                "ack_timeout_seconds": "1.0",
                "done_timeout_seconds": "30.0",
                "wait_for_start": "false",
            },
            "camera": {
                "transport": "gopro",
                "mock_image": "data/with_aruco2_flattened.JPG",
            },
            "coordinate_mapper": {
                "scale_x": "1.0",
                "scale_y": "1.0",
            },
            "coordinate_mapper.start": {
                "x_min": "0.0",
                "y_min": "0.0",
            },
            "coordinate_mapper.end": {
                "x_min": "0.0",
                "y_min": "0.0",
            },
            "solver": {
                "algorithm": "fast",
                "min_area": "60000",
                "threshold": "none",
            },
        }
    )
    parser.read(config_path, encoding="utf-8")

    return AppConfig(
        logging=LoggingConfig(
            level=parser.get("logging", "level").strip(),
        ),
        microcontroller=MicrocontrollerConfig(
            transport=parser.get("microcontroller", "transport").strip().lower(),
        ),
        uart=UartConfig(
            port=parser.get("uart", "port").strip(),
            baudrate=parser.getint("uart", "baudrate"),
            timeout_seconds=parser.getfloat("uart", "timeout_seconds"),
            ack_timeout_seconds=parser.getfloat("uart", "ack_timeout_seconds"),
            done_timeout_seconds=parser.getfloat("uart", "done_timeout_seconds"),
            wait_for_start=parser.getboolean("uart", "wait_for_start"),
        ),
        camera=CameraConfig(
            transport=parser.get("camera", "transport").strip().lower(),
            mock_image=_resolve_config_path(
                parser.get("camera", "mock_image").strip(),
                config_path.parent,
            ),
        ),
        coordinate_mapper=CoordinateMapperConfig(
            scale_x=parser.getfloat("coordinate_mapper", "scale_x"),
            scale_y=parser.getfloat("coordinate_mapper", "scale_y"),
            start=_read_coordinate_offset(parser, "coordinate_mapper.start"),
            end=_read_coordinate_offset(parser, "coordinate_mapper.end"),
        ),
        solver=SolverConfig(
            algorithm=parser.get("solver", "algorithm").strip().lower(),
            min_area=parser.getint("solver", "min_area"),
            threshold_value=_optional_value(parser.get("solver", "threshold")),
        ),
    )


def _resolve_config_path(value: str, config_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config_dir / path


def _optional_value(value: str) -> str | None:
    value = value.strip()
    if not value or value.lower() in {"none", "null"}:
        return None
    return value


def _read_coordinate_offset(
    parser: ConfigParser,
    section: str,
) -> CoordinateOffsetConfig:
    x_min = parser.getfloat(section, "x_min")
    y_min = parser.getfloat(section, "y_min")
    return CoordinateOffsetConfig(
        x_min=x_min,
        y_min=y_min,
    )
