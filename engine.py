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
    # Converted to bottom-origin coordinates: y signs inverted compared to previous top-origin data.
    # Now each (dx, dy) is relative to bottom-origin (y increases upward).
    "I": [(-1, 0), (0, 0), (1, 0), (2, 0)],
    "O": [(0, 0), (1, 0), (0, -1), (1, -1)],
    "T": [(0, 1), (-1, 0), (0, 0), (1, 0)],
    "L": [(1, 1), (-1, 0), (0, 0), (1, 0)],
    "J": [(-1, 1), (-1, 0), (0, 0), (1, 0)],
    "S": [(0, 0), (1, 0), (-1, -1), (0, -1)],
    "Z": [(-1, 0), (0, 0), (0, -1), (1, -1)],
}

# 七种标准方块类型列表（用于7-bag随机生成）
ALL_PIECES: list[str] = ["I", "O", "T", "L", "J", "S", "Z"]

# ----------------- Wall kick / spawn related constants -----------------
# These are a compact, pragmatic set of kick offsets to try when a rotation
# collides. They are not a full SRS implementation but are more explicit
# and easier to maintain than an ad-hoc inline list.
# I-piece generally needs wider horizontal kicks, so we provide a separate
# set for it.
WALL_KICKS_OTHERS: list[tuple[int, int]] = [
    (0, 0),
    (1, 0),
    (-1, 0),
    # vertical components were inverted when switching to bottom-origin;
    # use positive values to represent upward kicks in internal coords.
    (0, 1),
    (1, 1),
    (-1, 1),
    (0, 2),
]

WALL_KICKS_I: list[tuple[int, int]] = [
    (0, 0),
    (1, 0),
    (-1, 0),
    (2, 0),
    (-2, 0),
    # same vertical flip for I-piece special kicks
    (0, 1),
    (0, 2),
]

