from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SolverPlacement:
    piece_id: int
    start: tuple[float, float]
    end: tuple[float, float]
    rotation: float


@dataclass(frozen=True)
class MachinePlacement:
    piece_id: int
    start: tuple[float, float]
    end: tuple[float, float]
    rotation: float
