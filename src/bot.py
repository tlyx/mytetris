# bot.py — 自动游戏机器人，独立于 TetrisApp
#
# 公平性设计：bot 不再直连引擎。游戏主循环每帧调用一次 BotRunner.tick()
# 传入当前方块 id 与快照工厂，取回可应用的按键动作（Action）；内部换块
# 投递、节流、过期丢弃全部封装。动作经 TetrisApp._apply_action 喂进与
# 人类键盘完全相同的输入路径。重力、锁定延迟、计分对 bot 一视同仁；
# 求解期间若块已被重力锁定，放弃结果对新块重算——像真正的人一样：
# 想太久，方块自己掉下去锁掉。
#
# 对外 API（游戏主体只依赖这些）：
#   - BotInterface : TetrisApp 依赖的协议（可整体替换 bot 实现）
#   - BotRunner    : 具体实现（组合点在 TetrisApp._init_bot）
#   - BotSnapshot  : 游戏侧构造的只读状态快照
#   - STRATEGIES / DEFAULT_STRATEGY : 评估策略的可配置行为
#
# 其余模块级求解函数均为私有（_ 前缀）实现细节，仅供 BotRunner 内部
# 与白盒测试使用，不属于对外接口。
#
# 此文件主要负责：
#  - 2-ply 前瞻求解与评估策略注册表
#  - BotRunner 独立线程调度（快照信箱 / 动作队列 / 生命周期）
#  - 对外接口（BotInterface / BotSnapshot / BotRunner）
#
# 评估策略可选用（STRATEGIES 注册表，构造参数或 set_strategy /
# cycle_strategy 切换）：
#   - modern（默认）：经典 Dellacherie 特征（landing height / 消行 /
#     行过渡 / 列过渡 / 空洞 / 井深和），重存活、稳如老狗；
#   - legacy：Dellacherie 之前的手调启发式，清行更大胆（Tetris 略多
#     但更早顶死）。
#
# 注：曾尝试"挖井攒 Tetris"（hunter）策略——任何井奖励（井深和/最大
# 井深/锚定井深）都会在 2-ply 内层搜索中把空盘决策翻成靠边竖放，级联
# 成乱堆秒死。挖井策略本质需要知道 I 何时到来（bag 前瞻），单格预览
# 的加法特征表达不了，故不提供该策略。
#
# 求解基于盘面快照与 engine 的共享几何原语（rotate_shape / spawn_y /
# collides / drop_y / cells_in_bounds），碰撞检查作用于模拟盘面而非
# 引擎实时网格，保证 2-ply 模拟语义正确（历史 bug：旧版内层模拟用
# 引擎实时网格检查与 post 盘面不一致）。

import copy
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, final

from actions import Action
from engine import (
    GRID_HEIGHT,
    GRID_WIDTH,
    SHAPES_DATA,
    cells_in_bounds,
    collides,
    drop_y,
    rotate_shape,
    spawn_y,
)

# 模拟落子时的占位颜色（启发式只关心单元格是否被占用）
_OCCUPIED: tuple[int, int, int] = (1, 1, 1)

# 默认评估策略（见 STRATEGIES 注册表）
DEFAULT_STRATEGY = "modern"


# ------------------------------------------------------------------
# 内部求解器（私有实现细节，仅 BotRunner 内部与白盒测试使用）
# ------------------------------------------------------------------

def _best_move(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
    next_shape: list[tuple[int, int]] | None,
    strategy: str = DEFAULT_STRATEGY,
) -> tuple[int, int] | None:
    """2-ply 前瞻求解：返回当前块最优 (rotation, target_x)，无合法落点返回 None。

    对每个 (rotation, x) 候选：
      1. 将候选落定到盘面快照，得到 post 盘面（每候选一次深拷贝）；
      2. 在 post 盘面上穷举下一块的最佳落点（copy-on-write，免内层深拷贝）；
      3. 按 score1 + 0.5 * _best_next 选取最优候选。

    :param strategy: 评估策略名（见 STRATEGIES），默认 modern。
    """
    scorer = _get_strategy(strategy)
    best_score = float("-inf")
    best: tuple[int, int] | None = None
    for rotation in range(4):
        piece = rotate_shape(shape, rotation)
        for x in range(GRID_WIDTH):
            y = _landing_y(grid, piece, x)
            if y is None:
                continue
            landing_height = y + min(py for _, py in piece)
            # post 盘面：候选落定后的结果（每候选一次深拷贝）
            post = copy.deepcopy(grid)
            for gx, gy in cells_in_bounds(x, y, piece):
                post[gy][gx] = _OCCUPIED
            score = scorer(post, landing_height)
            if next_shape is not None:
                score += 0.5 * _best_next(post, next_shape, scorer)
            if score > best_score:
                best_score = score
                best = (rotation, x)
    return best


