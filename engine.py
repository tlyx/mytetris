# engine.py — 我的方块核心引擎
# 负责网格、方块生成、移动、旋转、消行、计分等逻辑

from typing import final
from random import shuffle

GRID_WIDTH, GRID_HEIGHT = 10, 20

# ---------- 上限常量 ----------
MAX_SCORE = 999999
MAX_TOTAL_LINES = 999999
# -----------------------------

# ---------- 速度与级别相关常量 ----------
MAX_INITIAL_SPEED = 500          # 初始下落间隔（毫秒）
SPEED_DECREASE = 30              # 每升一级减少的毫秒数
MIN_SPEED = 100                  # 速度下限（最快）
# 根据线性公式计算最大级别：当 500 - (level-1)*30 <= 100 时，level >= 14
MAX_LEVEL = (MAX_INITIAL_SPEED - MIN_SPEED) // SPEED_DECREASE + 1   # =14
# ---------------------------------------

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

# 七种标准方块类型列表（用于7-bag随机生成）
ALL_PIECES: list[str] = ["I", "O", "T", "L", "J", "S", "Z"]


@final
class TetrisEngine:
    """游戏逻辑引擎，不依赖任何图形库。"""

    # 消行得分表（类常量）
    SCORE_TABLE: dict[int, int] = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}

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
    # 7-bag 相关
    _bag: list[str]

    # 消行动画相关（记录最近一次消除的行号，供渲染器在下一帧使用）
    _last_cleared_rows: list[int]

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
        self._bag = []
        self._last_cleared_rows = []
        self.reset()

    def reset(self) -> None:
        """重置游戏：清空网格、重置分数/等级、生成第一个方块。"""
        self.grid = [[None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.score = 0
        self.level = 1
        self.total_lines = 0
        self.game_over = False
        # 清空 bag 并重新填充
        self._bag = []
        self._refill_bag()
        # 从 bag 中取出第一个方块作为 next_type
        self.next_type = self._draw_from_bag()
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

        # 记录所有满行的行号
        cleared_rows: list[int] = []
        for row in range(GRID_HEIGHT):
            if all(cell is not None for cell in self.grid[row]):
                cleared_rows.append(row)
        self._last_cleared_rows = cleared_rows

        lines_cleared = len(cleared_rows)
        self.total_lines += lines_cleared
        if self.total_lines > MAX_TOTAL_LINES:
            self.total_lines = MAX_TOTAL_LINES

        # 使用类常量 SCORE_TABLE
        self.score += TetrisEngine.SCORE_TABLE.get(lines_cleared, 800) * self.level
        if self.score > MAX_SCORE:
            self.score = MAX_SCORE

        # 级别上限限制
        potential_level = (self.total_lines // 10) + 1
        self.level = min(potential_level, MAX_LEVEL)

        # 从网格中删除满行（从后往前删，避免索引错乱），再在顶部插入空行
        if lines_cleared > 0:
            for row in reversed(cleared_rows):
                del self.grid[row]
            for _ in range(lines_cleared):
                self.grid.insert(0, [None for _ in range(GRID_WIDTH)])

        self._spawn_piece()

    def _spawn_piece(self) -> None:
        """生成下一个方块到顶部，若碰撞则标记游戏结束。"""
        self.current_type = self.next_type
        # 使用 list() 浅拷贝即可（内部元组不可变）
        self.current_shape = list(SHAPES_DATA[self.current_type])
        # 从 bag 中取出下一个方块作为 next_type（若 bag 为空则重新填充）
        self.next_type = self._draw_from_bag()
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

    # ---------- 7-bag 随机生成器 ----------
    def _refill_bag(self) -> None:
        """用全部七种方块填充 bag 并随机打乱。"""
        self._bag = list(ALL_PIECES)   # 浅拷贝即可，元素为不可变字符串
        shuffle(self._bag)

    def _draw_from_bag(self) -> str:
        """从 bag 顶部取一个方块类型，bag 为空时自动重新填充。"""
        if not self._bag:
            self._refill_bag()
        return self._bag.pop()

    # ---------- Ghost piece ----------
    def get_ghost_y(self) -> int:
        """返回当前方块垂直落到底部后的 y 坐标。"""
        ghost_y = self.y
        while not self._check_collision(self.x, ghost_y + 1):
            ghost_y += 1
        return ghost_y

    # ---------- 消行动画轮询 ----------
    def poll_cleared_rows(self) -> list[int]:
        """返回最近一次消除的行号列表，并清空内部记录。"""
        result = self._last_cleared_rows[:]
        self._last_cleared_rows = []
        return result

    # ---------- 新增：根据等级计算下落速度（毫秒） ----------
    @staticmethod
    def fall_speed(level: int) -> int:
        """返回下落间隔（毫秒），使用匀加速曲线（速度线性增长）。

        速度范围 2.0～10.0 格/秒，每升一级速度增加量相等。
        """
        speed_min = 1000.0 / MAX_INITIAL_SPEED   # 2.0 格/秒
        speed_max = 1000.0 / MIN_SPEED           # 10.0 格/秒
        # 线性插值速度
        speed = speed_min + (speed_max - speed_min) * (level - 1) / (MAX_LEVEL - 1)
        # 转换为毫秒间隔
        return int(round(1000.0 / speed))
