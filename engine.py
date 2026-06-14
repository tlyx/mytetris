# engine.py — 俄罗斯方块核心引擎
# 负责网格、方块生成、移动、旋转、消行、计分等逻辑

from typing import final
from random import choice

GRID_WIDTH, GRID_HEIGHT = 10, 20

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

SHAPES_DATA: dict[str, list[tuple[int, int]]] = {
    "I": [(-1, 0), (0, 0), (1, 0), (2, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(0, -1), (-1, 0), (0, 0), (1, 0)],
    "L": [(1, -1), (-1, 0), (0, 0), (1, 0)],
    "J": [(-1, -1), (-1, 0), (0, 0), (1, 0)],
    "S": [(0, 0), (1, 0), (-1, 1), (0, 1)],
    "Z": [(-1, 0), (0, 0), (0, 1), (1, 1)],
}

@final
class TetrisEngine:
    """游戏逻辑引擎，不依赖任何图形库。"""

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
        """初始化网格与属性，并立即调用 reset 开始第一局。"""
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
        """重置游戏：清空网格、重置分数/等级、生成第一个方块。"""
        self.grid = [[None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.score = 0
        self.level = 1
        self.total_lines = 0
        self.game_over = False
        self.next_type = choice(list(SHAPES_DATA.keys()))
        self._spawn_piece()

    def move(self, dx: int, dy: int) -> bool:
        """尝试移动当前方块，返回是否成功移动。"""
        if not self._check_collision(self.x + dx, self.y + dy):
            self.x += dx
            self.y += dy
            return True
        return False

    def rotate(self) -> None:
        """尝试旋转当前方块（O 型不旋转），支持 Wall Kick。"""
        if self.current_type == "O":
            return
        new_shape: list[tuple[int, int]] = [(-dy, dx) for dx, dy in self.current_shape]
        if not self._check_collision(self.x, self.y, new_shape):
            self.current_shape = new_shape
            return
        kicks = [(1, 0), (-1, 0), (0, -1), (1, -1), (-1, -1), (0, -2)]
        for ox, oy in kicks:
            if not self._check_collision(self.x + ox, self.y + oy, new_shape):
                self.x += ox
                self.y += oy
                self.current_shape = new_shape
                return

    def lock_and_clear_lines(self) -> None:
        """锁定当前方块到网格，然后检测并消除满行，更新分数、等级，生成下一个方块。"""
        lock_color = COLORS[self.current_type]
        for dx, dy in self.current_shape:
            if 0 <= self.y + dy < GRID_HEIGHT:
                self.grid[self.y + dy][self.x + dx] = lock_color

        new_grid: list[list[tuple[int, int, int] | None]] = [
            row for row in self.grid if any(cell is None for cell in row)
        ]
        lines_cleared: int = GRID_HEIGHT - len(new_grid)
        self.total_lines += lines_cleared

        score_table: dict[int, int] = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
        self.score += score_table.get(lines_cleared, 800) * self.level

        self.level = (self.total_lines // 10) + 1

        while len(new_grid) < GRID_HEIGHT:
            new_grid.insert(0, [None for _ in range(GRID_WIDTH)])
        self.grid = new_grid
        self._spawn_piece()

    def _spawn_piece(self) -> None:
        """生成下一个方块到顶部，若碰撞则标记游戏结束。"""
        self.current_type = self.next_type
        self.current_shape = SHAPES_DATA[self.current_type]
        self.next_type = choice(list(SHAPES_DATA.keys()))
        self.x = 4
        self.y = 1

        if self._check_collision(self.x, self.y):
            self.game_over = True

    def _check_collision(
        self, nx: int, ny: int, shape: list[tuple[int, int]] | None = None
    ) -> bool:
        """检查方块在给定位置是否与墙壁或已有块碰撞。"""
        shape = shape or self.current_shape
        for dx, dy in shape:
            tx, ty = nx + dx, ny + dy
            if not (0 <= tx < GRID_WIDTH and 0 <= ty < GRID_HEIGHT):
                return True
            if ty >= 0 and self.grid[ty][tx]:
                return True
        return False
