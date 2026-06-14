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

import pygame
import platformdirs

from engine import TetrisEngine, GRID_WIDTH, GRID_HEIGHT, COLORS, SHAPES_DATA

# 方块大小（逻辑像素）
BLOCK_SIZE = 30

# 左右两侧边栏宽度（逻辑像素）
LEFT_WIDTH = 160
RIGHT_WIDTH = 200

# 逻辑分辨率（基于 BLOCK_SIZE=30）
SCREEN_WIDTH = LEFT_WIDTH + GRID_WIDTH * BLOCK_SIZE + RIGHT_WIDTH
SCREEN_HEIGHT = GRID_HEIGHT * BLOCK_SIZE

HIGH_SCORE_FILE = "highscore.txt"

# 最小窗口尺寸（小于此值会被强制拉伸到该最小尺寸）
# 增加50像素避免黑边过窄
MIN_WINDOW_WIDTH = max(400, LEFT_WIDTH + GRID_WIDTH * BLOCK_SIZE + RIGHT_WIDTH + 50)
MIN_WINDOW_HEIGHT = 400

# ---- 音频文件路径 ----
BG_MUSIC_FILE = "assets/bg_music.mp3"
CLEAR_SOUND_FILE = "assets/clear.wav"
GAME_OVER_SOUND_FILE = "assets/game_over.mp3"
# -----------------------

# ---- 应用图标路径 ----
LOGO_FILE = "assets/logo.png"
# -----------------------


def _highscore_file() -> str:
    """返回符合 XDG 数据目录的高分记录文件路径，并确保目录存在。"""
    data_dir = platformdirs.user_data_dir("mytetris")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "highscore.txt")


