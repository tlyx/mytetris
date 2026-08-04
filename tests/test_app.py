# tests/test_app.py — App 层行为测试
"""App 层回归测试。

重点覆盖 bot 模式与重力定时器的竞态修复：bot 启用时重力定时器不得
移动/锁定当前块（高等级或帧卡顿时，定时器可能抢在 bot 计划前把方块
直落锁定）。
"""

from __future__ import annotations

import os

# pygame 无头环境：必须在构造 TetrisApp（初始化显示/音频）之前设置
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from tetris import TetrisApp


def _app_with_piece_at_bottom() -> TetrisApp:
    """构造 App 并把当前块硬降到贴底（再下移必失败）。"""
    app = TetrisApp()
    app.game.reset()
    while app.game.move(0, -1):
        pass
    return app


def test_fall_timer_ignored_when_bot_enabled() -> None:
    """bot 模式下重力定时器不得移动/锁定当前块（竞态修复）。

    复现路径：贴底方块 + bot 开启 + 触发 handle_fall_timer。
    修复前定时器会把方块直接锁定（直落、不按 bot 计划）。
    """
    app = _app_with_piece_at_bottom()
    app.bot_enabled = True
    before = (app.game.current_type, app.game.x, app.game.y)
    app.handle_fall_timer()
    assert (app.game.current_type, app.game.x, app.game.y) == before
    assert not app.game.game_over


def test_fall_timer_locks_when_bot_disabled() -> None:
    """bot 关闭时定时器照常锁定贴底方块（门控不影响正常路径）。"""
    app = _app_with_piece_at_bottom()
    piece_before = app.game.current_type
    lines_before = app.game.total_lines
    app.handle_fall_timer()
    assert app.game.current_type != piece_before  # 已锁定并生成新块
    assert app.game.total_lines == lines_before   # 空盘无消行
