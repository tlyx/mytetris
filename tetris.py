from typing import final
import sys

import pygame

from engine import TetrisEngine, BLOCK_SIZE, GRID_WIDTH, GRID_HEIGHT, COLORS, SHAPES_DATA

SIDEBAR_WIDTH = 200
SCREEN_WIDTH = GRID_WIDTH * BLOCK_SIZE + SIDEBAR_WIDTH
SCREEN_HEIGHT = GRID_HEIGHT * BLOCK_SIZE


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
    clock: pygame.time.Clock
    sidebar_bg: tuple[int, int, int]

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Tetris Professional - macOS Lab")
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
        self.sidebar_bg = (20, 22, 28)

    def _update_speed(self) -> None:
        """根据等级计算下落速度"""
        speed = max(100, 500 - (self.game.level - 1) * 50)
        pygame.time.set_timer(self.fall_event, speed)
        self.current_level = self.game.level

    def run(self) -> None:
        while True:
            self.process_events()
            self.render_game_scene()
            self.clock.tick(60)

    def process_events(self) -> None:
        """处理所有事件（瞬时/持续）"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # 确认退出状态优先处理
            if self.confirm_quit:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
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
                continue

            # 暂停状态下忽略除暂停键外的其他游戏事件
            if self.paused:
                continue

            if event.type == self.fall_event:
                if not self.game.move(0, 1):
                    self.game.lock_and_clear_lines()
                    # 检查是否需要更新速度
                    if self.game.level != self.current_level:
                        self._update_speed()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.game.rotate()
                elif event.key == pygame.K_LEFT:
                    self.game.move(-1, 0)
                elif event.key == pygame.K_RIGHT:
                    self.game.move(1, 0)
                elif event.key == pygame.K_DOWN:
                    self.game.move(0, 1)

    def render_game_scene(self) -> None:
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

        # C. 绘制美观侧边栏
        sidebar_x: int = GRID_WIDTH * BLOCK_SIZE + 20
        sidebar_width: int = SIDEBAR_WIDTH - 40  # 留边距

        # 绘制面板背景
        panel_rect = pygame.Rect(
            GRID_WIDTH * BLOCK_SIZE, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT
        )
        pygame.draw.rect(self.screen, self.sidebar_bg, panel_rect)

        # 1. Top Bar: Level & Lines (Small font)
        level_surf = self.small_font.render(f"LV: {self.game.level}", True, (0, 255, 255))
        lines_surf = self.small_font.render(f"LN: {self.game.total_lines}", True, (0, 255, 0))
        self.screen.blit(level_surf, (sidebar_x, 20))
        self.screen.blit(lines_surf, (sidebar_x + 80, 20))

        # 分隔线
        pygame.draw.line(
            self.screen, (60, 60, 60),
            (sidebar_x, 50), (sidebar_x + sidebar_width, 50), 1
        )

        # 2. Score
        score_label = self.font.render("SCORE", True, (200, 200, 200))
        score_label_x = sidebar_x + (sidebar_width - score_label.get_width()) // 2
        self.screen.blit(score_label, (score_label_x, 70))
        score_val = self.font.render(str(self.game.score).zfill(6), True, COLORS["SCORE_GOLD"])
        score_val_x = sidebar_x + (sidebar_width - score_val.get_width()) // 2
        self.screen.blit(score_val, (score_val_x, 105))

        # 分隔线
        pygame.draw.line(
            self.screen, (60, 60, 60),
            (sidebar_x, 145), (sidebar_x + sidebar_width, 145), 1
        )

        # 3. Next
        next_label = self.font.render("NEXT", True, (200, 200, 200))
        next_label_x = sidebar_x + (sidebar_width - next_label.get_width()) // 2
        self.screen.blit(next_label, (next_label_x, 160))

        # 预览框（4x4 方块大小）
        preview_size = 4 * BLOCK_SIZE
        preview_x = sidebar_x + (sidebar_width - preview_size) // 2
        preview_y = 200
        preview_rect = (preview_x, preview_y, preview_size, preview_size)
        pygame.draw.rect(self.screen, COLORS["GRID_LINE"], preview_rect, 2)

        # 绘制预览方块（居中）
        next_shape: list[tuple[int, int]] = SHAPES_DATA[self.game.next_type]
        # 计算形状的包围盒
        xs: list[int] = [dx for dx, _dy in next_shape]
        ys: list[int] = [dy for _dx, dy in next_shape]
        min_dx = min(xs)
        max_dx = max(xs)
        min_dy = min(ys)
        max_dy = max(ys)
        shape_width = max_dx - min_dx + 1
        shape_height = max_dy - min_dy + 1
        # 预览框中心偏移
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

        # D. 绘制 Game Over 弹窗
        if self.game.game_over:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))

            go_text = self.font.render("GAME OVER", True, (255, 0, 0))
            restart_text = self.small_font.render("Press RETURN to restart", True, (255, 255, 255))

            self.screen.blit(go_text, (SCREEN_WIDTH // 2 - go_text.get_width() // 2, SCREEN_HEIGHT // 2 - 40))
            self.screen.blit(restart_text, (SCREEN_WIDTH // 2 - restart_text.get_width() // 2, SCREEN_HEIGHT // 2 + 20))

        # E. 绘制暂停弹窗（仅在无 Game Over 且暂停时）
        elif self.paused:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))

            paused_text = self.font.render("PAUSED", True, (255, 255, 0))
            resume_text = self.small_font.render("Press SPACE to resume", True, (255, 255, 255))
            self.screen.blit(paused_text, (SCREEN_WIDTH // 2 - paused_text.get_width() // 2, SCREEN_HEIGHT // 2 - 40))
            self.screen.blit(resume_text, (SCREEN_WIDTH // 2 - resume_text.get_width() // 2, SCREEN_HEIGHT // 2 + 20))

        # F. 确认退出弹窗（优先级最高）
        if self.confirm_quit:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(200)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))

            confirm_text = self.small_font.render("Quit? ESC to confirm, any other key to cancel", True, (255, 255, 0))
            self.screen.blit(confirm_text, (SCREEN_WIDTH // 2 - confirm_text.get_width() // 2, SCREEN_HEIGHT // 2 - 20))

        pygame.display.flip()