def load_high_score() -> int:
    """从文件读取最高分，若文件不存在或格式错误则返回 0。"""
    try:
        with open(_highscore_file(), "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def save_high_score(value: int) -> None:
    """将最高分写入文件。"""
    with open(_highscore_file(), "w") as f:
        f.write(str(value))


@final
class TetrisApp:
    """俄罗斯方块主应用程序类，负责窗口管理、事件循环和渲染。"""
    screen: pygame.Surface
    font: pygame.font.Font
    small_font: pygame.font.Font
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
        pygame.mouse.set_visible(False)

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
        self.font = pygame.font.SysFont("Arial Black", 32)
        self.small_font = pygame.font.SysFont("Arial Black", 20)
        self._logical = None   # 逻辑表面，渲染时按比例缩放

    def _init_input(self) -> None:
        """设置按键重复参数。"""
        pygame.key.set_repeat(200, 50)   # 长按方向键时的重复延迟和间隔

    def _init_game_state(self) -> None:
        """初始化游戏引擎、定时器、等级、分数、暂停等状态。"""
        self.game = TetrisEngine()
        self.fall_event = pygame.USEREVENT + 1
        self.current_level = 1
        self._update_speed()
        self.clock = pygame.time.Clock()
        self.paused = False
        self.confirm_quit = False
        self.high_score = load_high_score()
        self.game_start_ticks = pygame.time.get_ticks()
        self.music_enabled = True
        self.sfx_enabled = True
        self._game_over_sound_played = False
        self._music_paused_for_gamepause = False

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

            if os.path.isfile(BG_MUSIC_FILE):
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
        """实时更新最高分（内存中）"""
        if self.game.score > self.high_score:
            self.high_score = self.game.score

    def run(self) -> None:
        """主循环：保持窗口尺寸、处理事件、渲染场景"""
        while True:
            self._enforce_min_size()
            self._process_events()
            self._render_game_scene()
            self.clock.tick(60)

    def _process_events(self) -> None:
        """处理所有事件（瞬时/持续）

           设计说明：
           - 使用独立的事件处理，避免在弹窗状态下误触游戏操作。
           - M / S 在暂停和游戏结束状态下也可切换音频。
           - 暂停和确认退出状态会覆盖其他按键。
        """
        # 游戏结束时（刚进入此帧）播放一次结束音效
        if self.game.game_over and not self._game_over_sound_played:
            self._play_sound("game_over")
            self._game_over_sound_played = True

        for event in pygame.event.get():
            # --- 音频开关（高优先级，任何时候都能响应）---
            if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                self._toggle_music()
                continue

            if event.type == pygame.KEYDOWN and event.key == pygame.K_s:
                self._toggle_sfx()
                continue

            # --- 退出 ---
            if event.type == pygame.QUIT:
                save_high_score(self.high_score)
                pygame.mouse.set_visible(True)
                pygame.quit()
                sys.exit()

            # --- 窗口大小改变 ---
            if event.type == pygame.VIDEORESIZE:
                new_w = max(event.w, MIN_WINDOW_WIDTH)
                new_h = max(event.h, MIN_WINDOW_HEIGHT)
                self.window_width = new_w
                self.window_height = new_h
                self.screen = pygame.display.set_mode(
                    (new_w, new_h), pygame.RESIZABLE
                )
                continue

            # --- 退出确认弹窗（覆盖其他所有按键）---
            if self.confirm_quit:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        save_high_score(self.high_score)
                        pygame.mouse.set_visible(True)
                        pygame.quit()
                        sys.exit()
                    else:
                        self.confirm_quit = False
                continue

            # --- 首次按下 ESC 进入退出确认 ---
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.confirm_quit = True
                continue

            # --- 暂停 / 恢复（使用 P 键）---
            if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                if not self.game.game_over:
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
                continue

            # --- 游戏结束时的重置处理 ---
            if self.game.game_over:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    self.game.reset()
                    self.current_level = 1
                    self._update_speed()
                    self.paused = False
                    self.game_start_ticks = pygame.time.get_ticks()
                    self._game_over_sound_played = False
                    self._music_paused_for_gamepause = False
                continue

            # --- 暂停状态下忽略其他操作 ---
            if self.paused:
                continue

            # --- 下落定时器 ---
            if event.type == self.fall_event:
                if not self.game.move(0, 1):
                    prev_lines = self.game.total_lines
                    self.game.lock_and_clear_lines()
                    if self.game.total_lines > prev_lines:
                        self._play_sound("clear")
                    self._update_high_score()
                    self._check_level_upgrade()

            # --- 方向键操作 & 硬降（空格键） ---
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.game.rotate()
                elif event.key == pygame.K_LEFT:
                    self.game.move(-1, 0)
                elif event.key == pygame.K_RIGHT:
                    self.game.move(1, 0)
                elif event.key == pygame.K_DOWN:
                    self.game.move(0, 1)
                elif event.key == pygame.K_SPACE:
                    # 硬降：方块直接落到底部
                    self.game.hard_drop()
                    self._update_high_score()
                    self._check_level_upgrade()

    def _render_game_scene(self) -> None:
        """极致渲染：主场 + 左侧面板 + 美观侧边栏 + Game Over / Pause / Confirm Quit 弹窗

        根据窗口大小动态缩放逻辑表面，确保文字在高分屏下清晰。

        绘制顺序：
        1. 填充背景（GRID_LINE 色，防止取整露出纯黑）
        2. 绘制游戏区域背景（覆盖整个左‑右边界之间的高度）
        3. 绘制主棋盘（包括网格和已锁定方块）
        4. 绘制当前操控块
        5. 绘制游戏区域外框（上、左、下三边，右边稍后画）
        6. 绘制左侧面板（游戏名称、版本、音频状态）
        7. 绘制右侧侧边栏，并拉伸至逻辑表面右边界（消除可能出现的黑色缝隙）
        8. 在右侧面板左边缘绘制右边分隔线
        9. 根据状态覆盖弹窗（Game Over / Pause / Confirm Quit）
        10. 将逻辑表面显示到物理窗口（侧边栏背景色填充）
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

        # 计算缩放后的尺寸
        bs = int(BLOCK_SIZE * scale)               # 缩放后的方块大小
        left_width_px = int(LEFT_WIDTH * scale)    # 左侧面板像素宽
        right_width_px = int(RIGHT_WIDTH * scale)  # 右侧面板像素宽
        font_size = max(10, int(32 * scale))
        small_font_size = max(8, int(20 * scale))
        font_big = pygame.font.SysFont("Arial Black", font_size)
        font_small = pygame.font.SysFont("Arial Black", small_font_size)

        # 开始绘制
        ds = ls
        # 用棋盘网格颜色填充底漆，避免任何未覆盖区域暴露黑色
        ds.fill(COLORS["GRID_LINE"])

        # 常量
        board_left = left_width_px
        board_w = GRID_WIDTH * bs
        board_h = GRID_HEIGHT * bs
        sidebar_left = board_left + board_w     # 右侧面板左边缘

        # ---- 游戏区域背景（覆盖至逻辑表面右边界之前） ----
        game_area_width = sidebar_left - board_left
        pygame.draw.rect(ds, COLORS["GRID_LINE"],
                         (board_left, 0, game_area_width, logical_h))

        # A. 绘制主棋盘（10×20 网格）
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

        # C. 游戏区域外框（上、左、下边，右边稍后画）
        border_color = (80, 85, 95)
        # 上边
        pygame.draw.line(ds, border_color, (board_left, 0),
                         (board_left + board_w, 0), 2)
        # 左边
        pygame.draw.line(ds, border_color, (board_left, 0),
                         (board_left, board_h), 2)
        # 下边（恢复，消除方块浮空感）
        pygame.draw.line(ds, border_color, (board_left, board_h),
                         (board_left + board_w, board_h), 2)

        # D. 左侧面板（游戏名称、版本、音频状态）
        if left_width_px > 0:
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

        # E. 绘制右侧侧边栏 -------------------------------------------------
        # 面板背景从 sidebar_left 扩充到逻辑表面右边界（消除取整缝隙）
        panel_rect = pygame.Rect(sidebar_left, 0,
                                 logical_w - sidebar_left, logical_h)
        pygame.draw.rect(ds, self.sidebar_bg, panel_rect)

        content_padding = int(20 * scale)
        sidebar_content_left = sidebar_left + content_padding
        # 保持右侧内容区域右端点基于预期宽度（多余部分留给背景）
        sidebar_content_right = sidebar_left + right_width_px - content_padding
        sidebar_content_width = sidebar_content_right - sidebar_content_left

        # ---- 侧边栏内容 ----
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

        # F. 绘制 Game Over 弹窗
        if self.game.game_over:
            overlay = pygame.Surface((logical_w, logical_h))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            ds.blit(overlay, (0, 0))

            go_text = font_big.render("GAME OVER", True, (255, 0, 0))
            restart_text = font_small.render(
                "Press RETURN to restart", True, (255, 255, 255)
            )
            ds.blit(
                go_text,
                (logical_w // 2 - go_text.get_width() // 2, logical_h // 2 - 40),
            )
            ds.blit(
                restart_text,
                (
                    logical_w // 2 - restart_text.get_width() // 2,
                    logical_h // 2 + 20,
                ),
            )

        # G. 绘制暂停弹窗
        elif self.paused:
            overlay = pygame.Surface((logical_w, logical_h))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            ds.blit(overlay, (0, 0))

            paused_text = font_big.render("PAUSED", True, (255, 255, 0))
            resume_text = font_small.render(
                "Press P to resume", True, (255, 255, 255)
            )
            ds.blit(
                paused_text,
                (logical_w // 2 - paused_text.get_width() // 2, logical_h // 2 - 40),
            )
            ds.blit(
                resume_text,
                (
                    logical_w // 2 - resume_text.get_width() // 2,
                    logical_h // 2 + 20,
                ),
            )

        # H. 确认退出弹窗
        if self.confirm_quit:
            overlay = pygame.Surface((logical_w, logical_h))
            overlay.set_alpha(200)
            overlay.fill((0, 0, 0))
            ds.blit(overlay, (0, 0))

            quit_title = font_big.render("QUIT ?", True, (255, 100, 100))
            line_esc = font_small.render(
                "Press ESC to confirm", True, (255, 255, 255)
            )
            line_cancel = font_small.render(
                "Any other key to cancel", True, (255, 255, 255)
            )

            title_h = quit_title.get_height()
            small_h = line_esc.get_height()
            gap = int(15 * scale)

            total_h = title_h + gap + small_h + gap + small_h
            start_y = (logical_h - total_h) // 2

            ds.blit(
                quit_title,
                (logical_w // 2 - quit_title.get_width() // 2, start_y),
            )
            ds.blit(
                line_esc,
                (logical_w // 2 - line_esc.get_width() // 2, start_y + title_h + gap),
            )
            ds.blit(
                line_cancel,
                (logical_w // 2 - line_cancel.get_width() // 2,
                 start_y + title_h + gap + small_h + gap),
            )

        # 4. 将逻辑表面显示到物理窗口（居中，侧边栏背景色填充）
        x_off = (self.window_width - logical_w) // 2
        y_off = (self.window_height - logical_h) // 2

        self.screen.fill(self.sidebar_bg)
        self.screen.blit(self._logical, (x_off, y_off))

        pygame.display.flip()
