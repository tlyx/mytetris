# pyright: reportPrivateUsage=false
# test_bot.py — bot 求解器与公平运行器回归测试
# 覆盖 2-ply 前瞻、策略注册表、BotRunner 决策语义与线程生命周期。
#
# 此文件主要负责：
#  - 求解器 / 决策 / 信箱 / 节流 / 线程回归测试

"""Bot 2-ply 前瞻求解器与公平运行器的回归测试。

历史 bug：_best_next 在“当前块落定前”的原始盘面上计算，对每个候选是
常数，因此 0.5 * next 项从不影响决策（前瞻是死代码），且每次落子白付
40×40 次深拷贝。

本测试保护：
  1. 求解结果 = 朴素 2-ply 参考实现（COW 不改变结果）；
  2. 在构造的盘面上决策 != 纯贪心（前瞻确实影响决策）；
  3. 求解不修改外部盘面（COW 撤销正确）；
  4. 无合法落点时返回 None；
  5. 计划 → 动作序列 → 引擎机械，与人类按键等价（旋转/移动/硬降/锁定）；
  6. BotRunner 决策语义：同块不重解、求解期间换块则作废重算；
  7. 信箱 generation / 动作节流 / 线程生命周期。
"""

import copy
import time

import pytest

from actions import Action
from bot import (
    STRATEGIES,
    BotRunner,
    BotSnapshot,
    _best_move,
    _board_features,
    _evaluate,
    _landing_y,
    _Mailbox,
    _plan_to_actions,
)
from engine import (
    GRID_HEIGHT,
    GRID_WIDTH,
    SHAPES_DATA,
    TetrisEngine,
    cells_in_bounds,
    rotate_shape,
)

# ----------------------------------------------------------------------
# 测试盘面构造
# ----------------------------------------------------------------------

def make_engine(
    board: list[list[tuple[int, int, int] | None]],
    current: str,
    next_type: str,
) -> TetrisEngine:
    """构造只读场景：求解函数只读取 grid/current_type/next_type。"""
    eng = TetrisEngine()
    eng.grid = copy.deepcopy(board)
    eng.current_type = current
    eng.next_type = next_type
    return eng


def solve_engine(eng: TetrisEngine) -> tuple[int, int] | None:
    """对引擎当前块做一次 2-ply 求解。"""
    return _best_move(
        eng.grid,
        SHAPES_DATA[eng.current_type],
        SHAPES_DATA.get(eng.next_type),
    )


def well_board() -> list[list[tuple[int, int, int] | None]]:
    """列 5 有深 4 的井，其余列高 8（T 入井 vs 平放留给 I 的经典场景）。"""
    grid: list[list[tuple[int, int, int] | None]] = [
        [None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)
    ]
    for x, height in enumerate((8, 8, 8, 8, 8, 4, 8, 8, 8, 8)):
        for row in range(height):
            grid[row][x] = (1, 1, 1)
    return grid


def no_placement_board() -> list[list[tuple[int, int, int] | None]]:
    """只留顶行空着，任何方块生成即碰撞。"""
    grid: list[list[tuple[int, int, int] | None]] = [
        [(1, 1, 1) for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT - 1)
    ]
    grid.append([None for _ in range(GRID_WIDTH)])
    return grid


# ----------------------------------------------------------------------
# 参考实现（与 bot 共享几何/评估原语，但用朴素深拷贝 + 不同循环结构）
# ----------------------------------------------------------------------

def _naive_place(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
    rotation: int,
    x: int,
) -> tuple[float, list[list[tuple[int, int, int] | None]]] | None:
    """落定 shape 并返回 (得分, post 盘面)；无法放置返回 None。"""
    piece = rotate_shape(shape, rotation)
    y = _landing_y(grid, piece, x)
    if y is None:
        return None
    landing_height = y + min(py for _, py in piece)
    post = copy.deepcopy(grid)
    for gx, gy in cells_in_bounds(x, y, piece):
        post[gy][gx] = (1, 1, 1)
    return _evaluate(post, landing_height), post


