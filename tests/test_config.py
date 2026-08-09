# pyright: reportPrivateUsage=false
# test_config.py — 配置持久化契约测试
# 覆盖：默认值、round-trip、缺失键回退、最高分钳制、无变化不落盘。

import json
from pathlib import Path

from config_manager import ConfigManager
from engine import MAX_SCORE


def _make_manager(path: Path) -> ConfigManager:
    cm = ConfigManager()
    cm._config_file = lambda: path  # 白盒：重定向到临时文件
    cm.load()
    return cm


def test_defaults_on_fresh_load(tmp_path: Path) -> None:
    cm = _make_manager(tmp_path / "config.json")
    assert cm.music_enabled is True
    assert cm.sfx_enabled is True
    assert cm.clear_anim_enabled is True
    assert cm.ghost_enabled is False  # 与旧行为一致：默认关闭落点影子
    assert cm.high_score == 0


def test_round_trip_preserves_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cm = _make_manager(path)
    cm.music_enabled = False
    cm.ghost_enabled = True
    cm.clear_anim_enabled = False
    cm.high_score = 12345
    cm.save()

    cm2 = _make_manager(path)
    assert cm2.music_enabled is False
    assert cm2.ghost_enabled is True
    assert cm2.clear_anim_enabled is False
    assert cm2.high_score == 12345


def test_missing_keys_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"music_enabled": False}))
    cm = _make_manager(path)
    assert cm.music_enabled is False
    assert cm.sfx_enabled is True  # 缺键 → 默认值
    assert cm.ghost_enabled is False
    assert cm.clear_anim_enabled is True


def test_high_score_is_clamped(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"high_score": MAX_SCORE + 100}))
    assert _make_manager(path).high_score == MAX_SCORE

    path.write_text(json.dumps({"high_score": -5}))
    assert _make_manager(path).high_score == 0


def test_save_is_noop_without_changes(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cm = _make_manager(path)
    cm.save()
    assert not path.exists()  # 无变化不落盘
