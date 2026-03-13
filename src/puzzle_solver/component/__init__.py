# -*- coding: utf-8 -*-
"""Module with all the essential Components"""

__copyright__ = "Copyright (c) 2025 HSLU PREN Team 13, HS25. All rights reserved."

# simplifies access to these classes
from .puzzle_piece import PuzzlePiece
from .polygon import Polygon
from .point import Point
from .edge import Edge
from .outer_edge import OuterEdge


__all__ = [
    "Edge",
    "EdgeDir",
    "Corner",
    "print_whole_puzzle_image",
    "PuzzlePiece",
    "PuzzlePieceOld",
    "Solution",
    "Polygon",
    "Point",
]