def _naive_two_ply(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
    next_shape: list[tuple[int, int]] | None,
) -> tuple[int, int] | None:
    """参考实现：每个候选深拷贝 post 盘面，再在 post 上穷举下一块。"""
    best = float("-inf")
    best_move_: tuple[int, int] | None = None
    for r1 in range(4):
        for x1 in range(GRID_WIDTH):
            res = _naive_place(grid, shape, r1, x1)
            if res is None:
                continue
            s1, post = res
            if next_shape is None:
                total = s1
            else:
                _best_next = float("-inf")
                for r2 in range(4):
                    for x2 in range(GRID_WIDTH):
                        r2v = _naive_place(post, next_shape, r2, x2)
                        if r2v is not None:
                            _best_next = max(_best_next, r2v[0])
                total = s1 + 0.5 * _best_next
            if total > best:
                best = total
                best_move_ = (r1, x1)
    return best_move_


def _greedy(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
) -> tuple[int, int] | None:
    """纯贪心：只按当前块落定的盘面得分选，不看下一块。"""
    best = float("-inf")
    best_move_: tuple[int, int] | None = None
    for r in range(4):
        for x in range(GRID_WIDTH):
            res = _naive_place(grid, shape, r, x)
            if res is not None and res[0] > best:
                best = res[0]
                best_move_ = (r, x)
    return best_move_


# ----------------------------------------------------------------------
# 测试用例
# ----------------------------------------------------------------------

def test_solver_matches_naive_two_ply() -> None:
    eng = make_engine(well_board(), "T", "I")
    plan = solve_engine(eng)
    naive = _naive_two_ply(eng.grid, SHAPES_DATA["T"], SHAPES_DATA["I"])
    assert plan == naive


def lookahead_board() -> list[list[tuple[int, int, int] | None]]:
    """四格基座：y0 填 x0,x1；y1 填 x1,x2（实测第 2 块 I 的天然场景）。"""
    grid: list[list[tuple[int, int, int] | None]] = [
        [None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)
    ]
    grid[0][0] = (1, 1, 1)
    grid[0][1] = (1, 1, 1)
    grid[1][1] = (1, 1, 1)
    grid[1][2] = (1, 1, 1)
    return grid


def test_lookahead_changes_decision() -> None:
    """四格基座 + I + 下一块 Z：贪心竖放左侧 (1,0)，2-ply 平放右侧 (0,7)。"""
    eng = make_engine(lookahead_board(), "I", "Z")
    plan = solve_engine(eng)
    greedy = _greedy(eng.grid, SHAPES_DATA["I"])
    assert greedy == (1, 0)
    assert plan == (0, 7)
    assert plan != greedy  # 前瞻必须真正影响决策（死代码回归保护）


def test_board_features_counts() -> None:
    """特征计数对照：构造已知盘面，逐一验证五个特征的数值。"""
    grid: list[list[tuple[int, int, int] | None]] = [
        [None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)
    ]
    # y=0 全满（完整行 +1）；y=1 只有 x9 空（洞）；y=2 只有 x5 空（洞+井）；
    # y=3 全满（完整行 +1）；y=4..19 全空
    for x in range(GRID_WIDTH):
        grid[0][x] = (1, 1, 1)
        grid[3][x] = (1, 1, 1)
    for x in range(9):
        grid[1][x] = (1, 1, 1)
    for x in range(GRID_WIDTH):
        if x != 5:
            grid[2][x] = (1, 1, 1)

    rows, holes, row_trans, col_trans, wells = _board_features(grid)
    assert rows == 2        # y=0 与 y=3 两行完整
    assert holes == 2       # y=1 x9 与 y=2 x5 上方均有方块
    assert row_trans == 36  # y1:2 + y2:2 + 16 个空行×2
    assert col_trans == 4   # x5 与 x9 两列空洞各进出 2
    assert wells == 1       # y=2 x5 左右均为已填（x9 靠边不计）

    # 落点高度线性惩罚：每高 1 行，得分 -1
    assert _evaluate(grid, 0) == rows - row_trans - col_trans - 4 * holes - wells
    assert _evaluate(grid, 7) == _evaluate(grid, 0) - 7


