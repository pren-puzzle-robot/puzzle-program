# -*- coding: utf-8 -*-
"""Module with all the essential Components"""

__copyright__ = "Copyright (c) 2025 HSLU PREN Team 13, HS25. All rights reserved."


# simplifies access to these classes
from .puzzle_piece_loader import PuzzlePieceLoader
from .draw_puzzle_piece import print_whole_puzzle_image
from .polygon_analysis import analyze_polygon

from .solver import Solver

def load_pieces():
    """
    Returns a dictionary with all the puzzle pieces\n
    found in output and adds their value as a key to\n
    find them more easily.
    """
    return PuzzlePieceLoader.load_pieces()

__all__ = ["load_pieces", "compute_offset", "print_whole_puzzle_image", "analyze_polygon", "Solver"]
