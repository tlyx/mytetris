from typing import final
import os
import sys

import pygame
import platformdirs

from engine import TetrisEngine, BLOCK_SIZE, GRID_WIDTH, GRID_HEIGHT, COLORS, SHAPES_DATA

SIDEBAR_WIDTH = 200
SCREEN_WIDTH = GRID_WIDTH * BLOCK_SIZE + SIDEBAR_WIDTH
SCREEN_HEIGHT = GRID_HEIGHT * BLOCK_SIZE

HIGH_SCORE_FILE = "highscore.txt"

# 版本号
__version__ = "0.6.0"

# 最小窗口尺寸（小于此值会被强制拉伸到该最小尺寸）
MIN_WINDOW_WIDTH = 400
MIN_WINDOW_HEIGHT = 400


def _highscore_file() -> str:
    """返回符合 XDG 数据目录的高分记录文件路径，并确保目录存在。"""
    data_dir = platformdirs.user_data_dir("mytetris")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "highscore.txt")


def load_high_score() -> int:
    try:
        with open(_highscore_file(), "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def save_high_score(value: int) -> None:
    with open(_highscore_file(), "w") as f:
        f.write(str(value))


@final
class TetrisApp:
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
    _logical: pygame.Surface | None  # 根据窗口大小动态创建的绘制表面

    def __init__(self) -> None:
        pygame.init()
        # 使用 RESIZABLE 标志允许用户改变窗口大小
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE
        )
        pygame.display.set_caption("Tetris Professional - macOS Lab")
        # 原始字体尺寸（实际缩放时动态创建，此处仅用于类型提示）
        self.font = pygame.font.SysFont("Arial Black", 32)
        self.small_font = pygame.font.SysFont("Arial Black", 20)
        # 启用按键重复（延迟 200 ms，间隔 50 ms）
        pygame.key.set_repeat(200, 50)

        self.game = TetrisEngine()
        self.fall_event = pygame.USEREVENT + 1
        self.current_level = 1
        self._update_speed()
        self.clock = pygame.time.Clock()
        self.paused = False
        self.confirm_quit = False
        self.high_score = load_high_score()
        self.game_start_ticks = pygame.time.get_ticks()
        self.sidebar_bg = (20, 22, 28)

        # 保存当前窗口实际尺寸，用于缩放
        self.window_width = SCREEN_WIDTH
        self.window_height = SCREEN_HEIGHT
        self._logical = None  # 延迟创建

        # 隐藏鼠标指针，避免遮挡游戏画面
        pygame.mouse.set_visible(False)

    def _update_speed(self) -> None:
        """根据等级计算下落速度"""
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
        while True:
            self._process_events()
            self._render_game_scene()
            self.clock.tick(60)

    def _process_events(self) -> None:
        """处理所有事件（瞬时/持续）"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_high_score(self.high_score)
                pygame.mouse.set_visible(True)   # 退出前恢复鼠标
                pygame.quit()
                sys.exit()

            # 窗口大小改变事件
            if event.type == pygame.VIDEORESIZE:
                new_w = max(event.w, MIN_WINDOW_WIDTH)
                new_h = max(event.h, MIN_WINDOW_HEIGHT)
                # 避免无限触发事件：只有当尺寸真正改变时才更新
                if (new_w, new_h) != (self.window_width, self.window_height):
                    self.window_width = new_w
                    self.window_height = new_h
                    self.screen = pygame.display.set_mode(
                        (new_w, new_h), pygame.RESIZABLE
                    )
                continue

            # 确认退出状态优先处理
            if self.confirm_quit:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        save_high_score(self.high_score)
                        pygame.mouse.set_visible(True)   # 退出前恢复鼠标
                        pygame.quit()
                        sys.exit()
                    else:
                        self.confirm_quit = False
                continue

            # 按下 ESC 触发退出确认
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.confirm_quit = True
                continue

            # 暂停切换，使用空格键（仅在非 Game Over 时有效）
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                if not self.game.game_over:
                    self.paused = not self.paused
                    if self.paused:
                        pygame.time.set_timer(self.fall_event, 0)
                    else:
                        self._update_speed()
                continue  # 切换后不做其他处理

            # Game Over 状态只响应 Return 键重开
            if self.game.game_over:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    self.game.reset()
                    self.current_level = 1
                    self._update_speed()
                    self.paused = False
                    # 重置开始时间
                    self.game_start_ticks = pygame.time.get_ticks()
                continue

            # 暂停状态下忽略除暂停键外的其他游戏事件
            if self.paused:
                continue

            if event.type == self.fall_event:
                if not self.game.move(0, 1):
                    self.game.lock_and_clear_lines()
                    self._update_high_score()
                    # 检查是否需要更新速度
                    self._check_level_upgrade()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.game.rotate()
                elif event.key == pygame.K_LEFT:
                    self.game.move(-1, 0)
                elif event.key == pygame.K_RIGHT:
                    self.game.move(1, 0)
                elif event.key == pygame.K_DOWN:
                    self.game.move(0, 1)

    def _render_game_scene(self) -> None:
        """极致渲染：主场 + 美观侧边栏 + Game Over / Pause / Confirm Quit 弹窗

        根据窗口大小动态缩放逻辑表面，确保文字在高分屏下清晰。
        """
        # 1. 计算缩放比例并创建对应的逻辑表面
        scale = min(
            self.window_width / SCREEN_WIDTH,
            self.window_height / SCREEN_HEIGHT,
        )
        logical_w = int(SCREEN_WIDTH * scale)
        logical_h = int(SCREEN_HEIGHT * scale)
        # 只有当尺寸变化时才重新创建表面（避免频繁创建）
        if (self._logical is None
                or self._logical.get_width() != logical_w
                or self._logical.get_height() != logical_h):
            self._logical = pygame.Surface((logical_w, logical_h))
        ls = self._logical

        # 2. 计算缩放后的块大小与字体大小
        bs = int(BLOCK_SIZE * scale)                   # 每个格子像素宽度
        sb_width = int(SIDEBAR_WIDTH * scale)          # 侧边栏宽度
        font_size = max(10, int(32 * scale))
        small_font_size = max(8, int(20 * scale))
        # 临时创建字体（每次渲染会新建，但开销很小）
        font_big = pygame.font.SysFont("Arial Black", font_size)
        font_small = pygame.font.SysFont("Arial Black", small_font_size)

        # 3. 开始绘制
        ds = ls
        ds.fill(COLORS["BACKGROUND"])

        # A. 绘制主棋盘
        for r in range(GRID_HEIGHT):
            for c in range(GRID_WIDTH):
                color: tuple[int, int, int] = (
                    self.game.grid[r][c] or COLORS["GRID_LINE"]
                )
                rect = (c * bs, r * bs, bs - 1, bs - 1)
                pygame.draw.rect(ds, color, rect)

        # B. 绘制当前操控块 (仅在游戏进行时)
        if not self.game.game_over:
            for dx, dy in self.game.current_shape:
                rect = (
                    (self.game.x + dx) * bs,
                    (self.game.y + dy) * bs,
                    bs - 1,
                    bs - 1,
                )
                pygame.draw.rect(ds, COLORS[self.game.current_type], rect)

        # C. 绘制美观侧边栏 -------------------------------------------------
        sidebar_left = GRID_WIDTH * bs                 # 从棋盘右侧开始
        sidebar_right = sidebar_left + sb_width
        content_padding = int(20 * scale)              # 左右留白
        sidebar_content_left = sidebar_left + content_padding
        sidebar_content_right = sidebar_right - content_padding
        sidebar_content_width = sidebar_content_right - sidebar_content_left

        # 绘制面板背景
        panel_rect = pygame.Rect(sidebar_left, 0, sb_width, logical_h)
        pygame.draw.rect(ds, self.sidebar_bg, panel_rect)

        # ---- 侧边栏内容 ----
        # 第一行：LV 和 SCORE 标签（小号字体）
        lv_label = font_small.render("LV", True, (150, 150, 160))
        score_label = font_small.render("SCORE", True, (150, 150, 160))
        ds.blit(lv_label, (sidebar_content_left, 20))
        ds.blit(
            score_label,
            (sidebar_content_right - score_label.get_width(), 20),
        )

        # 第二行：对应数值（大号）
        lv_val = font_big.render(f"{self.game.level}", True, (255, 255, 255))
        score_val = font_big.render(
            f"{self.game.score:6d}", True, COLORS["SCORE_GOLD"]
        )
        ds.blit(lv_val, (sidebar_content_left, 45))
        ds.blit(
            score_val,
            (sidebar_content_right - score_val.get_width(), 45),
        )

        # 微弱分隔线
        sep_y1 = int(85 * scale)
        pygame.draw.line(
            ds,
            (60, 60, 70),
            (sidebar_content_left, sep_y1),
            (sidebar_content_right, sep_y1),
            1,
        )

        # 预览框（下一个方块） -------------------------------
        preview_size = 4 * bs
        preview_x = sidebar_content_left + (sidebar_content_width - preview_size) // 2
        preview_y = int(130 * scale)

        # 内框背景
        preview_rect_inner = pygame.Rect(preview_x, preview_y, preview_size, preview_size)
        pygame.draw.rect(ds, (20, 22, 28), preview_rect_inner)

        # 绘制预览方块（居中）
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

        info_y = preview_y + preview_size + int(90 * scale)
        line_spacing = int(35 * scale)

        for i, (label_text, value_text) in enumerate(bottom_lines):
            label_surf = font_small.render(label_text + ": ", True, (200, 200, 200))
            val_surf = font_small.render(value_text, True, (255, 255, 255))
            ds.blit(label_surf, (sidebar_content_left, info_y + i * line_spacing))
            ds.blit(
                val_surf,
                (sidebar_content_left + label_surf.get_width(),
                 info_y + i * line_spacing),
            )

        # D. 绘制 Game Over 弹窗
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

        # E. 绘制暂停弹窗
        elif self.paused:
            overlay = pygame.Surface((logical_w, logical_h))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            ds.blit(overlay, (0, 0))

            paused_text = font_big.render("PAUSED", True, (255, 255, 0))
            resume_text = font_small.render(
                "Press SPACE to resume", True, (255, 255, 255)
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

        # F. 确认退出弹窗
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

            base_y = logical_h // 2 - 50
            ds.blit(
                quit_title,
                (logical_w // 2 - quit_title.get_width() // 2, base_y),
            )
            ds.blit(
                line_esc,
                (logical_w // 2 - line_esc.get_width() // 2, base_y + 40),
            )
            ds.blit(
                line_cancel,
                (logical_w // 2 - line_cancel.get_width() // 2, base_y + 75),
            )

        # 4. 将逻辑表面显示到窗口（居中，黑边填充）
        x_off = (self.window_width - logical_w) // 2
        y_off = (self.window_height - logical_h) // 2
        self.screen.fill((0, 0, 0))
        self.screen.blit(self._logical, (x_off, y_off))

        pygame.display.flip()
