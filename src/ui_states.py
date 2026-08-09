# ui_states.py — UI 流程状态机（状态模式）
#
# 此文件主要负责：
#  - 状态机：Playing / Paused / GameOver / ConfirmQuit / Help
#  - 各状态下的按键分发与状态转换
#  - AppInterface 契约（GameApp 对外接口）见 contracts.py

from __future__ import annotations

from typing import override

import pygame

from contracts import AppInterface


class StateHandler:
    """状态处理器基类。"""

    def on_enter(self, app: AppInterface) -> None:
        """进入该状态时调用。"""

    def on_exit(self, app: AppInterface) -> None:
        """离开该状态时调用。"""

    def handle_event(
        self, app: AppInterface, event: pygame.event.Event
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
            if key == pygame.K_F1 or (key == pygame.K_SLASH and (mods & pygame.KMOD_SHIFT)):
                app.toggle_help()
                return HelpState()
            else:
                # 使用统一时间源 app.now
                app.keyboard_handler.handle_keydown(key, app.now)
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