def _best_next(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
    scorer: Callable[[list[list[tuple[int, int, int] | None]], int], float],
) -> float:
    """在 grid（post 盘面）上穷举下一块的最佳落点得分（copy-on-write）。

    写入仅 4 个单元格，求值后原位撤销，避免为每个内层候选做深拷贝。
    """
    best = float("-inf")
    for rotation in range(4):
        piece = rotate_shape(shape, rotation)
        for x in range(GRID_WIDTH):
            y = _landing_y(grid, piece, x)
            if y is None:
                continue
            landing_height = y + min(py for _, py in piece)
            cells = cells_in_bounds(x, y, piece)
            saved = [grid[gy][gx] for gx, gy in cells]
            for gx, gy in cells:
                grid[gy][gx] = _OCCUPIED
            score = scorer(grid, landing_height)
            for (gx, gy), prev in zip(cells, saved):
                grid[gy][gx] = prev
            best = max(best, score)
    return best


def _landing_y(
    grid: list[list[tuple[int, int, int] | None]],
    piece: list[tuple[int, int]],
    x: int,
) -> int | None:
    """返回 piece 落在 x 列的最终 y（底部原点）；无法放置返回 None。

    与引擎生成位/碰撞/下落规则共用 engine.collides / drop_y / spawn_y；
    碰撞检查作用于传入的模拟盘面（而非引擎实时网格）。
    """
    min_px = min(px for px, _ in piece)
    max_px = max(px for px, _ in piece)
    if x + min_px < 0 or x + max_px >= GRID_WIDTH:
        return None
    y = spawn_y(piece)
    if collides(grid, x, y, piece):
        return None
    return drop_y(grid, piece, x, y)


def _board_features(
    grid: list[list[tuple[int, int, int] | None]],
) -> tuple[int, int, int, int, int]:
    """统计盘面特征，返回 (完整行数, 空洞数, 行过渡数, 列过渡数, 井深和)。

    行过渡：同一行内 填/空 相邻变化次数，左右边界视为已填。
    列过渡：同一列内 填/空 相邻变化次数，列顶以上的“天空”视为已填
            （空洞在列过渡中体现为 +2，实心列过渡为 0）。
    井：空单元格左右相邻均为已填（列内连续井单元格累加为井深和）。
    """
    rows_cleared = 0
    holes = 0
    row_transitions = 0
    column_transitions = 0
    well_sums = 0

    # 完整行数与行过渡（左右边界视为已填）
    for y in range(GRID_HEIGHT):
        row = grid[y]
        if all(cell is not None for cell in row):
            rows_cleared += 1
        prev = True
        for cell in row:
            filled = cell is not None
            if filled != prev:
                row_transitions += 1
            prev = filled
        if not prev:
            row_transitions += 1

    # 列过渡、空洞、井（逐列扫描）
    for x in range(GRID_WIDTH):
        in_stack = False
        prev = True  # 顶部天空视为已填
        for y in range(GRID_HEIGHT - 1, -1, -1):
            filled = grid[y][x] is not None
            if filled:
                in_stack = True
            cur = filled or not in_stack  # 天空视为已填
            if cur != prev:
                column_transitions += 1
            prev = cur

        in_stack = False
        for y in range(GRID_HEIGHT - 1, -1, -1):
            if grid[y][x] is not None:
                in_stack = True
            elif in_stack:
                holes += 1

        if 0 < x < GRID_WIDTH - 1:
            for y in range(GRID_HEIGHT):
                if (
                    grid[y][x] is None
                    and grid[y][x - 1] is not None
                    and grid[y][x + 1] is not None
                ):
                    well_sums += 1

    return rows_cleared, holes, row_transitions, column_transitions, well_sums


