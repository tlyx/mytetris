# pyright: reportPrivateUsage=false
# test_app.py — App 层行为测试
# 覆盖公平性（bot 与人类共用重力/锁定延迟/计分）与指南标准计分。

"""App 层回归测试。

重点覆盖公平性：bot 模式与人类模式共用同一套重力/锁定延迟/计分机制
（bot 只是另一个输入源），以及软降/硬降计分等指南标准行为。
"""

import json
import os
from pathlib import Path

import pytest

# pygame 无头环境：必须在构造 GameApp（初始化显示/音频）之前设置
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from app import GameApp
from config_manager import ConfigManager
from contracts import Action
from engine import LOCK_DELAY_MS


def _app_with_piece_at_bottom() -> GameApp:
    """构造 App 并把当前块硬降到贴底（再下移必失败）。"""
    app = GameApp()
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
    app._now = LOCK_DELAY_MS + 100
    app.handle_fall_timer()  # 窗口已满 → 锁定
    assert app.game.current_type != piece_before  # 与 bot 关闭时一致
    assert not app.game.game_over


def test_cycle_bot_strategy() -> None:
    """循环切换 bot 策略：顺序遍历注册表。"""
    app = GameApp()
    assert app.bot.strategy == "modern"
    app.cycle_bot_strategy()
    assert app.bot.strategy == "legacy"
    app.cycle_bot_strategy()
    assert app.bot.strategy == "modern"


def test_drop_actions_score_points() -> None:
    """软降每格 +1、硬降每格 +2（指南标准计分）。"""
    app = GameApp()
    app.game.reset()

    score_before = app.game.score
    app._on_keyboard_action(Action.SOFT_DROP)
    assert app.game.score == score_before + 1  # 软降一格

    # 硬降：I 块空盘从生成位落到底（距离 = 生成 y），每格 +2
    app.game.reset()
    app.game.next_type = "I"
    app.game._spawn_piece()  # pyright: ignore[reportPrivateUsage]
    d_before = app.game.y    # I 的 max_py=0，生成在顶行 y=19
    app._on_keyboard_action(Action.HARD_DROP)
    assert app.game.score == 2 * d_before  # I 落到底，距离恰为 d_before


def test_fall_timer_locks_when_bot_disabled() -> None:
    """bot 关闭时定时器按锁定延迟锁定贴底方块（门控不影响正常路径）。"""
    app = _app_with_piece_at_bottom()
    piece_before = app.game.current_type
    lines_before = app.game.total_lines
    app._now = 0
    app.handle_fall_timer()                      # 首 tick：进入贴地窗口，不锁定
    assert app.game.current_type == piece_before
    app._now = LOCK_DELAY_MS + 100
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
    app._on_keyboard_action(Action.MOVE_LEFT)  # 移动成功 → 重置计时
    app._now = 400
    app.handle_fall_timer()               # 重新开始计时（t=400）
    app._now = 800
    app.handle_fall_timer()               # 400ms < 500ms → 仍不锁定
    assert app.game.current_type == piece_before

    app._now = 400 + LOCK_DELAY_MS + 100  # 已超窗口
    app.handle_fall_timer()
    assert app.game.current_type != piece_before  # 锁定并生成新块


def test_lock_delay_reset_budget_capped_at_15() -> None:
    """锁定延迟重置预算（指南标准）：每块最多 15 次成功移动重置。

    预算耗尽后继续移动不再延长计时，500ms 窗口走完即锁定。
    """
    app = _app_with_piece_at_bottom()
    piece_before = app.game.current_type
    app._now = 0
    app.handle_fall_timer()  # 进入贴地窗口
    assert app.game.current_type == piece_before
    # 15 次成功移动（左右交替，保证每次都成功）——每次重置计时并消耗预算
    for i in range(15):
        app._now = 100 * (i + 1)
        app._on_keyboard_action(Action.MOVE_LEFT if i % 2 == 0 else Action.MOVE_RIGHT)
        app.handle_fall_timer()
        assert app.game.current_type == piece_before
    # 预算耗尽（15/15）：第 16 次移动不再重置，计时仍从 t=1500 起算
    app._now = 1600
    app._on_keyboard_action(Action.MOVE_LEFT)
    app.handle_fall_timer()
    assert app.game.current_type == piece_before  # 1600-1500=100ms < 500
    app._now = 2100
    app.handle_fall_timer()  # 2100-1500=600ms >= 500 → 锁定
    assert app.game.current_type != piece_before


def test_ghost_enabled_loaded_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ghost 开关启动时读取配置，而非默认 False。

    回归：__init__ 里晚于 _init_config() 的 `self.ghost_enabled = False`
    会把配置文件里已保存的值冲掉——配置写了但永远不生效。
    """
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"ghost_enabled": True}))

    def _fake_config_file(self: ConfigManager) -> Path:
        return cfg

    monkeypatch.setattr(ConfigManager, "_config_file", _fake_config_file)
    app = GameApp()
    assert app.ghost_enabled is True
    assert app.config.ghost_enabled is True


def test_t_spin_playthrough_via_app_actions():
    """通过 TetrisApp 真实动作路径打出 T-spin 单消（补偿无法手测的用户）。

    动作序列与手玩一致：空中旋转 → 右移 → 软降进缺口 → 收尾旋转 →
    走锁定窗口（handle_fall_timer 贴地计时）。锁定瞬间应恰 +800。
    """
    app = GameApp()
    app.game.reset()
    # 搭结构：底行留第 5 列缺口 + 帽子 (3,1)/(4,2)
    for col in range(10):
        if col != 5:
            app.game.grid[0][col] = (1, 1, 1)
    app.game.grid[1][3] = (1, 1, 1)
    app.game.grid[2][4] = (1, 1, 1)
    # 指定 T 块
    app.game.next_type = "T"
    app.game._spawn_piece()
    # ① 空中旋转 → rot1
    app._apply_action(Action.ROTATE)
    # ② 右移到缺口上方
    while app.game.x < 5:
        app._apply_action(Action.MOVE_RIGHT)
    # ③ 软降进缺口（软降清标志，无妨）
    while app.game.soft_drop():
        pass
    # ④ 收尾旋转（最后动作）
    app._apply_action(Action.ROTATE)
    assert app.game.last_was_rotation is True
    assert app.game.rotation == 2
    # ⑤ 走锁定窗口：首 tick 开始贴地计时，窗口满后锁定
    score_before = app.game.score
    app._now = 1000
    app.handle_fall_timer()  # 贴地 → resting_since = 1000
    app._now = 1000 + LOCK_DELAY_MS + 1
    app.handle_fall_timer()  # 窗口满 → 锁定结算
    assert app.game.total_lines == 1
    assert app.game.score - score_before == 800  # T-spin 单消 +800
