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
class AudioConfig:
    enabled: bool
    start: Path | None
    in_progress_loop: Path | None
    success: Path | None
    camera_error: Path | None
    solver_error: Path | None
    coordinate_mapper_error: Path | None
    microcontroller_error: Path | None
    unexpected_error: Path | None
    error_sound_rules: dict[str, Path]


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
    auto_calculate_scale: bool
    base_plate_width_mm: float | None
    base_plate_height_mm: float | None
    steps_per_mm: float
    start: CoordinateOffsetConfig
    end: CoordinateOffsetConfig


@dataclass(frozen=True)
class SolverConfig:
    algorithm: str
    min_area: int
    threshold_value: str | None
    piece_margin: float
    corner_simplify_frac: float


@dataclass(frozen=True)
class AppConfig:
    logging: LoggingConfig
    audio: AudioConfig
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
            "audio": {
                "enabled": "false",
                "start": "",
                "in_progress_loop": "",
                "success": "",
                "camera_error": "",
                "solver_error": "",
                "coordinate_mapper_error": "",
                "microcontroller_error": "",
                "unexpected_error": "",
            },
            "audio.error_sounds": {},
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
                "auto_calculate_scale": "false",
                "base_plate_width_mm": "",
                "base_plate_height_mm": "",
                "steps_per_mm": "80.0",
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
                "piece_margin": "0.0",
                "corner_simplify_frac": "0.001",
            },
        }
    )
    parser.read(config_path, encoding="utf-8")

    return AppConfig(
        logging=LoggingConfig(
            level=parser.get("logging", "level").strip(),
        ),
        audio=AudioConfig(
            enabled=parser.getboolean("audio", "enabled"),
            start=_optional_path(
                parser.get("audio", "start"),
                config_path.parent,
            ),
            in_progress_loop=_optional_path(
                parser.get("audio", "in_progress_loop"),
                config_path.parent,
            ),
            success=_optional_path(
                parser.get("audio", "success"),
                config_path.parent,
            ),
            camera_error=_optional_path(
                parser.get("audio", "camera_error"),
                config_path.parent,
            ),
            solver_error=_optional_path(
                parser.get("audio", "solver_error"),
                config_path.parent,
            ),
            coordinate_mapper_error=_optional_path(
                parser.get("audio", "coordinate_mapper_error"),
                config_path.parent,
            ),
            microcontroller_error=_optional_path(
                parser.get("audio", "microcontroller_error"),
                config_path.parent,
            ),
            unexpected_error=_optional_path(
                parser.get("audio", "unexpected_error"),
                config_path.parent,
            ),
            error_sound_rules=_read_audio_error_sound_rules(
                parser,
                "audio.error_sounds",
                config_path.parent,
            ),
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
            auto_calculate_scale=parser.getboolean("coordinate_mapper", "auto_calculate_scale"),
            base_plate_width_mm=_optional_float(
                parser.get("coordinate_mapper", "base_plate_width_mm")
            ),
            base_plate_height_mm=_optional_float(
                parser.get("coordinate_mapper", "base_plate_height_mm")
            ),
            steps_per_mm=parser.getfloat("coordinate_mapper", "steps_per_mm"),
            start=_read_coordinate_offset(parser, "coordinate_mapper.start"),
            end=_read_coordinate_offset(parser, "coordinate_mapper.end"),
        ),
        solver=SolverConfig(
            algorithm=parser.get("solver", "algorithm").strip().lower(),
            min_area=parser.getint("solver", "min_area"),
            threshold_value=_optional_value(parser.get("solver", "threshold")),
            piece_margin=_non_negative_float(
                parser.get("solver", "piece_margin"),
                "solver.piece_margin",
            ),
            corner_simplify_frac=_non_negative_float(
                parser.get("solver", "corner_simplify_frac"),
                "solver.corner_simplify_frac",
            ),
        ),
    )


def _resolve_config_path(value: str, config_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config_dir / path


def _optional_path(value: str, config_dir: Path) -> Path | None:
    parsed = _optional_value(value)
    if parsed is None:
        return None
    return _resolve_config_path(parsed, config_dir)


def _optional_value(value: str) -> str | None:
    value = value.strip()
    if not value or value.lower() in {"none", "null"}:
        return None
    return value


def _optional_float(value: str) -> float | None:
    parsed = _optional_value(value)
    if parsed is None:
        return None
    return float(parsed)


def _non_negative_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc

    if parsed < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


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


def _read_audio_error_sound_rules(
    parser: ConfigParser,
    section: str,
    config_dir: Path,
) -> dict[str, Path]:
    if not parser.has_section(section):
        return {}

    rules: dict[str, Path] = {}
    for key, value in parser.items(section):
        resolved = _optional_path(value, config_dir)
        if resolved is None:
            continue
        rules[key.strip().lower()] = resolved
    return rules
