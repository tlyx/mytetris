# actions.py — 游戏动作词汇表（人类输入与 bot 共用）
#
# 此文件主要负责：
#  - 定义 Action 动作枚举（输入层与 bot 的公共词汇）

from enum import Enum, auto


class Action(Enum):
    """游戏操控动作枚举。"""
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    SOFT_DROP = auto()
    HARD_DROP = auto()
    ROTATE = auto()