def test_modern_changes_decision() -> None:
    """对照：同一盘面，Dellacherie 与 legacy 策略的落点不同（换血保护）。"""
    eng = make_engine(well_board(), "T", "I")
    new = solve_engine(eng)
    legacy = _best_move(eng.grid, SHAPES_DATA["T"], SHAPES_DATA["I"], strategy="legacy")
    assert new != legacy
    assert legacy == (0, 8)  # legacy 把 T 平放留井给 I


def test_strategies_registry_and_selection() -> None:
    """策略注册表完整、可切换、未知名称报错；两种策略决策确有差异。"""
    assert set(STRATEGIES) == {"modern", "legacy"}

    eng = make_engine(well_board(), "T", "I")
    plans = {
        name: _best_move(eng.grid, SHAPES_DATA["T"], SHAPES_DATA["I"], strategy=name)
        for name in STRATEGIES
    }
    assert all(p is not None for p in plans.values())
    assert len(set(plans.values())) > 1  # 两种策略落点不全相同

    bot = BotRunner(strategy="legacy")
    assert bot.strategy == "legacy"
    bot.set_strategy("modern")
    assert bot.strategy == "modern"
    assert bot.cycle_strategy() == "legacy"  # modern -> legacy
    assert bot.cycle_strategy() == "modern"
    with pytest.raises(ValueError):
        BotRunner(strategy="nope")
    with pytest.raises(ValueError):
        bot.set_strategy("nope")



    eng = make_engine(well_board(), "T", "I")
    before = copy.deepcopy(eng.grid)
    solve_engine(eng)
    assert eng.grid == before


def test_no_legal_placement_returns_none() -> None:
    eng = make_engine(no_placement_board(), "O", "I")
    assert solve_engine(eng) is None


def make_snapshot(
    eng: TetrisEngine, piece_id: int | None = None
) -> BotSnapshot:
    """从引擎构造投递给 bot 线程的只读快照。

    :param piece_id: 显式指定方块实例 id（默认取引擎当前值；构造
        同类型多块场景时需要不同的 id 来区分）。
    """
    return BotSnapshot(
        grid=[row[:] for row in eng.grid],
        current_type=eng.current_type,
        current_shape=eng.current_shape.copy(),
        current_x=eng.x,
        current_y=eng.y,
        next_type=eng.next_type,
        level=eng.level,
        game_over=eng.game_over,
        piece_id=eng.piece_id if piece_id is None else piece_id,
    )


def apply_actions(eng: TetrisEngine, actions: list[Action]) -> None:
    """模拟主线程逐动作应用（与 TetrisApp._apply_action 的引擎机械一致）。"""
    for action in actions:
        if action == Action.MOVE_LEFT:
            eng.move(-1, 0)
        elif action == Action.MOVE_RIGHT:
            eng.move(1, 0)
        elif action == Action.ROTATE:
            eng.rotate()
        elif action == Action.HARD_DROP:
            eng.hard_drop()
    eng.lock_and_clear_lines()  # _apply_action 硬降路径同此


def test_plan_to_actions_locks_piece() -> None:
    """计划 → 动作序列 → 引擎机械，与人类按键等价（旋转/移动/硬降/锁定）。"""
    eng = TetrisEngine()
    eng.reset()
    plan = _best_move(
        eng.grid,
        SHAPES_DATA[eng.current_type],
        SHAPES_DATA.get(eng.next_type),
    )
    assert plan is not None
    actions = _plan_to_actions(plan, eng.x)
    # 动作序列 = 旋转×n + 水平移动 + 硬降
    assert actions[-1] == Action.HARD_DROP
    assert actions.count(Action.HARD_DROP) == 1
    locked_before = sum(cell is not None for row in eng.grid for cell in row)
    apply_actions(eng, actions)
    locked_after = sum(cell is not None for row in eng.grid for cell in row)
    assert locked_after == locked_before + 4  # 空盘无消行，锁定 4 格


