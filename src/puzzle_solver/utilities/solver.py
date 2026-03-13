"""Code-File providing the matching of puzzle edges."""

from __future__ import annotations
from abc import ABC, abstractmethod

from ..component import PuzzlePiece

class Solver(ABC):
    
    @classmethod
    @abstractmethod
    def solve(cls, puzzle: dict[int, PuzzlePiece]) -> list[int]:
        pass
