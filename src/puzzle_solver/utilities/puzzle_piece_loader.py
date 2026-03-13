# -*- coding: utf-8 -*-
"""
Utility class that loads the information saved as JSON files\n
about the coordinates of the corners that the puzzlepieces\n
have into more easily accessed puzzlepiece objects with\n
their added funcionalities. It is supposed to make the code\n
more understandable, well organized and easier to adapt or\n
reuse in case something changes.
"""

# load_corners_from_json.py

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, List

from ..component.point import Point
from ..component.puzzle_piece import PuzzlePiece


class PuzzlePieceLoader:
    """
    Simple utility class with one method `load_pieces()` which\n
    automatically generates the dictionary with the puzzle pieces\n
    and their respectiv corner values.
    """

    # setup
    ROOT_LOC: str = "src"
    FOLDERNAME: str = "output"
    FILENAME: str = "corners.json"

    @staticmethod
    def _setup_corner_data_path(
        pre_root_dir: str, folder_name: str, datafile_name: str
    ) -> Path:
        """
        Check if the given folder and filename lead to\n
        an existing file with the needed information about\n
        the puzzle.
        """
        result: Path = Path(__file__)

        while not Path(result).name == pre_root_dir:
            result = result.parent

        result = result.parent / folder_name / datafile_name
        result.resolve()

        if result.exists():
            return result

        raise FileNotFoundError

    # funcitionality
    @classmethod
    def load_pieces(cls) -> dict[int, PuzzlePiece]:
        """
        Returns a dictionary with all the puzzle pieces\n
        found in output and adds their value as a key to\n
        find them more easily.
        """
        JSON_PATH_TO_CORNERS: Path = cls._setup_corner_data_path(
            cls.ROOT_LOC, cls.FOLDERNAME, cls.FILENAME
        )
        return cls._load_corner_pieces(JSON_PATH_TO_CORNERS)

    @classmethod
    def _points_from_list(cls, raw_points: List[List[float]]) -> List[Point]:
        """
        Convert a list like [[x1, y1], [x2, y2], ...] into a list of Point objects.
        """
        points: List[Point] = []
        for idx, pair in enumerate(raw_points):
            if len(pair) != 2:
                raise ValueError(
                    f"Point at index {idx} does not have length 2: {pair!r}"
                )
            x, y = pair
            points.append(Point(float(x), float(y)))
        return points

    @classmethod
    def _load_corner_pieces(cls, json_path: Path) -> Dict[int, PuzzlePiece]:
        """
        Load corner puzzle pieces from a JSON file with structure:
            {
            "piece_1.png": [[x1, y1], [x2, y2], ...],
            "piece_2.png": [[x1, y1], [x2, y2], ...],
            ...
            }

        Returns a dict mapping filename -> PuzzlePiece.
        """
        with open(json_path, "r", encoding="utf-8") as f:
            data: Dict[str, List[List[float]]] = json.load(f)

        pieces: Dict[int, PuzzlePiece] = {}

        for filename, raw_points in data:
            points = cls._points_from_list(raw_points)

            # You can enforce at least 3 points if your Polygon requires it:
            if len(points) < 3:
                raise ValueError(
                    f"Piece {filename!r} has fewer than 3 points ({len(points)}); "
                    "cannot build a valid polygon"
                )

            piece_num: int = int(re.findall(r"\d+", filename)[0])

            piece = PuzzlePiece(points)
            pieces[piece_num] = piece

        return pieces