def test_plan_to_actions_sequence() -> None:
    """动作序列方向与数量正确：target_x 偏右→MOVE_RIGHT，偏左→MOVE_LEFT。"""
    assert _plan_to_actions((2, 6), 3) == [
        Action.ROTATE, Action.ROTATE,
        Action.MOVE_RIGHT, Action.MOVE_RIGHT, Action.MOVE_RIGHT,
        Action.HARD_DROP,
    ]
    assert _plan_to_actions((0, 2), 6) == [
        Action.MOVE_LEFT, Action.MOVE_LEFT, Action.MOVE_LEFT, Action.MOVE_LEFT,
        Action.HARD_DROP,
    ]
    assert _plan_to_actions((1, 4), 4) == [Action.ROTATE, Action.HARD_DROP]


def test_decide_same_piece_no_replan() -> None:
    """同一块实例已决策过 → 不再重复求解（动作已在队列里逐帧消费）。"""
    runner = BotRunner()
    snap = make_snapshot(make_engine(well_board(), "T", "I"))
    first = runner._decide(snap)
    assert first  # 产生了动作
    assert all(piece == snap.piece_id for piece, _ in first)
    assert runner._decide(snap) == []


def test_decide_resolves_same_type_new_piece() -> None:
    """同类型连块（7-bag 边界）必须重新求解——历史卡死 bug 回归。

    复现：块 A(T) 计划已产出并被消费锁定，新块恰好也是 T。旧实现按
    方块类型判断"换块"，漏掉同型新块 → bot 对它不动作，干等重力把整块
    掉完才继续。piece_id 每次生成 +1，换块判断必须用它。
    """
    runner = BotRunner()
    snap_a = make_snapshot(make_engine(well_board(), "T", "I"), piece_id=1)
    first = runner._decide(snap_a)
    assert first
    assert all(piece == 1 for piece, _ in first)
    # 同类型、新实例：必须重新求解，不能静默跳过
    snap_a2 = make_snapshot(make_engine(well_board(), "T", "I"), piece_id=2)
    second = runner._decide(snap_a2)
    assert second
    assert all(piece == 2 for piece, _ in second)


def test_decide_invalidated_when_locked_during_think() -> None:
    """求解期间块被重力锁定（快照换块）→ 结果作废，下一轮对最新块重算。"""
    runner = BotRunner()
    snap_a = make_snapshot(make_engine(well_board(), "T", "I"), piece_id=1)
    runner.post_snapshot(snap_a)
    snap_b = make_snapshot(make_engine(well_board(), "O", "I"), piece_id=2)
    runner.post_snapshot(snap_b)
    assert runner._decide(snap_a) == []  # 结果作废
    out = runner._decide(snap_b)
    assert out
    assert all(piece == 2 for piece, _ in out)


def test_decide_no_placement_abandons_piece() -> None:
    """无合法落点 → 放弃本块（不重试求解），等重力锁掉后新块再算。"""
    runner = BotRunner()
    snap = make_snapshot(make_engine(no_placement_board(), "O", "I"))
    assert runner._decide(snap) == []
    assert runner._decide(snap) == []  # 不再重复求解


def test_mailbox_generation_and_wait() -> None:
    """信箱：阻塞等待新一代快照；generation 随投递递增。"""
    mb = _Mailbox()
    assert mb.wait_new(0, timeout=0.01) is None
    snap = make_snapshot(make_engine(well_board(), "T", "I"))
    mb.post(snap)
    assert mb.wait_new(0, timeout=0.01) is snap
    assert mb.generation() == 1
    assert mb.wait_new(1, timeout=0.01) is None  # 无新代 → 超时


