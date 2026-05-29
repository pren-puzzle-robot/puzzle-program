from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

from .config import AudioConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorSoundMap:
    success: Path | None
    camera: Path | None
    solver: Path | None
    coordinate_mapper: Path | None
    microcontroller: Path | None
    unexpected: Path | None
    rules: dict[str, Path]

    @classmethod
    def from_config(cls, config: AudioConfig) -> "ErrorSoundMap":
        return cls(
            success=config.success,
            camera=config.camera_error,
            solver=config.solver_error,
            coordinate_mapper=config.coordinate_mapper_error,
            microcontroller=config.microcontroller_error,
            unexpected=config.unexpected_error,
            rules=config.error_sound_rules,
        )


class SoundPlayer:
    def __init__(self, enabled: bool, error_sounds: ErrorSoundMap) -> None:
        self._enabled = enabled
        self._error_sounds = error_sounds

    @classmethod
    def from_config(cls, config: AudioConfig) -> "SoundPlayer":
        return cls(
            enabled=config.enabled,
            error_sounds=ErrorSoundMap.from_config(config),
        )

    def play_camera_error(self, error: BaseException) -> None:
        self.play_error("camera", error)

    def play_solver_error(self, error: BaseException) -> None:
        self.play_error("solver", error)

    def play_coordinate_mapper_error(self, error: BaseException) -> None:
        self.play_error("coordinate_mapper", error)

    def play_microcontroller_error(self, error: BaseException) -> None:
        self.play_error("microcontroller", error)

    def play_unexpected_error(self, error: BaseException) -> None:
        self.play_error("unexpected", error)

    def play_success(self) -> None:
        self._play(self._error_sounds.success, "success", None)

    def play_error(self, stage: str, error: BaseException) -> None:
        sound_path = self._resolve_sound_path(stage, error)
        self._play(sound_path, stage, error)

    def _resolve_sound_path(self, stage: str, error: BaseException) -> Path | None:
        stage_key = stage.strip().lower()
        for exception_name in self._exception_names(error):
            sound_path = self._error_sounds.rules.get(f"{stage_key}.{exception_name}")
            if sound_path is not None:
                return sound_path

        stage_defaults = {
            "camera": self._error_sounds.camera,
            "solver": self._error_sounds.solver,
            "coordinate_mapper": self._error_sounds.coordinate_mapper,
            "microcontroller": self._error_sounds.microcontroller,
            "unexpected": self._error_sounds.unexpected,
        }
        stage_default = self._error_sounds.rules.get(f"{stage_key}.default")
        if stage_default is not None:
            return stage_default
        if stage_defaults.get(stage_key) is not None:
            return stage_defaults[stage_key]

        for exception_name in self._exception_names(error):
            sound_path = self._error_sounds.rules.get(exception_name)
            if sound_path is not None:
                return sound_path

        return self._error_sounds.rules.get("default")

    @staticmethod
    def _exception_names(error: BaseException) -> list[str]:
        return [cls.__name__.lower() for cls in type(error).__mro__ if cls is not object]

    def _play(self, sound_path: Path | None, stage: str, error: BaseException | None) -> None:
        if not self._enabled:
            return
        if sound_path is None:
            if error is None:
                logger.debug("No sound configured for %s", stage)
            else:
                logger.debug(
                    "No sound configured for %s error %s",
                    stage,
                    type(error).__name__,
                )
            return
        if not sound_path.exists():
            if error is None:
                logger.warning("Configured sound for %s does not exist: %s", stage, sound_path)
            else:
                logger.warning(
                    "Configured sound for %s error %s does not exist: %s",
                    stage,
                    type(error).__name__,
                    sound_path,
                )
            return

        try:
            self._play_path(sound_path)
        except Exception:
            if error is None:
                logger.exception("Failed to play sound for %s: %s", stage, sound_path)
            else:
                logger.exception(
                    "Failed to play sound for %s error %s: %s",
                    stage,
                    type(error).__name__,
                    sound_path,
                )

    @staticmethod
    def _play_path(sound_path: Path) -> None:
        sound_path = sound_path.resolve()

        if not sound_path.exists():
            raise FileNotFoundError(sound_path)

        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(
                str(sound_path),
                winsound.SND_FILENAME,
            )
            return

        errors: list[str] = []
        timeout_seconds = SoundPlayer._playback_timeout_seconds(sound_path)

        for command in (
            ("aplay", "-q", "-D", "plughw:2,0"),
            ("aplay", "-q"),
            ("pw-play",),
            ("paplay",),
            ("ffplay", "-nodisp", "-autoexit", "-loglevel", "error"),
        ):
            executable = shutil.which(command[0])
            if executable is None:
                continue

            try:
                completed = subprocess.run(
                    [executable, *command[1:], str(sound_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                errors.append(
                    f"{command[0]} timed out after {timeout_seconds:.1f} seconds"
                )
                continue

            if completed.returncode == 0:
                return

            output = (completed.stderr or completed.stdout).strip()
            if output:
                errors.append(f"{command[0]} exited with {completed.returncode}: {output}")
            else:
                errors.append(f"{command[0]} exited with {completed.returncode}")

        if errors:
            raise RuntimeError("Audio playback failed: " + "; ".join(errors))

        raise RuntimeError("No supported audio playback command found")

    @staticmethod
    def _playback_timeout_seconds(sound_path: Path) -> float:
        try:
            with wave.open(str(sound_path), "rb") as sound_file:
                frame_rate = sound_file.getframerate()
                frame_count = sound_file.getnframes()
                if frame_rate > 0:
                    return max(5.0, min(30.0, (frame_count / frame_rate) + 2.0))
        except (EOFError, OSError, wave.Error):
            pass

        return 10.0