# Note: spawn behavior will align the top of the piece to row 0 so all
# piece cells are at ty >= 0 immediately after spawn. This makes spawn
# deterministic and consistent across piece types.
# ---------------------------------------------------------------------


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
    rotation: int
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
        # rotation state 0..3 (0 = spawn orientation). Stored to allow
        # future SRS-style kick tables and deterministic rotation behavior.
        self.rotation = 0
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
        # ensure rotation state reset and spawn first piece
        self.rotation = 0
        self._spawn_piece()

    def move(self, dx: int, dy: int) -> bool:
        """尝试移动当前方块，返回是否成功移动。

        Note: internal coordinates use bottom-origin with y increasing upward,
        therefore callers that request a downward move should pass dy = -1.
        """
        if not self._check_collision(self.x + dx, self.y + dy):
            self.x += dx
            self.y += dy
            return True
        return False

    def rotate(self) -> bool:
        """Rotate current piece (no-op for O) and attempt wall-kicks.

        Returns True if the rotation was applied (possibly after a kick),
        False if no rotation occurred (O-piece or all kicks collided).

        The rotation here uses a 90-degree CLOCKWISE transform in the
        engine's internal bottom-origin coords: (x, y) -> (y, -x).
        """
        if self.current_type == "O":
            # O-piece rotation is a no-op
            return False

        # rotate 90 deg CLOCKWISE in engine internal coords.
        new_shape = [(dy, -dx) for dx, dy in self.current_shape]

        # try without kicks first
        if not self._check_collision(self.x, self.y, new_shape):
            self.current_shape = new_shape
            # update rotation state (one step in our clockwise convention)
            self.rotation = (self.rotation + 1) % 4
            return True

        # choose appropriate kick set
        kicks = WALL_KICKS_I if self.current_type == "I" else WALL_KICKS_OTHERS

        for ox, oy in kicks:
            if not self._check_collision(self.x + ox, self.y + oy, new_shape):
                self.x += ox
                self.y += oy
                self.current_shape = new_shape
                # update rotation state only when rotation actually applied
                self.rotation = (self.rotation + 1) % 4
                return True

        # rotation failed (all kicks collide)
        return False

    def lock_and_clear_lines(self) -> None:
        """锁定当前方块到网格，然后检测并消除满行，更新分数、等级，生成下一个方块。

        Internal grid semantics: self.grid[0] is the bottom row; self.grid[GRID_HEIGHT-1]
        is the top row.
        """
        lock_color = COLORS[self.current_type]
        for dx, dy in self.current_shape:
            gx = self.x + dx
            gy = self.y + dy
            if 0 <= gy < GRID_HEIGHT and 0 <= gx < GRID_WIDTH:
                self.grid[gy][gx] = lock_color

        # 记录所有满行的行号（internal indexing: 0=bottom）
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

        # 更新等级
        potential_level = (self.total_lines // 10) + 1
        self.level = min(potential_level, MAX_LEVEL)

        # 从网格中删除满行（从高索引到低索引删除以避免索引错乱），再在顶部插入空行
        if lines_cleared > 0:
            for row in sorted(cleared_rows, reverse=True):
                del self.grid[row]
            for _ in range(lines_cleared):
                self.grid.append([None for _ in range(GRID_WIDTH)])

        self._spawn_piece()

    def _spawn_piece(self) -> None:
        """生成下一个方块到顶部（internal bottom-origin），若碰撞则标记游戏结束。"""
        self.current_type = self.next_type
        self.current_shape = list(SHAPES_DATA[self.current_type])
        self.next_type = self._draw_from_bag()

        # 水平居中 spawn（基于 piece 的 bounding box）
        min_px = min(px for px, _ in self.current_shape)
        max_px = max(px for px, _ in self.current_shape)
        piece_width = max_px - min_px + 1
        self.x = (GRID_WIDTH - piece_width) // 2 - min_px

        # 将 piece 的最高单元对齐到顶部（internal top row = GRID_HEIGHT - 1）
        max_py = max(py for _, py in self.current_shape)
        self.y = GRID_HEIGHT - 1 - max_py

        # reset rotation
        self.rotation = 0

        if self._check_collision(self.x, self.y):
            self.game_over = True

    def _check_collision(
        self,
        nx: int,
        ny: int,
        shape: list[tuple[int, int]] | None = None,
    ) -> bool:
        """
        检查在内部坐标（底部原点）下放置 shape 于 (nx, ny) 是否与边界或已锁定方块冲突。

        规则：
          - gx 越界 -> collision
          - gy < 0 -> collision
          - gy >= GRID_HEIGHT -> allow (spawn above top)
          - 否则如果 grid[gy][gx] 非 None -> collision
        """
        shape = shape if shape is not None else self.current_shape

        for dx, dy in shape:
            gx = nx + dx
            gy = ny + dy  # internal bottom-origin y

            if gx < 0 or gx >= GRID_WIDTH:
                return True
            if gy < 0:
                return True
            if gy >= GRID_HEIGHT:
                # allow parts above the top (spawn area)
                continue
            if self.grid[gy][gx] is not None:
                return True

        return False

    def get_piece_cells(self):
        """Return absolute positions of current piece blocks using internal coords (bottom-origin)."""
        return [(self.x + dx, self.y + dy) for dx, dy in self.current_shape]

    def can_place(
        self,
        nx: int,
        ny: int,
        shape: list[tuple[int, int]] | None = None,
    ) -> bool:
        """Public helper: return True iff placing `shape` at (nx, ny) would NOT collide.

        This is a thin, readable wrapper around the internal _check_collision
        (which returns True on collision). Callers that need to query validity
        of a placement should use this rather than duplicating collision logic.
        """
        return not self._check_collision(nx, ny, shape)

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
        """返回当前方块垂直落到底部后的内部 y（底部为 0）。

        在内部坐标系中，下落方向表示为 y 减小（向下移动使 y 减 1）。
        """
        ghost_y = self.y
        while not self._check_collision(self.x, ghost_y - 1):
            ghost_y -= 1
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
        # Interpret the constants as milliseconds-per-cell for endpoints.
        # Convert to cells-per-second for interpolation to keep linear
        # progression in terms of falling speed (cells/sec), then convert
        # back to a millisecond interval.
        cells_per_sec_min = 1000.0 / MAX_INITIAL_SPEED   # e.g. 2.0 cells/sec
        cells_per_sec_max = 1000.0 / MIN_SPEED           # e.g. 10.0 cells/sec

        # linear interpolation of cells/sec across levels
        cells_per_sec = (
            cells_per_sec_min
            + (cells_per_sec_max - cells_per_sec_min) * (level - 1) / (MAX_LEVEL - 1)
        )

        # convert to milliseconds per cell (interval)
        ms_per_cell = 1000.0 / cells_per_sec
        return int(round(ms_per_cell))
