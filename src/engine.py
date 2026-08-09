# engine.py — 我的方块核心引擎（纯逻辑，不依赖图形库）
#
# 此文件主要负责：
#  - 10×20 网格与七种标准方块（7-bag 随机生成）
#  - 移动、旋转（wall-kick）、碰撞检测、锁定
#  - 消行、计分、连击、等级与下落速度
#  - 共享几何原语（rotate_shape / collides / drop_y / …，供 bot 复用）

from random import shuffle
from typing import ClassVar, final

GRID_WIDTH, GRID_HEIGHT = 10, 20

# ---------- 上限常量 ----------
MAX_SCORE = 999999
_MAX_TOTAL_LINES = 999999
# -----------------------------

# ---------- 速度与级别相关常量 ----------
_MAX_INITIAL_SPEED = 500          # 初始下落间隔（毫秒）
_SPEED_DECREASE = 30              # 每升一级减少的毫秒数
_MIN_SPEED = 100                  # 速度下限（最快）
# 最大级别：速度从 500ms 按每级 -30ms 递减，第 14 级为 110ms（下限 100 之上的最后一级）
_MAX_LEVEL = (_MAX_INITIAL_SPEED - _MIN_SPEED) // _SPEED_DECREASE + 1   # =14
# ---------------------------------------

# ---------- 锁定延迟（指南标准） ----------
# 方块贴地后仍可移动/旋转的操作窗口；每次成功移动/旋转重置计时，
# 但每块最多重置 15 次（预算耗尽后不再延长），硬降立即锁定不吃延迟。
LOCK_DELAY_MS = 500
LOCK_RESET_LIMIT = 15
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
    # 已转换为底部原点坐标：相对旧版顶部原点数据，y 符号取反。
    # 现在每个 (dx, dy) 相对底部原点（y 向上递增）。
    "I": [(-1, 0), (0, 0), (1, 0), (2, 0)],
    "O": [(0, 0), (1, 0), (0, -1), (1, -1)],
    "T": [(0, 1), (-1, 0), (0, 0), (1, 0)],
    "L": [(1, 1), (-1, 0), (0, 0), (1, 0)],
    "J": [(-1, 1), (-1, 0), (0, 0), (1, 0)],
    "S": [(0, 0), (1, 0), (-1, -1), (0, -1)],
    "Z": [(-1, 0), (0, 0), (0, -1), (1, -1)],
}

# 七种标准方块类型列表（用于7-bag随机生成）
_ALL_PIECES: list[str] = ["I", "O", "T", "L", "J", "S", "Z"]

# ----------------- Wall kick / spawn related constants -----------------
# 一组紧凑实用的踢位偏移：旋转碰撞时依次尝试。并非完整的 SRS 实现，
# 但比临时内联列表更明确、更易维护。
# I 方块通常需要更宽的横向踢位，因此单独提供一组。
_WALL_KICKS_OTHERS: list[tuple[int, int]] = [
    (0, 0),
    (1, 0),
    (-1, 0),
    # 切换到底部原点时 y 分量取反；
    # 使用正值表示内部坐标系中的向上踢。
    (0, 1),
    (1, 1),
    (-1, 1),
    (0, 2),
]

_WALL_KICKS_I: list[tuple[int, int]] = [
    (0, 0),
    (1, 0),
    (-1, 0),
    (2, 0),
    (-2, 0),
    # I 块特殊踢的垂直分量同样取反
    (0, 1),
    (0, 2),
]

# 注意：生成行为会把方块最高单元对齐到顶行，保证所有方块单元
# 生成后立即满足 ty >= 0，使各类型方块的生成位置确定且一致。
# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
# 纯几何原语（无状态，引擎方法与外部模拟共享）
#
# 所有函数使用内部底部原点坐标（y 向上为正）。提取为模块级函数，
# 使 bot 的模拟与引擎实际规则使用同一份实现，避免两处各自维护导致
# 语义漂移（bot 不能直接调引擎的实时网格碰撞检查，
# 而模拟必须作用在模拟盘面上）。
# ---------------------------------------------------------------------

def rotate_shape(
    shape: list[tuple[int, int]], times: int = 1
) -> list[tuple[int, int]]:
    """按引擎的 90° 顺时针变换旋转 shape times 次：(x, y) -> (y, -x)。"""
    piece = shape
    for _ in range(times):
        piece = [(py, -px) for px, py in piece]
    return piece


