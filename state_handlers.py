# state_handlers.py — 基于状态模式的事件分发处理器
# 每个游戏状态（playing、paused、game over、confirm quit、help）对应一个类，
# 负责处理该状态下的键盘事件，并返回下一个状态（如果需要）。

from __future__ import annotations

from typing import override, Protocol

import pygame

from engine import TetrisEngine  # 仅用于类型注解（不会引起循环导入）
from input_handler import InputHandler
from config_manager import ConfigManager


class AppInterface(Protocol):
    """TetrisApp 对外暴露的接口（供状态处理器调用）。"""
    game: TetrisEngine
    input_handler: InputHandler
    config: ConfigManager
    paused: bool
    confirm_quit: bool
    fall_event: int

    def toggle_pause(self) -> None: ...
    def handle_fall_timer(self) -> None: ...
    def toggle_help(self) -> None: ...
    def restart_game(self) -> None: ...
    def handle_quit(self) -> None: ...


class StateHandler:
    """状态处理器基类。"""

    def on_enter(self, _app: AppInterface) -> None:
        """进入该状态时调用。"""

    def on_exit(self, _app: AppInterface) -> None:
        """离开该状态时调用。"""

    def handle_event(
        self, _app: AppInterface, _event: pygame.event.Event
    ) -> StateHandler | None:
        """处理事件，返回新的状态处理器（如果状态改变），否则返回 None。"""
        raise NotImplementedError


class PlayingState(StateHandler):
    """正常游戏进行中的状态。"""

    @override
    def handle_event(
        self, app: AppInterface, event: pygame.event.Event
    ) -> StateHandler | None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            # 第一次 ESC：设置确认标志并进入确认退出状态
            app.confirm_quit = True
            return ConfirmQuitState()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            app.toggle_pause()          # 切换暂停状态，内部会修改 app.paused 和音乐
            return PausedState()
        elif event.type == app.fall_event:
            app.handle_fall_timer()     # 处理下落定时器事件
        elif event.type == pygame.KEYDOWN:
            key = event.key
            mods = pygame.key.get_mods()
            if key == pygame.K_F1:
                app.toggle_help()
                return HelpState()
            elif key == pygame.K_SLASH and (mods & pygame.KMOD_SHIFT):
                app.toggle_help()
                return HelpState()
            else:
                app.input_handler.handle_keydown(key)   # 方向键、旋转、硬降等
        return None


class PausedState(StateHandler):
    """暂停状态。"""

    @override
    def handle_event(
        self, app: AppInterface, event: pygame.event.Event
    ) -> StateHandler | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                app.toggle_pause()          # 恢复游戏
                return PlayingState()
            elif event.key == pygame.K_ESCAPE:
                # 在暂停状态下按 ESC 也表示确认退出
                app.confirm_quit = True
                return ConfirmQuitState()
        return None


class GameOverState(StateHandler):
    """游戏结束状态。"""

    @override
    def handle_event(
        self, app: AppInterface, event: pygame.event.Event
    ) -> StateHandler | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                app.restart_game()
                return PlayingState()
            elif event.key == pygame.K_ESCAPE:
                app.handle_quit()          # 直接退出，不经过确认
                return None                 # 退出整个应用，不再处理事件
        return None


class ConfirmQuitState(StateHandler):
    """确认退出对话框状态。"""

    @override
    def handle_event(
        self, app: AppInterface, event: pygame.event.Event
    ) -> StateHandler | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                # 第二次 ESC：真正退出
                app.handle_quit()
                return None
            elif event.key == pygame.K_r:
                # 按 R 重新开始
                app.confirm_quit = False
                app.restart_game()
                return PlayingState()
            else:
                # 其他键取消退出
                app.confirm_quit = False
                if app.game.game_over:
                    return GameOverState()
                elif app.paused:
                    return PausedState()
                else:
                    return PlayingState()
        return None

    @override
    def on_exit(self, app: AppInterface) -> None:
        """离开确认退出状态时确保标志关闭。"""
        app.confirm_quit = False


class HelpState(StateHandler):
    """帮助界面状态。按任意键关闭帮助。"""

    @override
    def handle_event(
        self, app: AppInterface, event: pygame.event.Event
    ) -> StateHandler | None:
        if event.type == pygame.KEYDOWN:
            app.toggle_help()              # 关闭帮助
            # 帮助只能从游戏进行中打开，所以总是返回 PlayingState
            return PlayingState()
        return None
