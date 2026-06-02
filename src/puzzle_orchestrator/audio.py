from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

from .config import AudioConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorSoundMap:
    start: Path | None
    in_progress_loop: Path | None
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
            start=config.start,
            in_progress_loop=config.in_progress_loop,
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
        self._background_stop = threading.Event()
        self._background_thread: threading.Thread | None = None
        self._background_process: subprocess.Popen[bytes] | None = None
        self._background_lock = threading.Lock()

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
        self.stop_in_progress_loop()
        self._play(self._error_sounds.success, "success", None)

    def play_error(self, stage: str, error: BaseException) -> None:
        self.stop_in_progress_loop()
        sound_path = self._resolve_sound_path(stage, error)
        self._play(sound_path, stage, error)

    def start_run_audio(self) -> None:
        if not self._enabled:
            return
        if self._error_sounds.start is None and self._error_sounds.in_progress_loop is None:
            return

        self.stop_in_progress_loop()

        with self._background_lock:
            self._background_stop = threading.Event()
            self._background_thread = threading.Thread(
                target=self._run_background_audio,
                name="run-audio",
                daemon=True,
            )
            self._background_thread.start()

    def stop_in_progress_loop(self) -> None:
        with self._background_lock:
            stop_event = self._background_stop
            thread = self._background_thread
            self._background_thread = None

        stop_event.set()
        self._stop_platform_loop()
        self._stop_background_process()

        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)

    def _run_background_audio(self) -> None:
        stop_event = self._background_stop

        if self._error_sounds.start is not None:
            self._play_background_start(self._error_sounds.start, stop_event)

        loop_sound_path = self._error_sounds.in_progress_loop
        if stop_event.is_set() or loop_sound_path is None:
            return
        if not loop_sound_path.exists():
            logger.warning(
                "Configured sound for %s does not exist: %s",
                "in_progress_loop",
                loop_sound_path,
            )
            return

        if self._start_platform_loop(loop_sound_path):
            stop_event.wait()
            return

        while not stop_event.is_set():
            self._play_background_loop(loop_sound_path, stop_event)

    def _play_background_start(self, sound_path: Path, stop_event: threading.Event) -> None:
        if not self._enabled:
            return
        if not sound_path.exists():
            logger.warning("Configured sound for %s does not exist: %s", "start", sound_path)
            return

        if sys.platform == "win32":
            try:
                self._play_windows_path_async(sound_path)
                if stop_event.wait(timeout=self._playback_timeout_seconds(sound_path)):
                    self._stop_platform_loop()
            except Exception:
                logger.exception("Failed to play sound for %s: %s", "start", sound_path)
            return

        try:
            self._play_background_process(sound_path, stop_event)
        except Exception:
            logger.exception("Failed to play sound for %s: %s", "start", sound_path)

    def _play_background_loop(self, sound_path: Path, stop_event: threading.Event) -> None:
        if sys.platform == "win32":
            self._play(sound_path, "in_progress_loop", None)
            return

        try:
            self._play_background_process(sound_path, stop_event)
        except Exception:
            logger.exception("Failed to play sound for %s: %s", "in_progress_loop", sound_path)
            stop_event.set()

    def _play_background_process(self, sound_path: Path, stop_event: threading.Event) -> None:
        process = self._start_background_process(sound_path)
        if process is None:
            self._play(sound_path, "background", None)
            return

        with self._background_lock:
            if stop_event.is_set():
                process.terminate()
                return
            self._background_process = process

        try:
            while process.poll() is None:
                if stop_event.wait(timeout=0.1):
                    self._terminate_process(process)
                    break
        finally:
            with self._background_lock:
                if self._background_process is process:
                    self._background_process = None

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
            SoundPlayer._play_windows_path_sync(sound_path)
            return

        errors: list[str] = []
        timeout_seconds = SoundPlayer._playback_timeout_seconds(sound_path)

        for executable, args in SoundPlayer._iter_playback_commands():
            if executable is None:
                continue

            try:
                completed = subprocess.run(
                    [executable, *args, str(sound_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                errors.append(
                    f"{Path(executable).name} timed out after {timeout_seconds:.1f} seconds"
                )
                continue

            if completed.returncode == 0:
                return

            output = (completed.stderr or completed.stdout).strip()
            if output:
                errors.append(f"{Path(executable).name} exited with {completed.returncode}: {output}")
            else:
                errors.append(f"{Path(executable).name} exited with {completed.returncode}")

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

    @staticmethod
    def _iter_playback_commands() -> list[tuple[str | None, tuple[str, ...]]]:
        return [
            (shutil.which("aplay"), ("-q", "-D", "plughw:2,0")),
            (shutil.which("aplay"), ("-q",)),
            (shutil.which("pw-play"), ()),
            (shutil.which("paplay"), ()),
            (shutil.which("ffplay"), ("-nodisp", "-autoexit", "-loglevel", "error")),
        ]

    @staticmethod
    def _start_background_process(sound_path: Path) -> subprocess.Popen[bytes] | None:
        sound_path = sound_path.resolve()
        if not sound_path.exists():
            raise FileNotFoundError(sound_path)

        if sys.platform == "win32":
            return None

        errors: list[str] = []
        for executable, args in SoundPlayer._iter_playback_commands():
            if executable is None:
                continue

            try:
                return subprocess.Popen(
                    [executable, *args, str(sound_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                errors.append(f"{Path(executable).name} failed to start: {exc}")

        if errors:
            raise RuntimeError("Audio playback failed: " + "; ".join(errors))

        raise RuntimeError("No supported audio playback command found")

    def _stop_background_process(self) -> None:
        with self._background_lock:
            process = self._background_process
            self._background_process = None

        if process is not None:
            self._terminate_process(process)

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return

        process.terminate()
        try:
            process.wait(timeout=0.3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=0.3)

    @staticmethod
    def _start_platform_loop(sound_path: Path) -> bool:
        sound_path = sound_path.resolve()
        if not sound_path.exists():
            raise FileNotFoundError(sound_path)

        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(
                str(sound_path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP,
            )
            return True

        return False

    @staticmethod
    def _play_windows_path_sync(sound_path: Path) -> None:
        import winsound

        winsound.PlaySound(
            str(sound_path),
            winsound.SND_FILENAME,
        )

    @staticmethod
    def _play_windows_path_async(sound_path: Path) -> None:
        import winsound

        winsound.PlaySound(
            str(sound_path),
            winsound.SND_FILENAME | winsound.SND_ASYNC,
        )

    @staticmethod
    def _stop_platform_loop() -> None:
        if sys.platform != "win32":
            return

        import winsound

        winsound.PlaySound(None, 0)