def test_decide_drops_stale_actions_on_new_piece() -> None:
    """换块时清空队列里上一块残留的动作（省去主线程逐帧丢弃）。

    旧行为：上一块锁定后，队列里剩余动作由主线程一帧一个地按戳丢弃；
    新行为：bot 检测到换块即清空，队列只含新块的动作。
    """
    runner = BotRunner()
    snap_a = make_snapshot(make_engine(well_board(), "T", "I"), piece_id=1)
    first = runner._decide(snap_a)
    assert first
    for item in first:
        runner._out.put(item)  # 模拟 _loop 入队
    runner._out.get_nowait()  # 消费一个，队列还残留旧块动作
    assert runner._out.qsize() > 0
    snap_b = make_snapshot(make_engine(well_board(), "O", "I"), piece_id=2)
    second = runner._decide(snap_b)
    assert second
    assert all(piece == 2 for piece, _ in second)
    for item in second:
        runner._out.put(item)
    assert runner._out.qsize() == len(second)  # 旧动作已清空


def test_tick_posts_only_on_piece_change() -> None:
    """tick 仅在换块时构造并投递快照（省逐帧拷贝与线程唤醒）。"""
    runner = BotRunner()
    calls: list[int] = []
    snap = make_snapshot(make_engine(well_board(), "T", "I"), piece_id=1)

    def make() -> BotSnapshot:
        calls.append(1)
        return snap

    runner.tick(1, make)
    assert len(calls) == 1
    runner.tick(1, make)  # 同块：不再构造快照
    assert len(calls) == 1
    runner.tick(2, make)  # 换块：构造一次
    assert len(calls) == 2
    assert runner._mailbox.generation() == 2  # 只投递了两次


def test_tick_skips_stale_actions() -> None:
    """tick 跳过过期动作，当帧直接取到当前块的动作（不浪费帧）。"""
    runner = BotRunner()
    runner._out.put((1, Action.ROTATE))      # 过期（旧块）
    runner._out.put((2, Action.MOVE_RIGHT))  # 当前块
    snap = make_snapshot(make_engine(well_board(), "T", "I"), piece_id=2)
    assert runner.tick(2, lambda: snap) == [Action.MOVE_RIGHT]
    assert runner.tick(2, lambda: snap) == []  # 队列已空


def test_tick_throttles_one_action_per_frame() -> None:
    """节流：每帧最多返回 1 个动作，剩余留到后续帧。"""
    runner = BotRunner()
    snap = make_snapshot(make_engine(well_board(), "T", "I"), piece_id=1)
    for _ in range(3):
        runner._out.put((1, Action.ROTATE))
    assert len(runner.tick(1, lambda: snap)) == 1
    assert len(runner.tick(1, lambda: snap)) == 1
    assert len(runner.tick(1, lambda: snap)) == 1
    assert runner.tick(1, lambda: snap) == []


def test_drain_limits() -> None:
    """drain 节流：默认每帧最多 1 个动作。"""
    runner = BotRunner()
    for _ in range(3):
        runner._out.put((1, Action.ROTATE))
    assert len(runner.drain(1)) == 1
    assert len(runner.drain(10)) == 2
    assert runner.drain(10) == []


def test_runner_thread_emits_actions_and_stops() -> None:
    """真线程冒烟：投递快照后产出动作；stop 能干净退出。"""
    runner = BotRunner()
    runner.start()
    try:
        eng = TetrisEngine()
        eng.reset()
        runner.post_snapshot(make_snapshot(eng))
        deadline = time.monotonic() + 2.0
        while runner._out.empty() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert not runner._out.empty()
        piece, action = runner._out.get_nowait()
        assert piece == eng.piece_id
        assert action in (Action.ROTATE, Action.MOVE_LEFT, Action.MOVE_RIGHT,
                          Action.HARD_DROP)
    finally:
        runner.stop()
        assert runner._thread is None
