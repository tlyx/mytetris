"""游戏动作词汇表：人类输入与 bot 共用，不依赖 pygame。

独立成模块，使 bot 侧（决策与调度）完全不触碰 pygame 相关代码。
"""

from __future__ import annotations

from enum import Enum, auto


class Action(Enum):
    """游戏操控动作枚举。"""
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    SOFT_DROP = auto()
    HARD_DROP = auto()
    ROTATE = auto()
