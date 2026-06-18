# config_manager.py — 配置管理器（读取/写入 config.json）
# 负责管理游戏配置的持久化，仅在值发生变化时写入文件。
# 使用平台无关的用户数据目录（通过 platformdirs）。

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, final

import platformdirs

from engine import MAX_SCORE

# 配置值的类型：bool 或 int
ConfigValue = bool | int


@final
class ConfigManager:
    """管理游戏配置（音乐、音效、消行动画、最高分）的加载与保存。"""

    # 配置字段默认值
    _defaults: ClassVar[dict[str, ConfigValue]] = {
        "music_enabled": True,
        "sfx_enabled": True,
        "clear_anim_enabled": True,
        "high_score": 0,
    }

    _app_name: str
    _data: dict[str, bool | int]
    _shadow: dict[str, bool | int]  # 用于检测变化

    def __init__(self, app_name: str = "mytetris") -> None:
        self._app_name = app_name
        self._data = {}
        self._shadow = {}

    # ---------- 配置文件路径 ----------
    def _config_file(self) -> Path:
        """返回配置文件 config.json 的路径，并确保目录存在。"""
        data_dir = Path(platformdirs.user_data_dir(self._app_name))
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "config.json"

    # ---------- 加载配置 ----------
    def load(self) -> None:
        """从配置文件读取所有配置项，若文件不存在或解析失败则使用默认值。"""
        path = self._config_file()
        # 先重置为默认值
        self._data = dict(ConfigManager._defaults)
        try:
            with open(path, "r") as f:
                cfg = json.load(f)
            # 只从文件中读取已知键
            for key in ConfigManager._defaults:
                if key in cfg:
                    value = cfg[key]
                    # 对最高分进行上限和下限检查
                    if key == "high_score":
                        value = int(value)
                        if value < 0:
                            value = 0
                        elif value > MAX_SCORE:
                            value = MAX_SCORE
                    # 其他字段转为布尔值
                    elif key in ("music_enabled", "sfx_enabled", "clear_anim_enabled"):
                        value = bool(value)
                    self._data[key] = value
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass
        # 记录初始影子值
        self._shadow = dict(self._data)

    # ---------- 保存配置（仅在值有变化时写入） ----------
    def save(self) -> None:
        """将当前配置写入文件，仅当任何字段发生变化时才实际写入。"""
        if self._data == self._shadow:
            return
        path = self._config_file()
        try:
            with open(path, "w") as f:
                json.dump(self._data, f, indent=2)
            self._shadow = dict(self._data)
        except Exception:
            pass  # 静默忽略写入错误

    # ---------- 读取配置项 ----------
    def get(self, key: str) -> ConfigValue:
        """返回指定配置项的当前值。"""
        # 字典中所有键始终存在（加载时已确保），无需 cast
        return self._data.get(key, ConfigManager._defaults[key])

    # ---------- 设置配置项 ----------
    def set(self, key: str, value: ConfigValue) -> None:
        """设置指定配置项的值，不会立即写入文件（需调用 save）。"""
        if key in self._data:
            self._data[key] = value

    # ---------- 便捷属性访问（与原有 TetrisApp 属性名一致） ----------
    @property
    def music_enabled(self) -> bool:
        val = self._data["music_enabled"]
        # 运行时应为布尔值，确保类型检查通过
        assert isinstance(val, bool)
        return val

    @music_enabled.setter
    def music_enabled(self, value: bool) -> None:
        self._data["music_enabled"] = value

    @property
    def sfx_enabled(self) -> bool:
        val = self._data["sfx_enabled"]
        assert isinstance(val, bool)
        return val

    @sfx_enabled.setter
    def sfx_enabled(self, value: bool) -> None:
        self._data["sfx_enabled"] = value

    @property
    def clear_anim_enabled(self) -> bool:
        val = self._data["clear_anim_enabled"]
        assert isinstance(val, bool)
        return val

    @clear_anim_enabled.setter
    def clear_anim_enabled(self, value: bool) -> None:
        self._data["clear_anim_enabled"] = value

    @property
    def high_score(self) -> int:
        val = self._data["high_score"]
        assert isinstance(val, int)
        return val

    @high_score.setter
    def high_score(self, value: int) -> None:
        if value < 0:
            value = 0
        elif value > MAX_SCORE:
            value = MAX_SCORE
        self._data["high_score"] = value
