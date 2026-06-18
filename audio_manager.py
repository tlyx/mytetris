# audio_manager.py — 音频管理器
# 负责所有音频相关的加载、播放、暂停、切换，与 TetrisApp 解耦。
# 使用 resource_path 获取资产文件的绝对路径（支持开发环境和 PyInstaller 打包）。

from __future__ import annotations

from pathlib import Path
from typing import final

import pygame  # via pygame-ce

from utils import resource_path


# 音频文件路径（使用 resource_path 以适应打包环境）
BG_MUSIC_FILE = resource_path("assets/bg_music.mp3")
CLEAR_SOUND_FILE = resource_path("assets/clear.wav")
GAME_OVER_SOUND_FILE = resource_path("assets/game_over.mp3")


@final
class AudioManager:
    """管理背景音乐与音效的加载、播放、暂停及切换。"""

    def __init__(self) -> None:
        # 是否成功加载了任何音频资源（至少一个文件存在）
        self.audio_enabled: bool = False
        # 已加载的音效字典
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        # 音乐/音效开关（初始值由外部设置）
        self.music_enabled: bool = True
        self.sfx_enabled: bool = True
        # 内部状态：因游戏暂停而暂停的音乐是否应恢复
        self._music_paused_by_pause: bool = False

    def load(self) -> None:
        """尝试加载背景音乐与音效文件，若缺少文件则静默运行。
           在调用此方法之前，应通过外部设置 self.music_enabled 和 self.sfx_enabled。
        """
        self.audio_enabled = False
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            if Path(BG_MUSIC_FILE).is_file():
                pygame.mixer.music.load(BG_MUSIC_FILE)

            if Path(CLEAR_SOUND_FILE).is_file():
                self.sounds["clear"] = pygame.mixer.Sound(CLEAR_SOUND_FILE)

            if Path(GAME_OVER_SOUND_FILE).is_file():
                self.sounds["game_over"] = pygame.mixer.Sound(GAME_OVER_SOUND_FILE)

            if Path(BG_MUSIC_FILE).is_file() or self.sounds:
                self.audio_enabled = True

            # 仅当音乐开关打开时才播放背景音乐
            if self.music_enabled and Path(BG_MUSIC_FILE).is_file():
                pygame.mixer.music.play(-1)

        except Exception as exc:
            print(f"WARNING: Failed to load audio files: {exc}")
            self.audio_enabled = False

        # 如果最终没有任何音频文件加载成功，打印一条警告
        if not self.audio_enabled:
            print(
                "WARNING: No audio files found (bg_music.mp3, clear.wav, game_over.mp3). "
                + "Game will run without sound."
            )

    # ---------- 音乐控制 ----------
    def play_music(self) -> None:
        """开始或恢复播放背景音乐。"""
        if not self.audio_enabled or not self.music_enabled:
            return
        try:
            pygame.mixer.music.play(-1)
        except pygame.error as exc:
            print(f"WARNING: Failed to play music: {exc}")

    def stop_music(self) -> None:
        """停止背景音乐。"""
        if not self.audio_enabled:
            return
        pygame.mixer.music.stop()

    def pause_music(self) -> None:
        """暂停背景音乐（仅当正在播放时），并标记为因游戏暂停而暂停。"""
        if not self.audio_enabled or not self.music_enabled:
            return
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self._music_paused_by_pause = True

    def resume_music(self) -> None:
        """恢复因游戏暂停而暂停的背景音乐。"""
        if not self.audio_enabled or not self.music_enabled:
            return
        if self._music_paused_by_pause:
            try:
                pygame.mixer.music.unpause()
            except pygame.error as exc:
                print(f"WARNING: Failed to unpause music: {exc}")
            # 如果音乐已停止（例如用户手动停止），则重新播放
            if not pygame.mixer.music.get_busy():
                try:
                    pygame.mixer.music.play(-1)
                except pygame.error as exc:
                    print(f"WARNING: Failed to replay music: {exc}")
            self._music_paused_by_pause = False

    def toggle_music(self) -> None:
        """切换背景音乐开关。返回切换后的音乐状态。"""
        if not self.audio_enabled:
            return
        self.music_enabled = not self.music_enabled
        if self.music_enabled:
            self.play_music()
        else:
            self.stop_music()

    def toggle_sfx(self) -> None:
        """切换音效开关。"""
        if not self.audio_enabled:
            return
        self.sfx_enabled = not self.sfx_enabled

    # ---------- 音效播放 ----------
    def play_sfx(self, name: str) -> None:
        """播放指定音效（若已启用且资源存在）。"""
        if self.audio_enabled and name in self.sounds and self.sfx_enabled:
            self.sounds[name].play()

    # ---------- 清理 ----------
    def shutdown(self) -> None:
        """停止所有音频，释放资源（退出时自动调用）。"""
        if self.audio_enabled:
            pygame.mixer.music.stop()
        self.sounds.clear()
        self._music_paused_by_pause = False