def _evaluate(
    grid: list[list[tuple[int, int, int] | None]],
    landing_height: int,
) -> float:
    """Pierre Dellacherie 评估（越高越好）。

    landing_height：落点高度（方块最低单元格距底部的行数，贴底为 0），
    由调用方在落定模拟时计算并传入。

    权重来自经典 Dellacherie 单块算法：
        -1 × landing_height
        +1 × 已消除行数
        -1 × 行过渡
        -1 × 列过渡
        -4 × 空洞
        -1 × 井深和

    旧版启发式（lines*800 - aggregate_height*6 - holes*120 - bumpiness*4
    - max_height*2 - |中心列偏移|*3）已由本函数替换，原实现保留如下：
    """
    rows_cleared, holes, row_trans, col_trans, well_sums = _board_features(grid)
    return (
        -1.0 * landing_height
        + 1.0 * rows_cleared
        - 1.0 * row_trans
        - 1.0 * col_trans
        - 4.0 * holes
        - 1.0 * well_sums
    )


def _column_heights(
    grid: list[list[tuple[int, int, int] | None]],
) -> list[int]:
    """返回每列高度（底部原点，空列高度为 0）。"""
    return [
        max(
            (y + 1 for y in range(GRID_HEIGHT) if grid[y][x] is not None),
            default=0,
        )
        for x in range(GRID_WIDTH)
    ]


