# tetris.py — 俄罗斯方块专业版（macOS Lab）
# 主窗口渲染、事件处理、音频控制
#
# 设计目标：使用逻辑表面（_logical）独立于物理窗口尺寸，
# 保证所有文字与方块在视网膜屏上依然清晰。
# 左侧面板展示游戏信息，右侧展示状态与预览。
# 音频模块尽可能静默加载，不因缺少资源而崩溃。

from typing import final
import os
import sys
import json

import pygame
import platformdirs

from engine import TetrisEngine, GRID_WIDTH, GRID_HEIGHT, COLORS, SHAPES_DATA, MAX_SCORE

# ---------- 资源路径辅助函数（支持开发环境和 PyInstaller 打包） ----------
def _resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，同时兼容 PyInstaller 打包后的路径。"""
    # 在 macOS BUNDLE + onedir 模式下，sys._MEIPASS 运行时直接指向 .app/Contents/Resources/
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)
# -------------------------------------------------------------------------

# 方块大小（逻辑像素）
BLOCK_SIZE = 30

# 左右两侧边栏宽度（逻辑像素）
LEFT_WIDTH = 160
RIGHT_WIDTH = 200

# 逻辑分辨率（基于 BLOCK_SIZE=30）
SCREEN_WIDTH = LEFT_WIDTH + GRID_WIDTH * BLOCK_SIZE + RIGHT_WIDTH
SCREEN_HEIGHT = GRID_HEIGHT * BLOCK_SIZE

# 最小窗口尺寸（小于此值会被强制拉伸到该最小尺寸）
# 增加50像素避免黑边过窄
MIN_WINDOW_WIDTH = max(400, LEFT_WIDTH + GRID_WIDTH * BLOCK_SIZE + RIGHT_WIDTH + 50)
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

# ---- 帮助文本（为避免重复创建，定义为常量） ----
HELP_LINES = [
    "HOW TO PLAY",
    "",
    "← →    Move left/right",
    "↓      Soft drop",
    "↑      Rotate",
    "Space  Hard drop",
    "",
    "P      Pause/Resume",
    "M      Toggle music",
    "S      Toggle sound effects",
    "F1/?   Show this help",
    "",
    "Press any key to close.",
]
# -------------------------------------------------

@final
class TetrisApp:
    """俄罗斯方块主应用程序类，负责窗口管理、事件循环和渲染。"""
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
            # 上下会有黑边，缩减高度
            new_w = init_w
            new_h = int(SCREEN_HEIGHT * scale_w)
        elif scale_h < scale_w:
            # 左右会有黑边，缩减宽度
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
        pygame.display.set_caption("Tetris Professional - macOS Lab")
        self._logical = None   # 逻辑表面，渲染时按比例缩放

    def _init_input(self) -> None:
        """设置按键重复参数。"""
        pygame.key.set_repeat(200, 50)   # 长按方向键时的重复延迟和间隔

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
            # 配置文件不存在或格式错误，保留当前默认值
            pass
        # 记录当前值作为影子值（之后比较变化时使用）
        self._initial_music_enabled = self.music_enabled
        self._initial_sfx_enabled = self.sfx_enabled
        # 注意 _initial_high_score 已在上面设置完毕

    def _save_config(self) -> None:
        """将音乐开关、音效开关和最高分写入配置文件（只在有变化时写入）。"""
        # 与影子值逐项比较，若无变化直接返回
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
            # 写入成功后更新影子值为当前值，避免下次保存时重复写
            self._initial_music_enabled = self.music_enabled
            self._initial_sfx_enabled = self.sfx_enabled
            self._initial_high_score = self.high_score
        except Exception:
            pass  # 静默失败，不影响游戏运行

    # --------------------------------------------

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
        # 影子值默认与当前默认值一致，随后 _load_config 会覆盖
        self._initial_music_enabled = True
        self._initial_sfx_enabled = True
        self._initial_high_score = 0
        self._game_over_sound_played = False
        self._music_paused_for_gamepause = False
        # HELP 相关
        self._help_active = False
        # 从配置文件覆盖上面默认值
        self._load_config()

    def _init_sidebar_style(self) -> None:
        """设置侧边栏背景色（灰蓝色调）。"""
        self.sidebar_bg = (40, 45, 55)

    def _init_icon(self) -> None:
        """设置窗口图标。"""
        # ---- 设置 Dock 栏图标 ----
        if os.path.isfile(LOGO_FILE):
            try:
                icon_surf = pygame.image.load(LOGO_FILE).convert_alpha()
                pygame.display.set_icon(icon_surf)
            except pygame.error:
                pass

    def _init_audio(self) -> None:
        """尽量加载背景音乐与删除行音效，若缺少文件则静默运行。
           设计思路：允许游戏在没有音频文件的环境下正常执行，
           不因文件缺失而抛出异常。
        """
        self.audio_enabled = False
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            # 背景音乐（循环播放）
            if os.path.isfile(BG_MUSIC_FILE):
                pygame.mixer.music.load(BG_MUSIC_FILE)

            # 消行音效
            if os.path.isfile(CLEAR_SOUND_FILE):
                self.sounds["clear"] = pygame.mixer.Sound(CLEAR_SOUND_FILE)

            # 游戏结束音效
            if os.path.isfile(GAME_OVER_SOUND_FILE):
                self.sounds["game_over"] = pygame.mixer.Sound(GAME_OVER_SOUND_FILE)

            # 只要存在任意音频资源就标记可用
            if os.path.isfile(BG_MUSIC_FILE) or self.sounds:
                self.audio_enabled = True

            # 仅当音乐开关打开时播放背景音乐
            if self.music_enabled and os.path.isfile(BG_MUSIC_FILE):
                pygame.mixer.music.play(-1)

        except Exception:
            # 任何初始化异常（如设备不支持）都静默关闭音频
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
        # 不再立即保存，退出时统一保存

    def _toggle_sfx(self) -> None:
        """切换音效的开关（S键）。"""
        if not self.audio_enabled:
            return
        self.sfx_enabled = not self.sfx_enabled
        # 不再立即保存，退出时统一保存

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
            # 限制最高分不超过 MAX_SCORE
            self.high_score = min(self.game.score, MAX_SCORE)

    # ---------- 新增统一锁定 + 更新方法 ----------
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

    # ---------- 新增重置游戏方法 ----------
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

    # ---------- 新增帮助切换方法 ----------
    def _toggle_help(self) -> None:
        """切换帮助界面的显示/隐藏。"""
        if self._help_active:
            self._help_active = False
            # 恢复下落定时器（仅当游戏未结束、未暂停时）
            if not self.game.game_over and not self.paused:
                self._update_speed()
        else:
            self._help_active = True
            # 停止下落定时器
            pygame.time.set_timer(self.fall_event, 0)
    # ---------------------------------------

    def run(self) -> None:
        """主循环：保持窗口尺寸、处理事件、渲染场景"""
        while True:
            self._enforce_min_size()
            self._process_events()
            self._render_game_scene()
            self.clock.tick(60)

    # ---------- 重构：事件处理（拆分） ----------

    def _process_events(self) -> None:
        """处理所有事件（按优先级和状态分发）"""
        # 游戏结束时（刚进入此帧）播放一次结束音效
        if self.game.game_over and not self._game_over_sound_played:
            self._play_sound("game_over")
            self._game_over_sound_played = True

        for event in pygame.event.get():
            # --- 全局高优先级事件（任何时候都能响应）---
            if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                self._toggle_music()
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_s:
                self._toggle_sfx()
                continue
            if event.type == pygame.QUIT:
                self._handle_quit()
                return  # 直接退出循环
            if event.type == pygame.VIDEORESIZE:
                self._handle_resize(event)
                continue

            # --- 帮助激活时，任意按键关闭帮助 ---
            if self._help_active:
                if event.type == pygame.KEYDOWN:
                    self._toggle_help()
                    continue
                # 其他事件忽略
                continue

            # --- 根据当前状态路由 ---
            if self.confirm_quit:
                self._handle_confirm_quit_event(event)
            elif self.game.game_over:
                self._handle_game_over_event(event)
            elif self.paused:
                # 暂停状态下只处理 P 键恢复 和 ESC 键进入退出确认
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_p:
                        self._toggle_pause()
                    elif event.key == pygame.K_ESCAPE:
                        self.confirm_quit = True
                # 忽略其他事件
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
        """处理游戏结束状态下的按键事件（支持回车重新开始和 ESC 退出游戏）。"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._restart_game()
            elif event.key == pygame.K_ESCAPE:
                self._handle_quit()

    def _handle_playing_event(self, event: pygame.event.Event) -> None:
        """处理正常游戏进行中的事件（包括 ESC 进入退出确认、P 暂停、下落定时器、方向键等）。"""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.confirm_quit = True
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            self._toggle_pause()
        elif event.type == self.fall_event:
            self._handle_fall_timer()
        elif event.type == pygame.KEYDOWN:
            # 检查 F1 和 ? 键
            key = event.key
            mods = pygame.key.get_mods()
            if key == pygame.K_F1:
                self._toggle_help()
            elif key == pygame.K_SLASH and (mods & pygame.KMOD_SHIFT):
                self._toggle_help()
            else:
                self._handle_movement_key(event.key)

    def _toggle_pause(self) -> None:
        """切换暂停状态（仅在游戏未结束时有效）。"""
        if self.game.game_over:
            return
        self.paused = not self.paused
        if self.paused:
            # 暂停：停止自动下落，暂停背景音乐
            pygame.time.set_timer(self.fall_event, 0)
            if self.music_enabled and pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
                self._music_paused_for_gamepause = True
        else:
            self._update_speed()
            # 恢复时，若音乐曾因暂停而被暂停，则恢复
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
        """处理下落定时器事件：尝试下落一格，若无法下落则锁定并进行消行检测。"""
        if not self.game.move(0, 1):
            self._lock_and_update()

    def _handle_movement_key(self, key: int) -> None:
        """处理方向键和空格键（硬降）。"""
        if key == pygame.K_UP:
            self.game.rotate()
        elif key == pygame.K_LEFT:
            self.game.move(-1, 0)
        elif key == pygame.K_RIGHT:
            self.game.move(1, 0)
        elif key == pygame.K_DOWN:
            # 尝试下落一格；若无法下落立即锁定
            if not self.game.move(0, 1):
                self._lock_and_update()
        elif key == pygame.K_SPACE:
            # 硬下降到底然后锁定
            while self.game.move(0, 1):
                pass
            self._lock_and_update()

    # ---------- 渲染方法（重构） ----------

    def _render_game_scene(self) -> None:
        """极致渲染：主场 + 左侧面板 + 侧边栏 + 弹窗

        根据窗口大小动态缩放逻辑表面，确保文字在高分屏下清晰。
        绘制顺序由各子方法确保。
        """
        scale = min(
            self.window_width / SCREEN_WIDTH,
            self.window_height / SCREEN_HEIGHT,
        )
        logical_w = int(SCREEN_WIDTH * scale)
        logical_h = int(SCREEN_HEIGHT * scale)
        # 如果逻辑表面尺寸改变，则重新创建（避免反复生成新表面）
        if (self._logical is None
                or self._logical.get_width() != logical_w
                or self._logical.get_height() != logical_h):
            self._logical = pygame.Surface((logical_w, logical_h))
        ls = self._logical

        # 字体懒加载缓存（仅在 scale 变化时重新创建）
        if (self._font_big is None
                or self._font_small is None
                or self._help_font is None
                or abs(scale - self._current_scale) > 1e-9):
            self._current_scale = scale
            font_size = max(10, int(32 * scale))
            small_font_size = max(8, int(20 * scale))
            help_font_size = max(8, int(20 * scale))
            # 使用统一字体的 .ttf 文件
            self._font_big = pygame.font.Font(FONT_FILE, font_size)
            self._font_small = pygame.font.Font(FONT_FILE, small_font_size)
            self._help_font = pygame.font.Font(HELP_FONT_FILE, help_font_size)

        # 计算缩放后的尺寸
        bs = int(BLOCK_SIZE * scale)               # 缩放后的方块大小
        left_width_px = int(LEFT_WIDTH * scale)    # 左侧面板像素宽
        right_width_px = int(RIGHT_WIDTH * scale)  # 右侧面板像素宽

        ds = ls
        # 用棋盘网格颜色填充底漆，避免任何未覆盖区域暴露黑色
        ds.fill(COLORS["GRID_LINE"])

        board_left = left_width_px
        board_w = GRID_WIDTH * bs
        board_h = GRID_HEIGHT * bs
        sidebar_left = board_left + board_w

        # 游戏区域背景（覆盖至侧边栏左边缘）
        game_area_width = sidebar_left - board_left
        pygame.draw.rect(ds, COLORS["GRID_LINE"],
                         (board_left, 0, game_area_width, logical_h))

        border_color = (80, 85, 95)

        # A. 绘制主棋盘、当前块、边框
        self._draw_board(ls, bs, board_left, board_w, board_h, border_color)

        # B. 绘制左侧面板
        self._draw_left_panel(ls, scale, left_width_px, logical_h, self._font_big, self._font_small)

        # C. 绘制右侧侧边栏
        self._draw_right_panel(ls, scale, board_h,
                               sidebar_left, right_width_px, border_color,
                               self._font_big, self._font_small, logical_h)

        # D. 绘制覆盖弹窗（传入棋盘区域坐标以定位遮罩）
        self._draw_overlays(ls, scale, logical_w, logical_h,
                            self._font_big, self._font_small, self._help_font,
                            board_left, board_w, board_h)

        # 4. 将逻辑表面显示到物理窗口（居中，侧边栏背景色填充）
        x_off = (self.window_width - logical_w) // 2
        y_off = (self.window_height - logical_h) // 2

        self.screen.fill(self.sidebar_bg)
        self.screen.blit(self._logical, (x_off, y_off))

        # ---- 动态鼠标可见性（根据是否在棋盘区域） ----
        mx, my = pygame.mouse.get_pos()
        board_phys_left = x_off + board_left
        board_phys_top = y_off
        board_phys_right = board_phys_left + board_w
        board_phys_bottom = board_phys_top + board_h
        in_board = (board_phys_left <= mx <= board_phys_right and
                    board_phys_top <= my <= board_phys_bottom)

        if in_board:
            if pygame.mouse.get_visible():
                pygame.mouse.set_visible(False)
        else:
            if not pygame.mouse.get_visible():
                pygame.mouse.set_visible(True)
        # ------------------------------------------------

        pygame.display.flip()

    def _draw_board(self, ls: pygame.Surface, bs: int,
                    board_left: int, board_w: int, board_h: int,
                    border_color: tuple[int, int, int]) -> None:
        """绘制 10×20 棋盘、当前操控块、以及上下左三边边框。"""
        ds = ls

        # A. 绘制主棋盘
        for r in range(GRID_HEIGHT):
            for c in range(GRID_WIDTH):
                color: tuple[int, int, int] = (
                    self.game.grid[r][c] or COLORS["GRID_LINE"]
                )
                rect = (board_left + c * bs, r * bs, bs - 1, bs - 1)
                pygame.draw.rect(ds, color, rect)

        # B. 绘制当前操控块 (仅在游戏进行时)
        if not self.game.game_over:
            for dx, dy in self.game.current_shape:
                rect = (
                    board_left + (self.game.x + dx) * bs,
                    (self.game.y + dy) * bs,
                    bs - 1,
                    bs - 1,
                )
                pygame.draw.rect(ds, COLORS[self.game.current_type], rect)

        # C. 游戏区域外框（上、左、下边）
        # 上边
        pygame.draw.line(ds, border_color, (board_left, 0),
                         (board_left + board_w, 0), 2)
        # 左边
        pygame.draw.line(ds, border_color, (board_left, 0),
                         (board_left, board_h), 2)
        # 下边
        pygame.draw.line(ds, border_color, (board_left, board_h),
                         (board_left + board_w, board_h), 2)

    def _draw_left_panel(self, ls: pygame.Surface, scale: float,
                         left_width_px: int, logical_h: int,
                         font_big: pygame.font.Font,
                         font_small: pygame.font.Font) -> None:
        """绘制左侧面板（游戏名称、音频状态）。"""
        if left_width_px <= 0:
            return
        ds = ls
        left_panel_rect = pygame.Rect(0, 0, left_width_px, logical_h)
        pygame.draw.rect(ds, self.sidebar_bg, left_panel_rect)

        left_padding = int(10 * scale)
        left_content_x = left_padding
        left_content_width = left_width_px - 2 * left_padding

        # 游戏名称（居中）
        title_str = "Tetris"
        title_surf = font_big.render(title_str, True, (255, 255, 255))
        title_x = left_content_x + (left_content_width - title_surf.get_width()) // 2
        ds.blit(title_surf, (title_x, int(20 * scale)))

        # 分隔线（标题下方）
        sep_line_y = int(70 * scale)
        pygame.draw.line(
            ds,
            (60, 60, 70),
            (left_content_x, sep_line_y),
            (left_content_x + left_content_width, sep_line_y),
            1,
        )

        # ---- 音乐 / 音效状态（从底部向上排列） ----
        music_str = "Music: " + ("ON" if self.music_enabled else "OFF")
        music_surf = font_small.render(music_str, True,
                                       (0, 255, 0) if self.music_enabled else (200, 50, 50))
        sfx_str = "SFX:    " + ("ON" if self.sfx_enabled else "OFF")
        sfx_surf = font_small.render(sfx_str, True,
                                     (0, 255, 0) if self.sfx_enabled else (200, 50, 50))

        # 底部留白 60*scale，然后向上依次放置音效行和音乐行
        bottom_margin = int(60 * scale)
        gap_between = int(10 * scale)

        sfx_y = logical_h - bottom_margin - sfx_surf.get_height()
        music_y = sfx_y - music_surf.get_height() - gap_between

        ds.blit(music_surf, (left_content_x, music_y))
        ds.blit(sfx_surf, (left_content_x, sfx_y))

    def _draw_right_panel(self, ls: pygame.Surface, scale: float,
                          board_h: int,
                          sidebar_left: int, right_width_px: int,
                          border_color: tuple[int, int, int],
                          font_big: pygame.font.Font,
                          font_small: pygame.font.Font,
                          logical_h: int) -> None:
        """绘制右侧侧边栏（LV、SCORE、预览、底部统计）。"""
        ds = ls
        logical_w = ls.get_width()
        # 面板背景从 sidebar_left 扩充到逻辑表面右边界
        panel_rect = pygame.Rect(sidebar_left, 0,
                                 logical_w - sidebar_left, logical_h)
        pygame.draw.rect(ds, self.sidebar_bg, panel_rect)

        content_padding = int(20 * scale)
        sidebar_content_left = sidebar_left + content_padding
        sidebar_content_right = sidebar_left + right_width_px - content_padding
        sidebar_content_width = sidebar_content_right - sidebar_content_left

        # LV 与 SCORE 标头
        lv_label = font_small.render("LV", True, (150, 150, 160))
        score_label = font_small.render("SCORE", True, (150, 150, 160))
        ds.blit(lv_label, (sidebar_content_left, 20))
        ds.blit(
            score_label,
            (sidebar_content_right - score_label.get_width(), 20),
        )

        lv_val = font_big.render(f"{self.game.level}", True, (255, 255, 255))
        score_val = font_big.render(
            f"{self.game.score:6d}", True, COLORS["SCORE_GOLD"]
        )
        ds.blit(lv_val, (sidebar_content_left, 45))
        ds.blit(
            score_val,
            (sidebar_content_right - score_val.get_width(), 45),
        )

        sep_y1 = int(85 * scale)
        pygame.draw.line(
            ds,
            (60, 60, 70),
            (sidebar_content_left, sep_y1),
            (sidebar_content_right, sep_y1),
            1,
        )

        # 预览框（下一个方块）
        bs = int(BLOCK_SIZE * scale)
        preview_size = 4 * bs
        preview_x = sidebar_content_left + (sidebar_content_width - preview_size) // 2
        preview_y = int(130 * scale)

        preview_rect_inner = pygame.Rect(preview_x, preview_y, preview_size, preview_size)
        pygame.draw.rect(ds, self.sidebar_bg, preview_rect_inner)

        next_shape: list[tuple[int, int]] = SHAPES_DATA[self.game.next_type]
        xs: list[int] = [dx for dx, _dy in next_shape]
        ys: list[int] = [dy for _dx, dy in next_shape]
        min_dx = min(xs)
        max_dx = max(xs)
        min_dy = min(ys)
        max_dy = max(ys)
        shape_width = max_dx - min_dx + 1
        shape_height = max_dy - min_dy + 1
        offset_x = (preview_size - shape_width * bs) // 2
        offset_y = (preview_size - shape_height * bs) // 2
        for dx, dy in next_shape:
            px = preview_x + offset_x + (dx - min_dx) * bs
            py = preview_y + offset_y + (dy - min_dy) * bs
            pygame.draw.rect(
                ds,
                COLORS[self.game.next_type],
                (px, py, bs - 1, bs - 1),
            )

        # 底部统计信息：Lines, High, Time
        elapsed_sec = (pygame.time.get_ticks() - self.game_start_ticks) // 1000
        mins = elapsed_sec // 60
        secs = elapsed_sec % 60
        time_str = f"{mins:02d}:{secs:02d}"

        bottom_lines = [
            ("Lines", str(self.game.total_lines)),
            ("High", str(self.high_score)),
            ("Time", time_str),
        ]

        right_bottom_margin = int(60 * scale)
        right_gap = int(10 * scale)

        temp_label = font_small.render("Lines: ", True, (200, 200, 200))
        temp_val = font_small.render("000", True, (255, 255, 255))
        row_height = max(temp_label.get_height(), temp_val.get_height())

        time_y = logical_h - right_bottom_margin - row_height
        high_y = time_y - row_height - right_gap
        lines_y = high_y - row_height - right_gap

        for i, (label_text, value_text) in enumerate(bottom_lines):
            if i == 0:
                y = lines_y
            elif i == 1:
                y = high_y
            else:
                y = time_y
            label_surf = font_small.render(label_text + ": ", True, (200, 200, 200))
            val_surf = font_small.render(value_text, True, (255, 255, 255))
            ds.blit(label_surf, (sidebar_content_left, y))
            ds.blit(
                val_surf,
                (sidebar_content_left + label_surf.get_width(), y),
            )

        # 画右边分隔线（在侧边栏左边缘）
        pygame.draw.line(
            ds, border_color,
            (sidebar_left, 0),
            (sidebar_left, board_h),
            2,
        )

    # ---------- 新增通用覆盖层绘制方法（支持左对齐选项） ----------
    def _draw_overlay_text(self, surface: pygame.Surface,
                           logical_w: int, logical_h: int,
                           font_big: pygame.font.Font,
                           font_small: pygame.font.Font,
                           scale: float,
                           title: str,
                           title_color: tuple[int, int, int],
                           lines: list[tuple[str, tuple[int, int, int]]],
                           alpha: int = 180,
                           align_left: bool = False,
                           overlay_rect: pygame.Rect | None = None) -> None:
        """绘制半透明覆盖层以及居中的标题和左对齐/居中的说明行。

        align_left: 如果为 True，则 lines 居左显示（与棋盘左边缘对齐）；否则居中。
        overlay_rect: 如果提供，遮罩只覆盖该矩形区域（棋盘区域），否则全屏。
        """
        if overlay_rect:
            # 局部遮罩：使用带 alpha 通道的表面，只填充指定矩形
            overlay = pygame.Surface((logical_w, logical_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha), overlay_rect)
        else:
            # 全屏遮罩（原有逻辑）
            overlay = pygame.Surface((logical_w, logical_h))
            overlay.set_alpha(alpha)
            overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))

        gap = int(15 * scale)
        title_surf = font_big.render(title, True, title_color)
        line_surfs = [font_small.render(text, True, color) for text, color in lines]

        total_h = (title_surf.get_height()
                   + sum(s.get_height() for s in line_surfs)
                   + len(lines) * gap)
        start_y = (logical_h - total_h) // 2

        # 标题始终居中
        tx = (logical_w - title_surf.get_width()) // 2
        surface.blit(title_surf, (tx, start_y))
        y = start_y + title_surf.get_height() + gap

        # 左对齐的缩进：棋盘左边缘
        # board_left = LEFT_WIDTH * scale (缩放后)
        if align_left:
            indent = int(LEFT_WIDTH * scale)
        else:
            indent = 0

        for line_surf in line_surfs:
            if align_left:
                lx = indent
            else:
                lx = (logical_w - line_surf.get_width()) // 2
            surface.blit(line_surf, (lx, y))
            y += line_surf.get_height() + gap

    # ---------- 新增帮助覆盖层绘制方法 ----------
    def _draw_help_overlay(self, surface: pygame.Surface,
                           logical_w: int, logical_h: int,
                           help_font: pygame.font.Font,
                           scale: float) -> None:
        """绘制半透明背景，居中显示帮助文字。

        标题（第一行）居中并使用金色，其余行左对齐并带有缩进（与棋盘左边缘对齐）。
        """
        overlay = pygame.Surface((logical_w, logical_h))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))

        # 第一行为标题
        title_line = HELP_LINES[0] if HELP_LINES else ""
        body_lines = HELP_LINES[1:] if len(HELP_LINES) > 1 else []

        # 标题颜色使用金色，其余行白色
        title_color = (255, 200, 0)   # 金色
        body_color = (255, 255, 255)

        # 渲染标题（居中）
        title_surf = help_font.render(title_line, True, title_color)
        tx = (logical_w - title_surf.get_width()) // 2
        # 计算垂直位置
        gap = int(12 * scale)
        # 先计算所有行总高度（标题 + 正文）
        body_surfaces = [help_font.render(line, True, body_color) for line in body_lines]
        total_body_h = sum(s.get_height() for s in body_surfaces) + \
                       (len(body_surfaces) - 1) * gap
        total_h = title_surf.get_height() + gap + total_body_h
        start_y = (logical_h - total_h) // 2

        surface.blit(title_surf, (tx, start_y))
        y = start_y + title_surf.get_height() + gap

        # 正文左对齐，缩进为棋盘左边缘
        indent = int(LEFT_WIDTH * scale)
        for body_surf in body_surfaces:
            surface.blit(body_surf, (indent, y))
            y += body_surf.get_height() + gap
    # --------------------------------------------

    # ---------- 重构后的覆盖层绘制方法 ----------
    def _draw_overlays(self, ls: pygame.Surface, scale: float,
                       logical_w: int, logical_h: int,
                       font_big: pygame.font.Font,
                       font_small: pygame.font.Font,
                       help_font: pygame.font.Font,
                       board_left: int, board_w: int, board_h: int) -> None:
        """绘制 Game Over / Pause / Confirm Quit / Help 弹窗。"""
        ds = ls

        # ---- 帮助覆盖层优先级最高 ----
        if self._help_active:
            self._draw_help_overlay(ds, logical_w, logical_h,
                                    help_font, scale)
            return

        # 棋盘区域矩形（遮罩只覆盖此处）
        board_rect = pygame.Rect(board_left, 0, board_w, board_h)

        # F. Game Over 弹窗（多行文字居中）
        if self.game.game_over:
            self._draw_overlay_text(
                ds, logical_w, logical_h, font_big, font_small, scale,
                "GAME OVER", (255, 0, 0),
                [
                    ("Press RETURN to restart", (255, 255, 255)),
                    ("Press ESC to quit", (255, 255, 255)),
                ],
                alpha=180,
                align_left=False,
                overlay_rect=board_rect,
            )

        # G. Pause 弹窗（单行文字居中）
        elif self.paused:
            self._draw_overlay_text(
                ds, logical_w, logical_h, font_big, font_small, scale,
                "PAUSED", (255, 255, 0),
                [("Press P to resume", (255, 255, 255))],
                alpha=180,
                align_left=False,   # 只有一行，居中显示
                overlay_rect=board_rect,
            )

        # H. Confirm Quit 弹窗（多行，左对齐）
        if self.confirm_quit:
            self._draw_overlay_text(
                ds, logical_w, logical_h, font_big, font_small, scale,
                "QUIT ?", (255, 100, 100),
                [
                    ("Press ESC to confirm", (255, 255, 255)),
                    ("Press R to restart", (255, 255, 255)),
                    ("Any other key to cancel", (255, 255, 255)),
                ],
                alpha=200,
                align_left=True,    # 多行，左对齐
                overlay_rect=board_rect,
            )