def spawn_y(shape: list[tuple[int, int]]) -> int:
    """返回生成位 y：将 shape 的最高单元对齐到顶部行（GRID_HEIGHT - 1）。"""
    return GRID_HEIGHT - 1 - max(py for _, py in shape)


def collides(
    grid: list[list[tuple[int, int, int] | None]],
    x: int,
    y: int,
    shape: list[tuple[int, int]],
) -> bool:
    """检查在内部坐标下放置 shape 于 (x, y) 是否与边界或已锁定方块冲突。

    规则：
      - gx 越界 -> 冲突
      - gy < 0 -> 冲突
      - gy >= GRID_HEIGHT -> 放行（生成区允许超出顶部）
      - 否则 grid[gy][gx] 非 None -> 冲突
    """
    for dx, dy in shape:
        gx = x + dx
        gy = y + dy
        if gx < 0 or gx >= GRID_WIDTH:
            return True
        if gy < 0:
            return True
        if gy >= GRID_HEIGHT:
            continue
        if grid[gy][gx] is not None:
            return True
    return False


def drop_y(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
    x: int,
    start_y: int,
) -> int:
    """从 start_y 垂直下落 shape 到不能再下，返回最终 y（start_y 处必须合法）。"""
    y = start_y
    while not collides(grid, x, y - 1, shape):
        y -= 1
    return y


