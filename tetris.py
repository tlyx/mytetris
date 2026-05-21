import sys
import time
from random import choice

import pygame

# --- 1. 配置与数据中心 ---
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
class TetrisEngine:
    def __init__(self) -> None:
        self.grid: list[list[tuple[int, int, int] | None]] = [
            [None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)
        ]
        self.score: int = 0
        self.next_type: str = choice(list(SHAPES_DATA.keys()))
        self.spawn_piece()

    def spawn_piece(self) -> None:
        """产生新方块并检查是否 Game Over"""
        self.current_type: str = self.next_type
        self.current_shape: list[tuple[int, int]] = SHAPES_DATA[self.current_type]
        self.next_type = choice(list(SHAPES_DATA.keys()))
        self.x: int = 4
        self.y: int = 1

        if self.check_collision(self.x, self.y):
            print(f"任务结束！最终战果: {self.score}")
            pygame.quit()
            sys.exit()

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

        # Nintendo 阶梯计分法
        score_table: dict[int, int] = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
        self.score += score_table.get(lines_cleared, 800)

        # 补齐空行
        while len(new_grid) < GRID_HEIGHT:
            new_grid.insert(0, [None for _ in range(GRID_WIDTH)])
        self.grid = new_grid
        self.spawn_piece()


class TetrisApp:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Tetris Professional - macOS Lab")
        self.font = pygame.font.SysFont("Arial Black", 32)
        
        self.game = TetrisEngine()
        self.fall_event = pygame.USEREVENT + 1
        pygame.time.set_timer(self.fall_event, 500)
        self.clock = pygame.time.Clock()
        self.pressing_timer = [0.0]

    def run(self) -> None:
        while True:
            self.process_events()
            self.handle_continuous_input()
            self.render_game_scene()
            self.clock.tick(60)

    def process_events(self) -> None:
        """处理 on_down (瞬时) 事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == self.fall_event:
                if not self.game.move(0, 1):
                    self.game.lock_and_clear_lines()

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
        """极致渲染：主场 + 侧边栏预览"""
        self.screen.fill(COLORS["BACKGROUND"])

        # A. 绘制主棋盘
        for r in range(GRID_HEIGHT):
            for c in range(GRID_WIDTH):
                color: tuple[int, int, int] = self.game.grid[r][c] or COLORS["GRID_LINE"]
                rect = (c * BLOCK_SIZE, r * BLOCK_SIZE, BLOCK_SIZE - 1, BLOCK_SIZE - 1)
                pygame.draw.rect(self.screen, color, rect)

        # B. 绘制当前操控块
        for dx, dy in self.game.current_shape:
            rect = (
                (self.game.x + dx) * BLOCK_SIZE,
                (self.game.y + dy) * BLOCK_SIZE,
                BLOCK_SIZE - 1,
                BLOCK_SIZE - 1,
            )
            pygame.draw.rect(self.screen, COLORS[self.game.current_type], rect)

        # C. 绘制复古侧边栏
        sidebar_x: int = GRID_WIDTH * BLOCK_SIZE + 40

        # 1. 分数 (金色占位显示)
        score_text: str = str(self.game.score).zfill(6)
        score_surf: pygame.Surface = self.font.render(score_text, True, COLORS["SCORE_GOLD"])
        self.screen.blit(score_surf, (sidebar_x, 40))

        # 2. Next 预览 (无文字，加边框)
        preview_rect = (sidebar_x, 120, 4 * BLOCK_SIZE, 4 * BLOCK_SIZE)
        pygame.draw.rect(self.screen, COLORS["GRID_LINE"], preview_rect, 1)

        next_shape: list[tuple[int, int]] = SHAPES_DATA[self.game.next_type]
        for dx, dy in next_shape:
            px: float = sidebar_x + (dx + 1.5) * BLOCK_SIZE
            py: float = 120 + (dy + 1.5) * BLOCK_SIZE
            pygame.draw.rect(
                self.screen,
                COLORS[self.game.next_type],
                (px, py, BLOCK_SIZE - 1, BLOCK_SIZE - 1),
            )
        pygame.display.flip()


