from typing import final
import sys

import pygame

from engine import TetrisEngine, BLOCK_SIZE, GRID_WIDTH, GRID_HEIGHT, COLORS, SHAPES_DATA

SIDEBAR_WIDTH = 200
SCREEN_WIDTH = GRID_WIDTH * BLOCK_SIZE + SIDEBAR_WIDTH
SCREEN_HEIGHT = GRID_HEIGHT * BLOCK_SIZE

HIGH_SCORE_FILE = "highscore.txt"


def load_high_score() -> int:
    try:
        with open(HIGH_SCORE_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def save_high_score(value: int) -> None:
    with open(HIGH_SCORE_FILE, "w") as f:
        f.write(str(value))


@final
class TetrisApp:
    screen: pygame.Surface
    font: pygame.font.Font
    small_font: pygame.font.Font
    serif_font: pygame.font.Font
    serif_bold_font: pygame.font.Font
    game: TetrisEngine
    fall_event: int
    current_level: int
    paused: bool
    confirm_quit: bool
    high_score: int
    game_start_ticks: int
    clock: pygame.time.Clock
    sidebar_bg: tuple[int, int, int]

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Tetris Professional - macOS Lab")
        self.font = pygame.font.SysFont("Arial Black", 32)
        self.small_font = pygame.font.SysFont("Arial Black", 20)
        # 衬线字体用于底部信息，比之前稍大
        self.serif_font = pygame.font.SysFont("Times New Roman", 18)
        self.serif_bold_font = pygame.font.SysFont("Times New Roman", 18, bold=True)
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
                pygame.quit()
                sys.exit()

            # 确认退出状态优先处理
            if self.confirm_quit:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        save_high_score(self.high_score)
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
        """极致渲染：主场 + 美观侧边栏 + Game Over / Pause / Confirm Quit 弹窗"""
        self.screen.fill(COLORS["BACKGROUND"])

        # A. 绘制主棋盘
        for r in range(GRID_HEIGHT):
            for c in range(GRID_WIDTH):
                color: tuple[int, int, int] = self.game.grid[r][c] or COLORS["GRID_LINE"]
                rect = (c * BLOCK_SIZE, r * BLOCK_SIZE, BLOCK_SIZE - 1, BLOCK_SIZE - 1)
                pygame.draw.rect(self.screen, color, rect)

        # B. 绘制当前操控块 (仅在游戏进行时)
        if not self.game.game_over:
            for dx, dy in self.game.current_shape:
                rect = (
                    (self.game.x + dx) * BLOCK_SIZE,
                    (self.game.y + dy) * BLOCK_SIZE,
                    BLOCK_SIZE - 1,
                    BLOCK_SIZE - 1,
                )
                pygame.draw.rect(self.screen, COLORS[self.game.current_type], rect)

        # C. 绘制美观侧边栏 -------------------------------------------------
        sidebar_x: int = GRID_WIDTH * BLOCK_SIZE + 20
        sidebar_width: int = SIDEBAR_WIDTH - 30  # 留边距

        # 绘制面板背景
        panel_rect = pygame.Rect(
            GRID_WIDTH * BLOCK_SIZE, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT
        )
        pygame.draw.rect(self.screen, self.sidebar_bg, panel_rect)

        # ---- 侧边栏内容：新布局 ----

        # 第一行：LV 和 SCORE 标签（小号字体）
        lv_label = self.small_font.render("LV", True, (150, 150, 160))
        score_label = self.small_font.render("SCORE", True, (150, 150, 160))
        # 将两个标签分别放在左右两侧
        self.screen.blit(lv_label, (sidebar_x, 20))
        self.screen.blit(
            score_label,
            (sidebar_x + sidebar_width - score_label.get_width(), 20),
        )

        # 第二行：对应数值（大号）
        lv_val = self.font.render(f"{self.game.level}", True, (255, 255, 255))
        score_val = self.font.render(
            f"{self.game.score:6d}", True, COLORS["SCORE_GOLD"]
        )
        self.screen.blit(lv_val, (sidebar_x, 45))
        self.screen.blit(
            score_val,
            (sidebar_x + sidebar_width - score_val.get_width(), 45),
        )

        # 微弱分隔线
        pygame.draw.line(
            self.screen,
            (60, 60, 70),
            (sidebar_x, 85),
            (sidebar_x + sidebar_width, 85),
            1,
        )

        # 预览框（下一个方块，不写 NEXT 标签） -------------------------------
        preview_size = 4 * BLOCK_SIZE
        preview_x = sidebar_x + (sidebar_width - preview_size) // 2
        preview_y = 110  # 往下移了一些，避免与数字重叠

        # 外框
        preview_rect_outer = pygame.Rect(
            preview_x - 4, preview_y - 4, preview_size + 8, preview_size + 8
        )
        pygame.draw.rect(self.screen, (40, 42, 50), preview_rect_outer)
        # 内框
        preview_rect_inner = pygame.Rect(
            preview_x, preview_y, preview_size, preview_size
        )
        pygame.draw.rect(self.screen, (20, 22, 28), preview_rect_inner)

        # 绘制预览方块（居中，不带圆角）
        next_shape: list[tuple[int, int]] = SHAPES_DATA[self.game.next_type]
        xs: list[int] = [dx for dx, _dy in next_shape]
        ys: list[int] = [dy for _dx, dy in next_shape]
        min_dx = min(xs)
        max_dx = max(xs)
        min_dy = min(ys)
        max_dy = max(ys)
        shape_width = max_dx - min_dx + 1
        shape_height = max_dy - min_dy + 1
        offset_x = (preview_size - shape_width * BLOCK_SIZE) // 2
        offset_y = (preview_size - shape_height * BLOCK_SIZE) // 2
        for dx, dy in next_shape:
            px = preview_x + offset_x + (dx - min_dx) * BLOCK_SIZE
            py = preview_y + offset_y + (dy - min_dy) * BLOCK_SIZE
            pygame.draw.rect(
                self.screen,
                COLORS[self.game.next_type],
                (px, py, BLOCK_SIZE - 1, BLOCK_SIZE - 1),
            )

        # 底部统计信息：Lines, Best, Time（衬线字体，稍大，左对齐） --------------
        # 计算游戏时间
        elapsed_sec = (pygame.time.get_ticks() - self.game_start_ticks) // 1000
        mins = elapsed_sec // 60
        secs = elapsed_sec % 60
        time_str = f"{mins:02d}:{secs:02d}"

        # 每行格式：标签（非粗体）＋ 数值（粗体）
        bottom_lines = [
            ("Lines", str(self.game.total_lines)),
            ("Best", str(self.high_score)),
            ("Time", time_str),
        ]

        # 更多下方位置，并且不使用居中，左对齐
        info_y = preview_y + preview_size + 40  # 预览框下方多留空间
        line_spacing = 30

        for i, (label_text, value_text) in enumerate(bottom_lines):
            # 标签和冒号
            prefix = f"{label_text}: "
            prefix_surf = self.serif_font.render(prefix, True, (200, 200, 200))
            # 粗体数值
            value_surf = self.serif_bold_font.render(value_text, True, (255, 255, 255))

            # 左对齐，直接放在侧边栏左侧
            self.screen.blit(prefix_surf, (sidebar_x, info_y + i * line_spacing))
            self.screen.blit(
                value_surf,
                (sidebar_x + prefix_surf.get_width(), info_y + i * line_spacing),
            )

        # D. 绘制 Game Over 弹窗
        if self.game.game_over:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))

            go_text = self.font.render("GAME OVER", True, (255, 0, 0))
            restart_text = self.small_font.render(
                "Press RETURN to restart", True, (255, 255, 255)
            )
            self.screen.blit(
                go_text,
                (SCREEN_WIDTH // 2 - go_text.get_width() // 2, SCREEN_HEIGHT // 2 - 40),
            )
            self.screen.blit(
                restart_text,
                (
                    SCREEN_WIDTH // 2 - restart_text.get_width() // 2,
                    SCREEN_HEIGHT // 2 + 20,
                ),
            )

        # E. 绘制暂停弹窗（仅在无 Game Over 且暂停时）
        elif self.paused:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))

            paused_text = self.font.render("PAUSED", True, (255, 255, 0))
            resume_text = self.small_font.render(
                "Press SPACE to resume", True, (255, 255, 255)
            )
            self.screen.blit(
                paused_text,
                (SCREEN_WIDTH // 2 - paused_text.get_width() // 2, SCREEN_HEIGHT // 2 - 40),
            )
            self.screen.blit(
                resume_text,
                (
                    SCREEN_WIDTH // 2 - resume_text.get_width() // 2,
                    SCREEN_HEIGHT // 2 + 20,
                ),
            )

        # F. 确认退出弹窗（优先级最高，多行排版）
        if self.confirm_quit:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(200)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))

            quit_title = self.font.render("QUIT ?", True, (255, 100, 100))
            line_esc = self.small_font.render(
                "Press ESC to confirm", True, (255, 255, 255)
            )
            line_cancel = self.small_font.render(
                "Any other key to cancel", True, (255, 255, 255)
            )

            base_y = SCREEN_HEIGHT // 2 - 50
            self.screen.blit(
                quit_title,
                (SCREEN_WIDTH // 2 - quit_title.get_width() // 2, base_y),
            )
            self.screen.blit(
                line_esc,
                (SCREEN_WIDTH // 2 - line_esc.get_width() // 2, base_y + 40),
            )
            self.screen.blit(
                line_cancel,
                (SCREEN_WIDTH // 2 - line_cancel.get_width() // 2, base_y + 75),
            )

        pygame.display.flip()
