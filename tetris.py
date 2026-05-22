from typing import final
from random import choice
import sys
import time

import pygame

# --- 1. 配置与数据中心 ---
# (Constants remain unchanged)
BLOCK_SIZE = 30
GRID_WIDTH, GRID_HEIGHT = 10, 20
SIDEBAR_WIDTH = 200
SCREEN_WIDTH = GRID_WIDTH * BLOCK_SIZE + SIDEBAR_WIDTH
SCREEN_HEIGHT = GRID_HEIGHT * BLOCK_SIZE

# 工业级调色板
COLORS: dict[str, tuple[int, int, int]] = {
    "BACKGROUND": (10, 12, 15),
    "GRID_LINE": (30, 33, 40),
    "SCORE_GOLD": (255, 215, 0),
    "I": (0, 240, 240),
    "O": (240, 240, 0),
    "T": (160, 0, 240),
    "L": (240, 160, 0),
    "J": (0, 0, 240),
    "S": (0, 240, 0),
    "Z": (240, 0, 0),
}

# 七种方块的坐标定义 (以中心点旋转)
SHAPES_DATA: dict[str, list[tuple[int, int]]] = {
    "I": [(-1, 0), (0, 0), (1, 0), (2, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(0, -1), (-1, 0), (0, 0), (1, 0)],
    "L": [(1, -1), (-1, 0), (0, 0), (1, 0)],
    "J": [(-1, -1), (-1, 0), (0, 0), (1, 0)],
    "S": [(0, 0), (1, 0), (-1, 1), (0, 1)],
    "Z": [(-1, 0), (0, 0), (0, 1), (1, 1)],
}

# --- 2. 核心逻辑引擎 ---
@final
class TetrisEngine:
    grid: list[list[tuple[int, int, int] | None]]
    score: int
    level: int
    total_lines: int
    game_over: bool
    next_type: str
    current_type: str
    current_shape: list[tuple[int, int]]
    x: int
    y: int

    def __init__(self) -> None:
        self.grid = []
        self.score = 0
        self.level = 1
        self.total_lines = 0
        self.game_over = False
        self.next_type = ""
        self.current_type = ""
        self.current_shape = []
        self.x = 0
        self.y = 0
        self.reset()

    def reset(self) -> None:
        self.grid = [[None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.score = 0
        self.level = 1
        self.total_lines = 0
        self.game_over = False
        self.next_type = choice(list(SHAPES_DATA.keys()))
        self.spawn_piece()

    def spawn_piece(self) -> None:
        """产生新方块并检查是否 Game Over"""
        self.current_type = self.next_type
        self.current_shape = SHAPES_DATA[self.current_type]
        self.next_type = choice(list(SHAPES_DATA.keys()))
        self.x = 4
        self.y = 1

        if self.check_collision(self.x, self.y):
            self.game_over = True

    def check_collision(
        self, nx: int, ny: int, shape: list[tuple[int, int]] | None = None
    ) -> bool:
        shape = shape or self.current_shape
        for dx, dy in shape:
            tx, ty = nx + dx, ny + dy
            if not (0 <= tx < GRID_WIDTH and 0 <= ty < GRID_HEIGHT):
                return True
            if ty >= 0 and self.grid[ty][tx]:
                return True
        return False

    def move(self, dx: int, dy: int) -> bool:
        if not self.check_collision(self.x + dx, self.y + dy):
            self.x += dx
            self.y += dy
            return True
        return False

    def rotate(self) -> None:
        if self.current_type == "O":
            return
        # 矩阵旋转逻辑：(x, y) -> (-y, x)
        new_shape: list[tuple[int, int]] = [(-dy, dx) for dx, dy in self.current_shape]
        if not self.check_collision(self.x, self.y, new_shape):
            self.current_shape = new_shape

    def lock_and_clear_lines(self) -> None:
        """固化方块并执行阶梯计分"""
        for dx, dy in self.current_shape:
            if 0 <= self.y + dy < GRID_HEIGHT:
                self.grid[self.y + dy][self.x + dx] = COLORS[self.current_type]

        # 找出非满行
        new_grid: list[list[tuple[int, int, int] | None]] = [
            row for row in self.grid if any(cell is None for cell in row)
        ]
        lines_cleared: int = GRID_HEIGHT - len(new_grid)
        self.total_lines += lines_cleared

        # Nintendo 阶梯计分法 (带等级加成)
        score_table: dict[int, int] = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
        self.score += score_table.get(lines_cleared, 800) * self.level

        # 难度升级逻辑
        self.level = (self.total_lines // 10) + 1

        # 补齐空行
        while len(new_grid) < GRID_HEIGHT:
            new_grid.insert(0, [None for _ in range(GRID_WIDTH)])
        self.grid = new_grid
        self.spawn_piece()


@final
class TetrisApp:
    screen: pygame.Surface
    font: pygame.font.Font
    small_font: pygame.font.Font
    game: TetrisEngine
    fall_event: int
    current_level: int
    clock: pygame.time.Clock
    pressing_timer: list[float]

    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Tetris Professional - macOS Lab")
        self.font = pygame.font.SysFont("Arial Black", 32)
        self.small_font = pygame.font.SysFont("Arial Black", 20)
        
        self.game = TetrisEngine()
        self.fall_event = pygame.USEREVENT + 1
        self.current_level = 1
        self._update_speed()
        self.clock = pygame.time.Clock()
        self.pressing_timer = [0.0]

    def _update_speed(self) -> None:
        """根据等级计算下落速度"""
        speed = max(100, 500 - (self.game.level - 1) * 50)
        pygame.time.set_timer(self.fall_event, speed)
        self.current_level = self.game.level

    def run(self) -> None:
        while True:
            self.process_events()
            if not self.game.game_over:
                self.handle_continuous_input()
            self.render_game_scene()
            self.clock.tick(60)

    def process_events(self) -> None:
        """处理 on_down (瞬时) 事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if self.game.game_over:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    self.game.reset()
                    self.current_level = 1
                    self._update_speed()
                continue

            if event.type == self.fall_event:
                if not self.game.move(0, 1):
                    self.game.lock_and_clear_lines()
                    # 检查是否需要更新速度
                    if self.game.level != self.current_level:
                        self._update_speed()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.game.rotate()
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()

    def handle_continuous_input(self) -> None:
        """处理 on_pressing (持续) 事件"""
        now: float = time.time()
        if now - self.pressing_timer[0] < 0.08:
            return

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            self.game.move(-1, 0)
        if keys[pygame.K_RIGHT]:
            self.game.move(1, 0)
        if keys[pygame.K_DOWN]:
            self.game.move(0, 1)

        self.pressing_timer[0] = now

    def render_game_scene(self) -> None:
        """极致渲染：主场 + 美观侧边栏 + Game Over 弹窗"""
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

        # 1. Top Bar: Level & Lines (Small font)
        level_surf = self.small_font.render(f"LV: {self.game.level}", True, (0, 255, 255))
        lines_surf = self.small_font.render(f"LN: {self.game.total_lines}", True, (0, 255, 0))
        self.screen.blit(level_surf, (sidebar_x, 20))
        self.screen.blit(lines_surf, (sidebar_x + 80, 20))

        # 2. Score
        score_label = self.font.render("SCORE", True, (200, 200, 200))
        self.screen.blit(score_label, (sidebar_x, 60))
        score_val = self.font.render(str(self.game.score).zfill(6), True, COLORS["SCORE_GOLD"])
        self.screen.blit(score_val, (sidebar_x, 90))

        # 3. Next
        next_label = self.font.render("NEXT", True, (200, 200, 200))
        self.screen.blit(next_label, (sidebar_x, 150))
        preview_rect = (sidebar_x, 190, 4 * BLOCK_SIZE, 4 * BLOCK_SIZE)
        pygame.draw.rect(self.screen, COLORS["GRID_LINE"], preview_rect, 1)

        next_shape: list[tuple[int, int]] = SHAPES_DATA[self.game.next_type]
        for dx, dy in next_shape:
            px: float = sidebar_x + (dx + 1.5) * BLOCK_SIZE
            py: float = 190 + (dy + 1.5) * BLOCK_SIZE
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
            restart_text = self.small_font.render("Press R to Restart", True, (255, 255, 255))
            
            self.screen.blit(go_text, (SCREEN_WIDTH // 2 - go_text.get_width() // 2, SCREEN_HEIGHT // 2 - 40))
            self.screen.blit(restart_text, (SCREEN_WIDTH // 2 - restart_text.get_width() // 2, SCREEN_HEIGHT // 2 + 20))

        pygame.display.flip()