def cells_in_bounds(
    x: int,
    y: int,
    shape: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """返回落定后实际在边界内的单元格坐标（超出顶部的部分被丢弃）。"""
    return [
        (x + dx, y + dy)
        for dx, dy in shape
        if 0 <= x + dx < GRID_WIDTH and 0 <= y + dy < GRID_HEIGHT
    ]


@final
class TetrisEngine:
    """游戏逻辑引擎，不依赖任何图形库。"""

    # 消行得分表（类常量）
    SCORE_TABLE: ClassVar[dict[int, int]] = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}

    grid: list[list[tuple[int, int, int] | None]]
    score: int
    level: int
    total_lines: int
    combo: int
    game_over: bool
    next_type: str
    current_type: str
    current_shape: list[tuple[int, int]]
    x: int
    y: int
    rotation: int
    # 当前方块的唯一实例 id：每次生成新块 +1。
    # 用于区分"同类型但不同的块"（bot 靠它识别换块，而非方块类型）。
    piece_id: int
    # 贴地时刻（ticks），锁定延迟计时；None 表示方块未贴地
    resting_since: int | None
    # 本块已消耗的锁定延迟重置次数（上限 LOCK_RESET_LIMIT，每块归零）
    lock_resets: int
    # 7-bag 相关
    _bag: list[str]

    # 消行动画相关（记录最近一次消除的行号，供渲染器在下一帧使用）
    _last_cleared_rows: list[int]

    def __init__(self) -> None:
        """初始化引擎并立即开始第一局（reset 负责全部规则状态）。"""
        # 仅在实例创建时初始化一次、且 reset 不负责的状态：
        self.piece_id = 0  # _spawn_piece 会自增，需先有初值
        self._last_cleared_rows = []  # 消行动画记录（reset 不重置）
        self.reset()

    def reset(self) -> None:
        """重置游戏：清空网格、重置分数/等级、生成第一个方块。"""
        self.grid = [[None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.score = 0
        self.level = 1
        self.total_lines = 0
        self.combo = 0
        self.game_over = False
        # 重新填充 bag（_refill_bag 全量写入），取出第一个方块
        self._refill_bag()
        self.next_type = self._draw_from_bag()
        # 生成第一个方块（_spawn_piece 内部重置旋转状态）
        self._spawn_piece()

    def move(self, dx: int, dy: int) -> bool:
        """尝试移动当前方块，返回是否成功移动。

        注意：内部坐标系为底部原点（y 向上递增），因此向下移动时
        调用方应传 dy = -1。
        """
        if not self._check_collision(self.x + dx, self.y + dy):
            self.x += dx
            self.y += dy
            return True
        return False

    def hard_drop(self) -> int:
        """硬降：将当前块垂直落到底部，返回落下的格数（计分用）。

        每落一格 +2 分（指南标准），由引擎统一计分。
        """
        distance = 0
        while self.move(0, -1):
            distance += 1
        self.add_score(2 * distance)  # 硬降每格 +2（指南标准）
        return distance

    def soft_drop(self) -> bool:
        """软降一格：成功则 +1 分（指南标准）并返回 True。

        与 move(0, -1) 的区别：软降是玩家主动下移，计软降分。
        """
        if self.move(0, -1):
            self.add_score(1)  # 软降每格 +1（指南标准）
            return True
        return False

    def add_score(self, points: int) -> None:
        """增加分数并封顶到 MAX_SCORE。"""
        self.score = min(self.score + points, MAX_SCORE)

    def rotate(self) -> bool:
        """旋转当前方块（O 方块为无操作）并尝试 wall-kick。

        返回 True 表示旋转已应用（可能经过 kick 位移），
        False 表示未发生旋转（O 方块或所有 kick 均碰撞）。

        旋转使用引擎内部底部原点坐标系下的 90° 顺时针变换：
        (x, y) -> (y, -x)。
        """
        if self.current_type == "O":
            # O 方块旋转是无操作
            return False

        # 在引擎内部坐标系中顺时针旋转 90°。
        new_shape = rotate_shape(self.current_shape, 1)

        # 先尝试不做踢位直接旋转
        if not self._check_collision(self.x, self.y, new_shape):
            self.current_shape = new_shape
            # update rotation state (one step in our clockwise convention)
            self.rotation = (self.rotation + 1) % 4
            return True

        # choose appropriate kick set
        kicks = _WALL_KICKS_I if self.current_type == "I" else _WALL_KICKS_OTHERS

        for ox, oy in kicks:
            if not self._check_collision(self.x + ox, self.y + oy, new_shape):
                self.x += ox
                self.y += oy
                self.current_shape = new_shape
                # update rotation state only when rotation actually applied
                self.rotation = (self.rotation + 1) % 4
                return True

        # 旋转失败（所有踢位均碰撞）
        return False

    def lock_and_clear_lines(self) -> None:
        """锁定当前方块到网格，然后检测并消除满行，更新分数、等级，生成下一个方块。

        内部网格语义：self.grid[0] 为底行；self.grid[GRID_HEIGHT-1] 为顶行。
        """
        lock_color = COLORS[self.current_type]
        for gx, gy in cells_in_bounds(self.x, self.y, self.current_shape):
            self.grid[gy][gx] = lock_color

        # 记录所有满行的行号（internal indexing: 0=bottom）
        cleared_rows: list[int] = []
        for row in range(GRID_HEIGHT):
            if all(cell is not None for cell in self.grid[row]):
                cleared_rows.append(row)
        self._last_cleared_rows = cleared_rows

        lines_cleared = len(cleared_rows)
        self.total_lines += lines_cleared
        self.total_lines = min(self.total_lines, _MAX_TOTAL_LINES)

        # 连击（指南标准）：连续消行的第 N 次额外 +50×(N-1)×level，未消行则清零
        if lines_cleared > 0:
            self.combo += 1
            combo_bonus = 50 * (self.combo - 1) * self.level
        else:
            self.combo = 0
            combo_bonus = 0

        # 使用类常量 SCORE_TABLE
        # lines_cleared ∈ 0..4（tetromino 在 10 宽网格中单行至多占 4 格），
        # 直接索引：若未来引入更宽的块导致越界，KeyError 立即暴露而非静默按 4 行计分
        self.add_score(
            TetrisEngine.SCORE_TABLE[lines_cleared] * self.level + combo_bonus
        )

        # 更新等级
        potential_level = (self.total_lines // 10) + 1
        self.level = min(potential_level, _MAX_LEVEL)

        # 从网格中删除满行（从高索引到低索引删除以避免索引错乱），再在顶部插入空行
        if lines_cleared > 0:
            for row in sorted(cleared_rows, reverse=True):
                del self.grid[row]
            for _ in range(lines_cleared):
                self.grid.append([None for _ in range(GRID_WIDTH)])

        self._spawn_piece()

    def reset_lock_delay(self, count: bool = False) -> None:
        """重置贴地计时（成功移动/旋转/切换暂停时调用）。

        :param count: 是否计入 LOCK_RESET_LIMIT 重置预算。仅方块贴地
            （无法下移）时的成功移动/旋转计入——预算约束落地后的微调
            次数；空中移动、暂停、硬降不计。
        """
        if count and self._check_collision(self.x, self.y - 1):
            if self.lock_resets >= LOCK_RESET_LIMIT:
                return  # 预算耗尽：不再重置，计时走完后锁定
            self.lock_resets += 1
        self.resting_since = None

    def handle_resting(self, now: int) -> bool:
        """当前块贴地时推进锁定延迟计时。

        首次调用记录贴地时刻；贴地满 LOCK_DELAY_MS 后返回 True（应由
        调用方锁定）。贴地期间的成功移动/旋转经 reset_lock_delay 重置计时。
        """
        if self.resting_since is None:
            self.resting_since = now
            return False
        if now - self.resting_since >= LOCK_DELAY_MS:
            self.resting_since = None
            return True
        return False

    def get_piece_cells(self) -> list[tuple[int, int]]:
        """返回当前方块各格的绝对坐标（内部底部原点坐标系）。"""
        return [(self.x + dx, self.y + dy) for dx, dy in self.current_shape]

    def get_ghost_y(self) -> int:
        """返回当前方块垂直落到底部后的内部 y（底部为 0）。

        在内部坐标系中，下落方向表示为 y 减小（向下移动使 y 减 1）。
        """
        return drop_y(self.grid, self.current_shape, self.x, self.y)

    # ---------- 消行动画轮询 ----------
    def poll_cleared_rows(self) -> list[int]:
        """返回最近一次消除的行号列表，并清空内部记录。"""
        result = self._last_cleared_rows[:]
        self._last_cleared_rows = []
        return result

    # ---------- 新增：根据等级计算下落速度（毫秒） ----------
    @staticmethod
    def fall_speed(level: int) -> int:
        """返回下落间隔（毫秒），速度随等级线性增加（cells/sec 线性变化）。

        速度范围 2.0～10.0 格/秒，每升一级速度增加量相等。
        """
        # 将常量解释为端点的每格毫秒数。
        # 换算为每秒钟数做插值，使下落速度（格/秒）随等级线性递增，
        # 再换算回毫秒间隔。
        cells_per_sec_min = 1000.0 / _MAX_INITIAL_SPEED   # 例如 2.0 格/秒
        cells_per_sec_max = 1000.0 / _MIN_SPEED           # 例如 10.0 格/秒

        # linear interpolation of cells/sec across levels
        cells_per_sec = (
            cells_per_sec_min
            + (cells_per_sec_max - cells_per_sec_min) * (level - 1) / (_MAX_LEVEL - 1)
        )

        # convert to milliseconds per cell (interval)
        ms_per_cell = 1000.0 / cells_per_sec
        return round(ms_per_cell)
    def _spawn_piece(self) -> None:
        """生成下一个方块到顶部（内部底部原点坐标系），若碰撞则标记游戏结束。"""
        self.current_type = self.next_type
        self.current_shape = list(SHAPES_DATA[self.current_type])
        self.next_type = self._draw_from_bag()
        self.piece_id += 1
        # 新块出生：贴地计时与重置预算清零
        self.resting_since = None
        self.lock_resets = 0

        # 水平居中 spawn（基于 piece 的 bounding box）
        min_px = min(px for px, _ in self.current_shape)
        max_px = max(px for px, _ in self.current_shape)
        piece_width = max_px - min_px + 1
        self.x = (GRID_WIDTH - piece_width) // 2 - min_px

        # 将 piece 的最高单元对齐到顶部（internal top row = GRID_HEIGHT - 1）
        self.y = spawn_y(self.current_shape)

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
          - gy >= GRID_HEIGHT -> 放行（生成区允许超出顶部）
          - 否则如果 grid[gy][gx] 非 None -> collision
        """
        shape = shape if shape is not None else self.current_shape

        return collides(self.grid, nx, ny, shape)

    # ---------- 7-bag 随机生成器 ----------
    def _refill_bag(self) -> None:
        """用全部七种方块填充 bag 并随机打乱。"""
        self._bag = list(_ALL_PIECES)   # 浅拷贝即可，元素为不可变字符串
        shuffle(self._bag)

    def _draw_from_bag(self) -> str:
        """从 bag 顶部取一个方块类型，bag 为空时自动重新填充。"""
        if not self._bag:
            self._refill_bag()
        return self._bag.pop()
