# pyright: reportPrivateUsage=false
# test_app.py — App 层行为测试
# 覆盖公平性（bot 与人类共用重力/锁定延迟/计分）与指南标准计分。
#
# 此文件主要负责：
#  - App 层公平性与计分行为回归测试

"""App 层回归测试。

重点覆盖公平性：bot 模式与人类模式共用同一套重力/锁定延迟/计分机制
（bot 只是另一个输入源），以及软降/硬降计分等指南标准行为。
"""

import os

# pygame 无头环境：必须在构造 TetrisApp（初始化显示/音频）之前设置
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from actions import Action
from tetris import _LOCK_DELAY_MS, TetrisApp


def _app_with_piece_at_bottom() -> TetrisApp:
    """构造 App 并把当前块硬降到贴底（再下移必失败）。"""
    app = TetrisApp()
    app.game.reset()
    while app.game.move(0, -1):
        pass
    return app


def test_fall_timer_applies_when_bot_enabled() -> None:
    """bot 模式下重力/锁定延迟照常生效（公平性：bot 只是另一个输入源）。

    复现路径：贴底方块 + bot 开启 + 触发 handle_fall_timer。
    修复前 bot 模式吞掉定时器事件（防重力后门）；现在与 bot 关闭时
    行为完全一致：首 tick 进入贴地窗口，窗口满后锁定。
    """
    app = _app_with_piece_at_bottom()
    app.bot_enabled = True
    piece_before = app.game.current_type
    app._now = 0
    app.handle_fall_timer()  # 首 tick：进入贴地窗口，不锁定
    assert app.game.current_type == piece_before
    app._now = _LOCK_DELAY_MS + 100
    app.handle_fall_timer()  # 窗口已满 → 锁定
    assert app.game.current_type != piece_before  # 与 bot 关闭时一致
    assert not app.game.game_over


def test_cycle_bot_strategy() -> None:
    """循环切换 bot 策略：顺序遍历注册表。"""
    app = TetrisApp()
    assert app.bot.strategy == "modern"
    app.cycle_bot_strategy()
    assert app.bot.strategy == "legacy"
    app.cycle_bot_strategy()
    assert app.bot.strategy == "modern"


def test_drop_actions_score_points() -> None:
    """软降每格 +1、硬降每格 +2（指南标准计分）。"""
    app = TetrisApp()
    app.game.reset()

    score_before = app.game.score
    app._on_input_action(Action.SOFT_DROP)
    assert app.game.score == score_before + 1  # 软降一格

    # 硬降：I 块空盘从生成位落到底（距离 = 生成 y），每格 +2
    app.game.reset()
    app.game.next_type = "I"
    app.game._spawn_piece()  # pyright: ignore[reportPrivateUsage]
    d_before = app.game.y    # I 的 max_py=0，生成在顶行 y=19
    app._on_input_action(Action.HARD_DROP)
    assert app.game.score == 2 * d_before  # I 落到底，距离恰为 d_before


def test_fall_timer_locks_when_bot_disabled() -> None:
    """bot 关闭时定时器按锁定延迟锁定贴底方块（门控不影响正常路径）。"""
    app = _app_with_piece_at_bottom()
    piece_before = app.game.current_type
    lines_before = app.game.total_lines
    app._now = 0
    app.handle_fall_timer()                      # 首 tick：进入贴地窗口，不锁定
    assert app.game.current_type == piece_before
    app._now = _LOCK_DELAY_MS + 100
    app.handle_fall_timer()                      # 窗口已满 → 锁定
    assert app.game.current_type != piece_before  # 已锁定并生成新块
    assert app.game.total_lines == lines_before   # 空盘无消行


def test_lock_delay_holds_and_resets_on_move() -> None:
    """锁定延迟：贴地后 500ms 内可操作；成功移动重置计时。"""
    app = _app_with_piece_at_bottom()
    piece_before = app.game.current_type

    app._now = 0
    app.handle_fall_timer()               # 开始贴地计时
    app._now = 300
    app._on_input_action(Action.MOVE_LEFT)  # 移动成功 → 重置计时
    app._now = 400
    app.handle_fall_timer()               # 重新开始计时（t=400）
    app._now = 800
    app.handle_fall_timer()               # 400ms < 500ms → 仍不锁定
    assert app.game.current_type == piece_before

    app._now = 400 + _LOCK_DELAY_MS + 100  # 已超窗口
    app.handle_fall_timer()
    assert app.game.current_type != piece_before  # 锁定并生成新块
