# tetris.py — 我的方块专业版（macOS Lab）
# 主窗口管理、事件处理、音频控制
#
# 设计目标：使用逻辑表面（_logical）独立于物理窗口尺寸，
# 保证所有文字与方块在视网膜屏上依然清晰。
# 左侧面板展示游戏信息，右侧展示状态与预览。
# 音频模块尽可能静默加载，不因缺少资源而崩溃。
#
# 此文件主要负责：
#  - 窗口创建与尺寸缩放
#  - 事件循环与状态转换
#  - 音频控制
#  - 将渲染委托给 Renderer 类（renderer.py）
#  - 创建 GameState 快照传递给 Renderer

from typing import final
import os
import sys
import json

import pygame  # via pygame-ce
import platformdirs

from engine import TetrisEngine, GRID_WIDTH, GRID_HEIGHT, MAX_SCORE
from renderer import Renderer, SCREEN_WIDTH, SCREEN_HEIGHT
from game_state import GameState

# ---------- 资源路径辅助函数（支持开发环境和 PyInstaller 打包） ----------
def _resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，同时兼容 PyInstaller 打包后的路径。"""
    # 在 macOS BUNDLE + onedir 模式下，sys._MEIPASS 运行时直接指向 .app/Contents/Resources/
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)
# -------------------------------------------------------------------------

# 方块大小（逻辑像素）
BLOCK_SIZE = 30

# 最小窗口尺寸（小于此值会被强制拉伸到该最小尺寸）
# 增加50像素避免黑边过窄
MIN_WINDOW_WIDTH = max(400, 160 + GRID_WIDTH * BLOCK_SIZE + 200 + 50)
MIN_WINDOW_HEIGHT = 400

# ---- 音频文件路径（使用 _resource_path 以适应打包环境） ----
BG_MUSIC_FILE = _resource_path("assets/bg_music.mp3")
CLEAR_SOUND_FILE = _resource_path("assets/clear.wav")
GAME_OVER_SOUND_FILE = _resource_path("assets/game_over.mp3")
# ------------------------------------------------------------

# ---- 应用图标路径 ----
LOGO_FILE = _resource_path("assets/logo.png")
# -----------------------

# ---- 字体文件路径（使用统一常量便于替换） ----
FONT_FILE = _resource_path("assets/fonts/DejaVuSans-Bold.ttf")
HELP_FONT_FILE = _resource_path("assets/fonts/DejaVuSansMono.ttf")
# ---------------------------------------------

@final
class TetrisApp:
    """我的方块主应用程序类，负责窗口管理、事件循环和音频控制。"""
    screen: pygame.Surface
    game: TetrisEngine
    fall_event: int
    current_level: int
    paused: bool
    confirm_quit: bool
    high_score: int
    game_start_ticks: int
    clock: pygame.time.Clock
    sidebar_bg: tuple[int, int, int]
    window_width: int
    window_height: int
    _logical: pygame.Surface | None
    # 音频相关
    audio_enabled: bool
    sounds: dict[str, pygame.mixer.Sound]
    music_enabled: bool
    sfx_enabled: bool
    _game_over_sound_played: bool
    _music_paused_for_gamepause: bool
    # 字体缓存（基于 scale 懒加载）
    _current_scale: float
    _font_big: pygame.font.Font | None
    _font_small: pygame.font.Font | None
    _help_font: pygame.font.Font | None
    # 配置文件的影子值（从文件读取的原始值，用于判断是否有变化）
    _initial_music_enabled: bool
    _initial_sfx_enabled: bool
    _initial_high_score: int
    # HELP 相关
    _help_active: bool

    # ---------- 自动重复键状态 ----------
    _DAS_INITIAL = 200
    _DAS_INTERVAL = 50
    _key_pressed_time: dict[int, int]
    _key_last_action_time: dict[int, int]
    # -----------------------------------------

    # ---- 渲染器实例 ----
    renderer: Renderer

    def __init__(self) -> None:
        """初始化 Pygame、窗口、字体、游戏引擎、音频等。"""
        pygame.init()
        self._init_display_sizes()
        self._init_window_and_surfaces()
        self._init_input()
        self._init_game_state()
        self._init_sidebar_style()
        self._enforce_min_size()
        self._init_icon()
        self._init_audio()
        # 初始时鼠标可见（不再全局隐藏）
        pygame.mouse.set_visible(True)
        # 字体缓存初始化
        self._current_scale = 0.0
        self._font_big = None
        self._font_small = None
        self._help_font = None

        # 初始化 DAS 状态字典
        self._key_pressed_time = {}
        self._key_last_action_time = {}

        # 创建渲染器实例
        self.renderer = Renderer()

    # ------------------------------------------------------------------
    # 初始化辅助方法 (将 __init__ 按功能拆分)
    # ------------------------------------------------------------------

    def _init_display_sizes(self) -> None:
        """计算初始窗口尺寸（消除黑边）。"""
        display_info = pygame.display.Info()
        screen_w = display_info.current_w
        screen_h = display_info.current_h

        # 初始窗口大小（物理窗口的80%）
        init_w = int(screen_w * 0.8)
        init_h = int(screen_h * 0.8)

        # 计算消除黑边的窗口尺寸
        scale_w = init_w / SCREEN_WIDTH
        scale_h = init_h / SCREEN_HEIGHT
        if scale_w < scale_h:
            new_w = init_w
            new_h = int(SCREEN_HEIGHT * scale_w)
        elif scale_h < scale_w:
            new_w = int(SCREEN_WIDTH * scale_h)
            new_h = init_h
        else:
            new_w = init_w
            new_h = init_h

        # 确保不小于最小尺寸
        self.window_width = max(new_w, MIN_WINDOW_WIDTH)
        self.window_height = max(new_h, MIN_WINDOW_HEIGHT)

    def _init_window_and_surfaces(self) -> None:
        """创建显示窗口、字体、逻辑表面。"""
        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height), pygame.RESIZABLE
        )
        pygame.display.set_caption("MyTetris Professional - macOS Lab")
        self._logical = None   # 逻辑表面，渲染时按比例缩放

    def _init_input(self) -> None:
        """设置按键重复参数。"""
        # 关闭全局自动重复，所有方向键的自动重复由我们手动实现
        pygame.key.set_repeat(0)

    # ---------- 配置文件辅助 ----------
    def _config_file(self) -> str:
        """返回配置文件 config.json 的路径，并确保目录存在。"""
        data_dir = platformdirs.user_data_dir("mytetris")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "config.json")

    def _load_config(self) -> None:
        """从配置文件读取音乐开关、音效开关和最高分。"""
        path = self._config_file()
        try:
            with open(path, "r") as f:
                cfg = json.load(f)
            self.music_enabled = bool(cfg.get("music_enabled", True))
            self.sfx_enabled = bool(cfg.get("sfx_enabled", True))
            raw_high_score = int(cfg.get("high_score", 0))
            # 如果读取的分值超过上限，运行时卡在 MAX_SCORE，但影子值保留原始值
            if raw_high_score > MAX_SCORE:
                self._initial_high_score = raw_high_score
                self.high_score = MAX_SCORE
            else:
                self._initial_high_score = raw_high_score
                self.high_score = raw_high_score
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass
        # 记录当前值作为影子值（之后比较变化时使用）
        self._initial_music_enabled = self.music_enabled
        self._initial_sfx_enabled = self.sfx_enabled

    def _save_config(self) -> None:
        """将音乐开关、音效开关和最高分写入配置文件（只在有变化时写入）。"""
        if (self.music_enabled == self._initial_music_enabled
                and self.sfx_enabled == self._initial_sfx_enabled
                and self.high_score == self._initial_high_score):
            return
        path = self._config_file()
        cfg = {
            "music_enabled": self.music_enabled,
            "sfx_enabled": self.sfx_enabled,
            "high_score": self.high_score,
        }
        try:
            with open(path, "w") as f:
                json.dump(cfg, f)
            self._initial_music_enabled = self.music_enabled
            self._initial_sfx_enabled = self.sfx_enabled
            self._initial_high_score = self.high_score
        except Exception:
            pass

    def _init_game_state(self) -> None:
        """初始化游戏引擎、定时器、等级、分数、暂停等状态。"""
        self.game = TetrisEngine()
        self.fall_event = pygame.USEREVENT + 1
        self.current_level = 1
        self._update_speed()
        self.clock = pygame.time.Clock()
        self.paused = False
        self.confirm_quit = False
        self.high_score = 0
        self.game_start_ticks = pygame.time.get_ticks()
        self.music_enabled = True
        self.sfx_enabled = True
        self._initial_music_enabled = True
        self._initial_sfx_enabled = True
        self._initial_high_score = 0
        self._game_over_sound_played = False
        self._music_paused_for_gamepause = False
        self._help_active = False
        self._load_config()

    def _init_sidebar_style(self) -> None:
        """设置侧边栏背景色（灰蓝色调）。"""
        self.sidebar_bg = (40, 45, 55)

    def _init_icon(self) -> None:
        """设置窗口图标。"""
        if os.path.isfile(LOGO_FILE):
            try:
                icon_surf = pygame.image.load(LOGO_FILE).convert_alpha()
                pygame.display.set_icon(icon_surf)
            except pygame.error:
                pass

    def _init_audio(self) -> None:
        """尽量加载背景音乐与删除行音效，若缺少文件则静默运行。"""
        self.audio_enabled = False
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            if os.path.isfile(BG_MUSIC_FILE):
                pygame.mixer.music.load(BG_MUSIC_FILE)

            if os.path.isfile(CLEAR_SOUND_FILE):
                self.sounds["clear"] = pygame.mixer.Sound(CLEAR_SOUND_FILE)

            if os.path.isfile(GAME_OVER_SOUND_FILE):
                self.sounds["game_over"] = pygame.mixer.Sound(GAME_OVER_SOUND_FILE)

            if os.path.isfile(BG_MUSIC_FILE) or self.sounds:
                self.audio_enabled = True

            if self.music_enabled and os.path.isfile(BG_MUSIC_FILE):
                pygame.mixer.music.play(-1)

        except Exception:
            self.audio_enabled = False

    def _toggle_music(self) -> None:
        """切换背景音乐的开关（M键）。"""
        if not self.audio_enabled:
            return
        self.music_enabled = not self.music_enabled
        if self.music_enabled:
            try:
                pygame.mixer.music.play(-1)
            except pygame.error:
                pass
        else:
            pygame.mixer.music.stop()

    def _toggle_sfx(self) -> None:
        """切换音效的开关（S键）。"""
        if not self.audio_enabled:
            return
        self.sfx_enabled = not self.sfx_enabled

    def _play_sound(self, name: str) -> None:
        """播放指定音效（若已启用且资源存在）。"""
        if self.audio_enabled and name in self.sounds and self.sfx_enabled:
            self.sounds[name].play()

    def _enforce_min_size(self) -> None:
        """确保当前窗口不小于最小尺寸。"""
        current_w, current_h = self.screen.get_size()
        new_w = max(current_w, MIN_WINDOW_WIDTH)
        new_h = max(current_h, MIN_WINDOW_HEIGHT)
        if (new_w, new_h) != (current_w, current_h):
            self.screen = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)
            self.window_width = new_w
            self.window_height = new_h

    def _update_speed(self) -> None:
        """根据等级计算下落速度（每级减50ms，最低100ms）。"""
        speed = max(100, 500 - (self.game.level - 1) * 50)
        pygame.time.set_timer(self.fall_event, speed)
        self.current_level = self.game.level

    def _check_level_upgrade(self) -> None:
        """如果等级发生变化则更新下落速度"""
        if self.game.level != self.current_level:
            self._update_speed()

    def _update_high_score(self) -> None:
        """实时更新最高分（内存中）。退出时统一保存配置。"""
        if self.game.score > self.high_score:
            self.high_score = min(self.game.score, MAX_SCORE)

    def _lock_and_update(self) -> None:
        """锁定当前方块，清除满行，更新分数、等级、音效。"""
        if self.game.game_over:
            return
        prev_lines = self.game.total_lines
        self.game.lock_and_clear_lines()
        if self.game.total_lines > prev_lines:
            self._play_sound("clear")
        self._update_high_score()
        self._check_level_upgrade()

    def _restart_game(self) -> None:
        """重置游戏所有状态，回到新游戏初始状态。"""
        self.game.reset()
        self.current_level = 1
        self._update_speed()
        self.paused = False
        self.game_start_ticks = pygame.time.get_ticks()
        self._game_over_sound_played = False
        self._music_paused_for_gamepause = False
        self._help_active = False
        self._key_pressed_time.clear()
        self._key_last_action_time.clear()

    def _toggle_help(self) -> None:
        """切换帮助界面的显示/隐藏。"""
        if self._help_active:
            self._help_active = False
            if not self.game.game_over and not self.paused:
                self._update_speed()
        else:
            self._help_active = True
            pygame.time.set_timer(self.fall_event, 0)

    def _build_game_state(self) -> GameState:
        """从当前游戏状态创建一个只读快照。"""
        return GameState(
            grid=[row[:] for row in self.game.grid],
            current_type=self.game.current_type,
            current_shape=self.game.current_shape.copy(),
            current_x=self.game.x,
            current_y=self.game.y,
            next_type=self.game.next_type,
            score=self.game.score,
            level=self.game.level,
            total_lines=self.game.total_lines,
            high_score=self.high_score,
            game_start_ticks=self.game_start_ticks,
            game_over=self.game.game_over,
            paused=self.paused,
            confirm_quit=self.confirm_quit,
            help_active=self._help_active,
            music_enabled=self.music_enabled,
            sfx_enabled=self.sfx_enabled,
        )

    def run(self) -> None:
        """主循环：保持窗口尺寸、处理事件、渲染场景"""
        while True:
            self._enforce_min_size()
            self._process_events()
            self._process_auto_repeat()
            self._render_game_scene()
            self.clock.tick(60)

    def _process_events(self) -> None:
        """处理所有事件（按优先级和状态分发）"""
        if self.game.game_over and not self._game_over_sound_played:
            self._play_sound("game_over")
            self._game_over_sound_played = True

        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                self._toggle_music()
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_s:
                self._toggle_sfx()
                continue
            if event.type == pygame.QUIT:
                self._handle_quit()
                return
            if event.type == pygame.VIDEORESIZE:
                self._handle_resize(event)
                continue

            if self._help_active:
                if event.type == pygame.KEYDOWN:
                    self._toggle_help()
                    continue
                continue

            if self.confirm_quit:
                self._handle_confirm_quit_event(event)
            elif self.game.game_over:
                self._handle_game_over_event(event)
            elif self.paused:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_p:
                        self._toggle_pause()
                    elif event.key == pygame.K_ESCAPE:
                        self.confirm_quit = True
            else:
                self._handle_playing_event(event)

    def _handle_quit(self) -> None:
        """处理退出事件（保存配置、关闭窗口、退出进程）。"""
        self._save_config()
        pygame.mouse.set_visible(True)
        pygame.quit()
        sys.exit()

    def _handle_resize(self, event: pygame.event.Event) -> None:
        """处理窗口大小改变事件。"""
        new_w = max(event.w, MIN_WINDOW_WIDTH)
        new_h = max(event.h, MIN_WINDOW_HEIGHT)
        self.window_width = new_w
        self.window_height = new_h
        self.screen = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)

    def _handle_confirm_quit_event(self, event: pygame.event.Event) -> None:
        """处理确认退出状态下的按键事件。"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._handle_quit()
            elif event.key == pygame.K_r:
                self._restart_game()
                self.confirm_quit = False
            else:
                self.confirm_quit = False

    def _handle_game_over_event(self, event: pygame.event.Event) -> None:
        """处理游戏结束状态下的按键事件。"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._restart_game()
            elif event.key == pygame.K_ESCAPE:
                self._handle_quit()

    def _handle_playing_event(self, event: pygame.event.Event) -> None:
        """处理正常游戏进行中的事件。"""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.confirm_quit = True
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            self._toggle_pause()
        elif event.type == self.fall_event:
            self._handle_fall_timer()
        elif event.type == pygame.KEYDOWN:
            key = event.key
            mods = pygame.key.get_mods()
            if key == pygame.K_F1:
                self._toggle_help()
            elif key == pygame.K_SLASH and (mods & pygame.KMOD_SHIFT):
                self._toggle_help()
            else:
                self._handle_movement_key(event.key)

    def _toggle_pause(self) -> None:
        """切换暂停状态。"""
        if self.game.game_over:
            return
        self.paused = not self.paused
        if self.paused:
            pygame.time.set_timer(self.fall_event, 0)
            if self.music_enabled and pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
                self._music_paused_for_gamepause = True
        else:
            self._update_speed()
            if self.music_enabled and self._music_paused_for_gamepause:
                try:
                    pygame.mixer.music.unpause()
                except pygame.error:
                    pass
                if not pygame.mixer.music.get_busy():
                    try:
                        pygame.mixer.music.play(-1)
                    except pygame.error:
                        pass
                self._music_paused_for_gamepause = False

    def _handle_fall_timer(self) -> None:
        """处理下落定时器事件。"""
        if not self.game.move(0, 1):
            self._lock_and_update()

    def _handle_movement_key(self, key: int) -> None:
        """处理方向键和空格键（硬降）。"""
        now = pygame.time.get_ticks()
        if key == pygame.K_UP:
            self.game.rotate()
        elif key == pygame.K_LEFT:
            self.game.move(-1, 0)
            self._key_pressed_time[pygame.K_LEFT] = now
            self._key_last_action_time[pygame.K_LEFT] = now
        elif key == pygame.K_RIGHT:
            self.game.move(1, 0)
            self._key_pressed_time[pygame.K_RIGHT] = now
            self._key_last_action_time[pygame.K_RIGHT] = now
        elif key == pygame.K_DOWN:
            if not self.game.move(0, 1):
                self._lock_and_update()
            self._key_pressed_time[pygame.K_DOWN] = now
            self._key_last_action_time[pygame.K_DOWN] = now
        elif key == pygame.K_SPACE:
            while self.game.move(0, 1):
                pass
            self._lock_and_update()

    def _process_auto_repeat(self) -> None:
        """每帧检查持续按下的方向键，按照 DAS 参数触发重复移动。"""
        if self.game.game_over or self.paused or self.confirm_quit or self._help_active:
            self._key_pressed_time.clear()
            self._key_last_action_time.clear()
            return

        now = pygame.time.get_ticks()
        keys = pygame.key.get_pressed()

        repeat_keys = {
            pygame.K_LEFT: lambda: self.game.move(-1, 0),
            pygame.K_RIGHT: lambda: self.game.move(1, 0),
            pygame.K_DOWN: self._auto_soft_drop,
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
                            action()
            else:
                self._key_pressed_time.pop(key, None)
                self._key_last_action_time.pop(key, None)

    def _auto_soft_drop(self) -> None:
        """软降自动重复时执行的一步下落。"""
        if not self.game.move(0, 1):
            self._lock_and_update()

    def _render_game_scene(self) -> None:
        """极致渲染：创建逻辑表面、保证字体、构建状态、委托给 Renderer。"""
        scale = min(
            self.window_width / SCREEN_WIDTH,
            self.window_height / SCREEN_HEIGHT,
        )
        logical_w = int(SCREEN_WIDTH * scale)
        logical_h = int(SCREEN_HEIGHT * scale)

        if (self._logical is None
                or self._logical.get_width() != logical_w
                or self._logical.get_height() != logical_h):
            self._logical = pygame.Surface((logical_w, logical_h))

        if (self._font_big is None
                or self._font_small is None
                or self._help_font is None
                or abs(scale - self._current_scale) > 1e-9):
            self._current_scale = scale
            font_size = max(10, int(32 * scale))
            small_font_size = max(8, int(20 * scale))
            help_font_size = max(8, int(20 * scale))
            self._font_big = pygame.font.Font(FONT_FILE, font_size)
            self._font_small = pygame.font.Font(FONT_FILE, small_font_size)
            self._help_font = pygame.font.Font(HELP_FONT_FILE, help_font_size)

            self.renderer.update_fonts(
                scale, self._font_big, self._font_small, self._help_font,
            )

        state = self._build_game_state()

        self.renderer.render(state, self._logical, scale)

        x_off = (self.window_width - logical_w) // 2
        y_off = (self.window_height - logical_h) // 2

        self.screen.fill(self.sidebar_bg)
        self.screen.blit(self._logical, (x_off, y_off))

        bs = int(BLOCK_SIZE * scale)
        left_width_px = int(160 * scale)
        board_left_px = left_width_px
        board_w_px = GRID_WIDTH * bs
        board_h_px = GRID_HEIGHT * bs

        mx, my = pygame.mouse.get_pos()
        board_phys_left = x_off + board_left_px
        board_phys_top = y_off
        board_phys_right = board_phys_left + board_w_px
        board_phys_bottom = board_phys_top + board_h_px
        in_board = (board_phys_left <= mx <= board_phys_right and
                    board_phys_top <= my <= board_phys_bottom)

        if in_board:
            if pygame.mouse.get_visible():
                pygame.mouse.set_visible(False)
        else:
            if not pygame.mouse.get_visible():
                pygame.mouse.set_visible(True)

        pygame.display.flip()
