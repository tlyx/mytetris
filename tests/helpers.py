# helpers.py — 测试辅助函数（公开命名，供各测试模块复用）
#
# 此文件主要负责：
#  - 生成指定方块 / 设置 bag / 碰撞检查等测试原语

"""Public-named test helpers for TetrisEngine.

This module mirrors the previous `_helpers.py` but uses a non-underscore
name as requested. Tests can import these helpers via

    from tests import helpers

and use the utilities to set up deterministic engine scenarios.
"""

from engine import TetrisEngine


def spawn_piece_for_test(engine: TetrisEngine, piece: str) -> None:
    """Set ``next_type`` and spawn the specified piece immediately."""
    engine.next_type = piece
    engine._spawn_piece()  # pyright: ignore[reportPrivateUsage]


def set_bag(engine: TetrisEngine, items: list[str]) -> None:
    """Replace the engine's internal bag with the provided list."""
    engine._bag = list(items)  # pyright: ignore[reportPrivateUsage]


def draw_from_bag(engine: TetrisEngine) -> str:
    """Draw the next piece from the internal bag (testing wrapper)."""
    return engine._draw_from_bag()  # pyright: ignore[reportPrivateUsage]


def check_collision(engine: TetrisEngine, nx: int, ny: int, shape: list[tuple[int, int]] | None = None) -> bool:
    """Wrapper around the engine's collision check used in tests."""
    return engine._check_collision(nx, ny, shape)  # pyright: ignore[reportPrivateUsage]


def set_last_cleared_rows(engine: TetrisEngine, rows: list[int]) -> None:
    """Set the internal last cleared rows list for testing purposes."""
    engine._last_cleared_rows = list(rows)  # pyright: ignore[reportPrivateUsage]