def _legacy_evaluate(
    grid: list[list[tuple[int, int, int] | None]],
    _landing_height: int,
) -> float:
    """旧版启发式（Dellacherie 替换前的公式，保留为可选策略）。

    与 Dellacherie 不同：无落点高度惩罚（参数保留以统一 STRATEGIES 签名，
    未使用，故以下划线命名），权重手调，中间堆高倾向明显、清行更大胆
    （Tetris 略多但更早顶死）。
    """
    heights = _column_heights(grid)
    holes = 0
    lines = 0
    for y in range(GRID_HEIGHT):
        if all(cell is not None for cell in grid[y]):
            lines += 1
    for x in range(GRID_WIDTH):
        block_found = False
        for y in range(GRID_HEIGHT - 1, -1, -1):
            if grid[y][x] is not None:
                block_found = True
            elif block_found:
                holes += 1

    bumpiness = sum(abs(heights[i] - heights[i + 1]) for i in range(GRID_WIDTH - 1))
    aggregate_height = sum(heights)
    max_height = max(heights)
    return (
        lines * 800
        - aggregate_height * 6
        - holes * 120
        - bumpiness * 4
        - max_height * 2
        - abs(GRID_WIDTH // 2 - heights.index(max_height)) * 3
    )


# ------------------------------------------------------------------
# 策略注册表（公开：bot 的可配置行为；BotRunner 构造参数与 cycle_strategy 使用）
# ------------------------------------------------------------------
# 评估策略注册表：名称 -> 评分函数 (grid, landing_height) -> float
STRATEGY_ORDER: tuple[str, ...] = ("modern", "legacy")
STRATEGIES: dict[str, Callable[[list[list[tuple[int, int, int] | None]], int], float]] = {
    "modern": _evaluate,
    "legacy": _legacy_evaluate,
}


def _get_strategy(
    name: str,
) -> Callable[[list[list[tuple[int, int, int] | None]], int], float]:
    """按名称取评估策略；未知名称抛 ValueError。"""
    if name not in STRATEGIES:
        raise ValueError(f"未知 bot 策略: {name!r}，可用: {sorted(STRATEGIES)}")
    return STRATEGIES[name]


def _plan_to_actions(
    plan: tuple[int, int], current_x: int, current_rotation: int
) -> list[Action]:
    """把 (rotation, target_x) 计划翻译成按键动作序列（旋转→水平→硬降）。

    :param current_x: 快照中当前块的 engine-local x，用于计算水平移动量。
    :param current_rotation: 快照中当前旋转状态 0..3；旋转按键按相对量
        计算（(目标 - 当前) % 4），中途接管（方块已被转过）也能正确执行。
    """
    target_rotation, target_x = plan
    actions: list[Action] = [Action.ROTATE] * (
        (target_rotation - current_rotation) % 4
    )
    dx = target_x - current_x
    if dx > 0:
        actions.extend([Action.MOVE_RIGHT] * dx)
    elif dx < 0:
        actions.extend([Action.MOVE_LEFT] * (-dx))
    actions.append(Action.HARD_DROP)
    return actions


# ------------------------------------------------------------------
# 对外接口（游戏主体依赖的部分）
# ------------------------------------------------------------------

@dataclass(frozen=True)
class BotSnapshot:
    """游戏侧构造、bot 侧消费的只读游戏状态快照（grid 为行拷贝）。"""

    grid: list[list[tuple[int, int, int] | None]]
    current_type: str
    current_x: int
    # 当前旋转状态 0..3（_plan_to_actions 按相对量计算按键次数）
    rotation: int
    next_type: str
    level: int
    game_over: bool
    # 当前方块实例 id（引擎每次生成新块 +1）：同一类型但不同的块 id 不同，
    # 是 bot 识别"换块了"的可靠依据（方块类型可能连续相同）。
    piece_id: int


@final
class _Mailbox:
    """单槽快照信箱：主线程投递，bot 线程阻塞等待新一代快照。

    generation 随每次投递递增，用于检测"求解期间状态已变"。
    """

    _cond: threading.Condition
    _latest: BotSnapshot | None
    _generation: int

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._latest = None
        self._generation = 0

    def post(self, snap: BotSnapshot) -> None:
        """投递最新快照（主线程调用，覆盖旧值）。"""
        with self._cond:
            self._latest = snap
            self._generation += 1
            self._cond.notify_all()

    def latest(self) -> BotSnapshot | None:
        """返回当前最新快照（bot 线程调用）。"""
        with self._cond:
            return self._latest

    def generation(self) -> int:
        with self._cond:
            return self._generation

    def wait_new(self, seen: int, timeout: float = 0.05) -> BotSnapshot | None:
        """阻塞直到出现 generation > seen 的新快照；超时返回 None。"""
        with self._cond:
            while self._latest is None or self._generation <= seen:
                if not self._cond.wait(timeout):
                    return None
            return self._latest


class BotInterface(Protocol):
    """游戏主体依赖的 bot 接口（可整体替换实现）。

    TetrisApp 只依赖此协议：换 bot 实现（如深度强化学习版）时，
    提供同接口即可，游戏代码零改动。
    """

    @property
    def strategy(self) -> str: ...

    def start(self) -> None: ...
    def stop(self, timeout: float = 1.0) -> None: ...
    def cycle_strategy(self) -> str: ...
    def tick(
        self,
        current_piece_id: int,
        make_snapshot: Callable[[], BotSnapshot],
    ) -> list[Action]: ...


@final
class BotRunner:
    """公平 bot：独立线程，只读快照，输出按键动作（与人类同一输入路径）。

    游戏侧每帧只调用 tick()：传入当前方块 id 与快照工厂，取回可应用
    的动作。换块投递、队列消费、过期动作丢弃等内部机制全部封装在
    runner 内部，TetrisApp 不感知。

    :param strategy: 评估策略名（见 STRATEGIES），默认 modern。
    """

    _strategy: str
    _mailbox: _Mailbox
    _out: queue.Queue[tuple[int, Action]]
    _stop: threading.Event
    _thread: threading.Thread | None
    _plan_piece_id: int | None  # 当前计划针对的方块实例 id
    _last_posted_id: int | None  # 上次投递给 bot 的方块实例 id（换块才投递）

    def __init__(self, strategy: str = DEFAULT_STRATEGY) -> None:
        if strategy not in STRATEGIES:
            raise ValueError(f"未知 bot 策略: {strategy!r}，可用: {sorted(STRATEGIES)}")
        self._strategy = strategy
        self._mailbox = _Mailbox()
        self._out = queue.Queue()
        self._stop = threading.Event()
        self._thread = None
        self._plan_piece_id = None
        self._last_posted_id = None

    # ---------- 策略管理（主线程调用） ----------
    @property
    def strategy(self) -> str:
        """当前评估策略名。"""
        return self._strategy

    def set_strategy(self, strategy: str) -> None:
        """切换评估策略；作废当前计划，下块按新策略重解。"""
        if strategy not in STRATEGIES:
            raise ValueError(f"未知 bot 策略: {strategy!r}，可用: {sorted(STRATEGIES)}")
        if strategy != self._strategy:
            self._strategy = strategy
            self._plan_piece_id = None  # 跨线程赋值，GIL 下原子，竞态无碍

    def cycle_strategy(self) -> str:
        """按 STRATEGY_ORDER 循环切换策略，返回新策略名。"""
        order = STRATEGY_ORDER
        self.set_strategy(order[(order.index(self._strategy) + 1) % len(order)])
        return self._strategy

    # ---------- 生命周期 ----------
    def start(self) -> None:
        """启动 bot 线程（幂等）。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        # 用局部变量承载线程对象：PyCharm 对实例属性赋值后的收窄不可靠，
        # 直接 self._thread.start() 会被按 Thread | None 判定告警。
        thread = threading.Thread(target=self._loop, name="mytetris-bot", daemon=True)
        self._thread = thread
        thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        """停止 bot 线程并等待退出（幂等）。"""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    # ---------- 主线程接口 ----------
    def tick(
        self,
        current_piece_id: int,
        make_snapshot: Callable[[], BotSnapshot],
    ) -> list[Action]:
        """游戏主循环每帧调用一次：取回可应用的动作（≤1 个）。

        内部封装：
          - 换块（current_piece_id 变化）才构造并投递快照，避免逐帧拷贝与
            线程唤醒；
          - 丢弃针对已消失方块（piece_id 戳不匹配）的过期动作。

        :param current_piece_id: 引擎当前方块实例 id。
        :param make_snapshot: 快照工厂（仅换块时调用一次）。
        :return: 保证针对当前方块的动作列表（长度 ≤1）。
        """
        if current_piece_id != self._last_posted_id:
            self._last_posted_id = current_piece_id
            self._mailbox.post(make_snapshot())
        actions: list[Action] = []
        while len(actions) < 1:  # 节流：每帧最多 1 个可应用动作
            try:
                piece, action = self._out.get_nowait()
            except queue.Empty:
                break
            if piece == current_piece_id:
                actions.append(action)
            # 过期动作直接丢弃，继续取下一个，不浪费本帧
        return actions

    # ---------- bot 线程 ----------
    def _loop(self) -> None:
        seen = 0
        while not self._stop.is_set():
            snap = self._mailbox.wait_new(seen)
            if snap is None:
                continue
            seen = self._mailbox.generation()
            for item in self._decide(snap):
                self._out.put(item)

    def _decide(self, snap: BotSnapshot) -> list[tuple[int, Action]]:
        """对快照决定动作序列（纯逻辑，可单测；空列表 = 无需处理）。

        - 同一块实例已决策过 → 不重复求解（动作已在队列里被主线程逐帧消费）；
        - 求解完成时若快照已换块（求解期间被重力锁定）→ 放弃，下轮重算；
        - 无合法落点 → 放弃本块，等它被重力锁掉，新块再算。

        换块判断用 piece_id（引擎每次生成新块 +1），而不是方块类型——
        7-bag 边界处可能连续出现同类型方块，按类型判断会漏掉换块，
        导致 bot 对整块新方块不动作、干等重力把它掉完（历史 bug）。

        换块时顺带清空队列里上一块残留的动作（上一块已锁定/被重力带
        走）：主线程不必再逐帧丢弃过期动作；piece_id 戳校验仍保留兜底。
        """
        if snap.game_over:
            return []
        if snap.piece_id == self._plan_piece_id:
            return []
        self._drop_pending()
        plan = _best_move(
            snap.grid,
            SHAPES_DATA[snap.current_type],
            SHAPES_DATA.get(snap.next_type),
            self._strategy,
        )
        latest = self._mailbox.latest()
        if latest is not None and latest.piece_id != snap.piece_id:
            return []  # 求解期间换块：结果作废，下一轮对最新块重算
        self._plan_piece_id = snap.piece_id
        if plan is None:
            return []
        return [
            (snap.piece_id, action)
            for action in _plan_to_actions(plan, snap.current_x, snap.rotation)
        ]

    def _drop_pending(self) -> None:
        """清空尚未被主线程消费的动作（换块时调用）。

        队列里只会存在针对 _plan_piece_id 的动作；换块后它们全部过期。
        """
        while True:
            try:
                self._out.get_nowait()
            except queue.Empty:
                return
