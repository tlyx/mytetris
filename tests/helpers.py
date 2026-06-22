"""Public-named test helpers for TetrisEngine.

This module mirrors the previous `_helpers.py` but uses a non-underscore
name as requested. Tests can import these helpers via

    from tests import helpers

and use the utilities to set up deterministic engine scenarios.
"""

from __future__ import annotations

from typing import Optional, List, Tuple

from engine import TetrisEngine


def spawn_piece_for_test(engine: TetrisEngine, piece: str) -> None:
    """Set ``next_type`` and spawn the specified piece immediately."""
    engine.next_type = piece
    engine._spawn_piece()


def set_bag(engine: TetrisEngine, items: List[str]) -> None:
    """Replace the engine's internal bag with the provided list."""
    engine._bag = list(items)


def draw_from_bag(engine: TetrisEngine) -> str:
    """Draw the next piece from the internal bag (testing wrapper)."""
    return engine._draw_from_bag()


def check_collision(engine: TetrisEngine, nx: int, ny: int, shape: Optional[List[Tuple[int, int]]] = None) -> bool:
    """Wrapper around the engine's collision check used in tests."""
    return engine._check_collision(nx, ny, shape)

