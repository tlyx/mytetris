# input_handler.py — 输入处理器
# 负责处理键盘输入事件和自动重复（DAS/ARR），并通过回调将动作传递给应用层。
# 解耦后 TetrisApp 无需直接管理按键重复逻辑。

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, final

import pygame


class Action(Enum):
    """游戏操控动作枚举。"""
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    SOFT_DROP = auto()
    HARD_DROP = auto()
    ROTATE = auto()


@final
class InputHandler:
    """管理键盘按键的首次按下和自动重复（DAS/ARR）。"""

    # 自动重复参数（与原来 TetrisApp 保持一致）
    _DAS_INITIAL: int = 200   # 首次触发前等待时间（毫秒）
    _DAS_INTERVAL: int = 50   # 触发间隔（毫秒）

    _callback: Callable[[Action], None]

    def __init__(self, callback: Callable[[Action], None]) -> None:
        """
        :param callback: 当动作被触发时调用，参数为 Action 枚举。
        """
        self._callback = callback
        self._key_pressed_time: dict[int, int] = {}
        self._key_last_action_time: dict[int, int] = {}

    # ---------- 首次按键处理 ----------
    def handle_keydown(self, key: int, now: int) -> None:
        """处理第一次按下方向键或动作键。

        :param key: pygame 按键常量
        :param now: 当前时间（毫秒），由外部传入
        """
        if key == pygame.K_UP:
            self._callback(Action.ROTATE)
        elif key == pygame.K_LEFT:
            self._callback(Action.MOVE_LEFT)
            self._key_pressed_time[pygame.K_LEFT] = now
            self._key_last_action_time[pygame.K_LEFT] = now
        elif key == pygame.K_RIGHT:
            self._callback(Action.MOVE_RIGHT)
            self._key_pressed_time[pygame.K_RIGHT] = now
            self._key_last_action_time[pygame.K_RIGHT] = now
        elif key == pygame.K_DOWN:
            self._callback(Action.SOFT_DROP)
            self._key_pressed_time[pygame.K_DOWN] = now
            self._key_last_action_time[pygame.K_DOWN] = now
        elif key == pygame.K_SPACE:
            self._callback(Action.HARD_DROP)

    # ---------- 每帧自动重复检测 ----------
    def process_auto_repeat(self, now: int) -> None:
        """每帧调用，根据持续按下的键触发自动重复动作。

        :param now: 当前时间（毫秒），由外部传入
        """
        keys = pygame.key.get_pressed()

        repeat_keys = {
            pygame.K_LEFT: Action.MOVE_LEFT,
            pygame.K_RIGHT: Action.MOVE_RIGHT,
            pygame.K_DOWN: Action.SOFT_DROP,
        }

        for key, action in repeat_keys.items():
            if keys[key]:
                if key not in self._key_pressed_time:
                    self._key_pressed_time[key] = now
                    self._key_last_action_time[key] = now
                else:
                    elapsed = now - self._key_pressed_time[key]
                    if elapsed >= self._DAS_INITIAL:
                        delta = now - self._key_last_action_time[key]
                        if delta >= self._DAS_INTERVAL:
                            self._key_last_action_time[key] = now
                            self._callback(action)
            else:
                self._key_pressed_time.pop(key, None)
                self._key_last_action_time.pop(key, None)

    # ---------- 重置（暂停、重新开始等） ----------
    def reset(self) -> None:
        """清空所有按键时间记录，停止自动重复。"""
        self._key_pressed_time.clear()
        self._key_last_action_time.clear()
