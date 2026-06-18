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
#  - 事件循环与状态转换（使用状态模式）
#  - 音频控制（委托给 AudioManager）
#  - 将渲染委托给 Renderer 类（renderer.py）
#  - 创建 GameState 快照传递给 Renderer
#  - 输入处理（委托给 InputHandler）

from typing import final
import sys
from pathlib import Path

import pygame  # via pygame-ce

from engine import TetrisEngine, GRID_WIDTH, GRID_HEIGHT, MAX_SCORE
from renderer import Renderer, SCREEN_WIDTH, SCREEN_HEIGHT
from game_state import GameState
from config_manager import ConfigManager
from audio_manager import AudioManager
from input_handler import InputHandler, Action
from state_handlers import (
    StateHandler,
    PlayingState,
    GameOverState,
)

# ---------- 资源路径辅助函数（支持开发环境和 PyInstaller 打包） ----------
def _resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，同时兼容 PyInstaller 打包后的路径。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / relative_path)
# -------------------------------------------------------------------------

# 方块大小（逻辑像素）
BLOCK_SIZE = 30

# 最小窗口尺寸（小于此值会被强制拉伸到该最小尺寸）
# 增加50像素避免黑边过窄
MIN_WINDOW_WIDTH = max(400, 160 + GRID_WIDTH * BLOCK_SIZE + 200 + 50)
MIN_WINDOW_HEIGHT = 400

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
    # 音频相关（委托给 AudioManager）
    audio: AudioManager
    _game_over_sound_played: bool
    # 字体缓存（基于 scale 懒加载）
    _current_scale: float
    _font_big: pygame.font.Font | None
    _font_small: pygame.font.Font | None
    _help_font: pygame.font.Font | None
    # HELP 相关
    _help_active: bool

    # Ghost piece 开关
    ghost_enabled: bool

    # 消行动画开关
    clear_anim_enabled: bool

    # ---- 输入处理器 ----
    input_handler: InputHandler

    # ---- 渲染器实例 ----
    renderer: Renderer

    # ---- 配置管理器 ----
    config: ConfigManager

    # ---- 当前状态处理器（状态模式） ----
    _current_state: StateHandler

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

        # ---- 加载配置（优先于音频初始化） ----
        self._init_config()

        # ---- 初始化音频（使用配置中的音乐/音效开关） ----
        self.audio = AudioManager()
        self.audio.music_enabled = self.music_enabled
        self.audio.sfx_enabled = self.sfx_enabled
        self.audio.load()

        # ---- 初始化输入处理器 ----
        self.input_handler = InputHandler(self._on_input_action)

        # ---- 初始化状态处理器（默认 Playing） ----
        self._current_state = PlayingState()

        # 初始时鼠标可见（不再全局隐藏）
        pygame.mouse.set_visible(True)
        # 字体缓存初始化
        self._current_scale = 0.0
        self._font_big = None
        self._font_small = None
        self._help_font = None

        # 默认关闭 ghost piece
        self.ghost_enabled = False

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
        # 关闭全局自动重复，所有方向键的自动重复由 InputHandler 实现
        pygame.key.set_repeat(0)

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
        self.clear_anim_enabled = True
        self._game_over_sound_played = False
        self._help_active = False

    def _init_sidebar_style(self) -> None:
        """设置侧边栏背景色（灰蓝色调）。"""
        self.sidebar_bg = (40, 45, 55)

    def _init_icon(self) -> None:
        """设置窗口图标。"""
        if Path(LOGO_FILE).is_file():
            try:
                icon_surf = pygame.image.load(LOGO_FILE).convert_alpha()
                pygame.display.set_icon(icon_surf)
            except pygame.error:
                pass

    def _init_config(self) -> None:
        """加载配置管理器并覆盖默认设置（音乐、音效、消行动画、最高分）。"""
        self.config = ConfigManager()
        self.config.load()
        self.music_enabled = self.config.music_enabled
        self.sfx_enabled = self.config.sfx_enabled
        self.clear_anim_enabled = self.config.clear_anim_enabled
        self.high_score = self.config.high_score

    # ---- 音频控制（委托给 AudioManager） ----
    def _toggle_music(self) -> None:
        """切换背景音乐的开关（M键）。"""
        self.audio.toggle_music()
        self.music_enabled = self.audio.music_enabled
        self.config.music_enabled = self.music_enabled

    def _toggle_sfx(self) -> None:
        """切换音效的开关（S键）。"""
        self.audio.toggle_sfx()
        self.sfx_enabled = self.audio.sfx_enabled
        self.config.sfx_enabled = self.sfx_enabled

    def _play_sound(self, name: str) -> None:
        """播放指定音效（若已启用且资源存在）。"""
        self.audio.play_sfx(name)

    def _toggle_ghost(self) -> None:
        """切换 Ghost piece（落点影子）显示开关。"""
        self.ghost_enabled = not self.ghost_enabled

    # ---- 输入动作回调（由 InputHandler 调用） ----
    def _on_input_action(self, action: Action) -> None:
        """根据 InputHandler 发出的动作执行对应的游戏逻辑。"""
        if action == Action.MOVE_LEFT:
            self.game.move(-1, 0)
        elif action == Action.MOVE_RIGHT:
            self.game.move(1, 0)
        elif action == Action.SOFT_DROP:
            if not self.game.move(0, 1):
                self._lock_and_update()
        elif action == Action.HARD_DROP:
            while self.game.move(0, 1):
                pass
            self._lock_and_update()
        elif action == Action.ROTATE:
            self.game.rotate()

    # -------------------- 公开方法（供状态处理器调用） --------------------
    def toggle_pause(self) -> None:
        """切换暂停状态（被状态类调用）。"""
        if self.game.game_over:
            return
        self.paused = not self.paused
        if self.paused:
            pygame.time.set_timer(self.fall_event, 0)
            self.audio.pause_music()
        else:
            self._update_speed()
            self.audio.resume_music()

    def handle_fall_timer(self) -> None:
        """处理下落定时器事件（被状态类调用）。"""
        if not self.game.move(0, 1):
            self._lock_and_update()

    def toggle_help(self) -> None:
        """切换帮助界面的显示/隐藏。"""
        if self._help_active:
            self._help_active = False
            if not self.game.game_over and not self.paused:
                self._update_speed()
        else:
            self._help_active = True
            pygame.time.set_timer(self.fall_event, 0)

    def restart_game(self) -> None:
        """重置游戏所有状态，回到新游戏初始状态。"""
        self.game.reset()
        self.current_level = 1
        self._update_speed()
        self.paused = False
        self.confirm_quit = False
        self.game_start_ticks = pygame.time.get_ticks()
        self._game_over_sound_played = False
        self._help_active = False
        self.input_handler.reset()
        # 状态切回 Playing
        self._current_state = PlayingState()

    def handle_quit(self) -> None:
        """处理退出事件（保存配置、关闭窗口、退出进程）。"""
        self.config.save()
        self.audio.shutdown()
        pygame.mouse.set_visible(True)
        pygame.quit()
        sys.exit()
    # ------------------------------------------------------------------

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
            self.config.high_score = self.high_score

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
            ghost_y=self.game.get_ghost_y(),
            ghost_enabled=self.ghost_enabled,
            clearing_rows=self.game.poll_cleared_rows(),
            clear_anim_enabled=self.clear_anim_enabled,
        )

    def run(self) -> None:
        """主循环：保持窗口尺寸、处理事件、渲染场景"""
        while True:
            self._enforce_min_size()
            self._process_events()
            # 只在游戏进行且非暂停/确认退出/帮助状态时处理自动重复
            if not (self.game.game_over or self.paused or self.confirm_quit or self._help_active):
                self.input_handler.process_auto_repeat()
            else:
                self.input_handler.reset()
            self._render_game_scene()
            self.clock.tick(60)

    def _process_events(self) -> None:
        """处理所有事件（按优先级和状态分发）"""
        # 全局一次性事件：game over 音效
        if self.game.game_over and not self._game_over_sound_played:
            self._play_sound("game_over")
            self._game_over_sound_played = True
            # 如果状态还不是 GameOver，切换过去
            if not isinstance(self._current_state, GameOverState):
                self._switch_state(GameOverState())

        for event in pygame.event.get():
            # --- 全局高优先级事件（任何时候都能响应）---
            if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                self._toggle_music()
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_s:
                self._toggle_sfx()
                continue
            # Ghost piece 开关（G键）全局响应
            if event.type == pygame.KEYDOWN and event.key == pygame.K_g:
                self._toggle_ghost()
                continue
            if event.type == pygame.QUIT:
                self._handle_quit()
                return
            if event.type == pygame.VIDEORESIZE:
                self._handle_resize(event)
                continue

            # 委托给当前状态处理器
            new_state = self._current_state.handle_event(self, event)
            if new_state is not None:
                self._switch_state(new_state)

    def _switch_state(self, new_state: StateHandler) -> None:
        """切换到新的状态，并调用生命周期方法。"""
        self._current_state.on_exit(self)
        self._current_state = new_state
        self._current_state.on_enter(self)

    def _handle_quit(self) -> None:
        """处理退出事件（保存配置、关闭窗口、退出进程）。"""
        self.config.save()
        self.audio.shutdown()
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
