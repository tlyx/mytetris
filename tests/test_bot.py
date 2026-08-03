# pyright: reportPrivateUsage=false
"""Bot 2-ply 前瞻求解器的回归测试。

历史 bug：best_next 在“当前块落定前”的原始盘面上计算，对每个候选是
常数，因此 0.5 * next 项从不影响决策（前瞻是死代码），且每次落子白付
40×40 次深拷贝。

本测试保护：
  1. 求解结果 = 朴素 2-ply 参考实现（COW 不改变结果）；
  2. 在构造的盘面上决策 != 纯贪心（前瞻确实影响决策）；
  3. 求解不修改外部盘面（COW 撤销正确）；
  4. 无合法落点时返回 None；
  5. bot.update 端到端驱动引擎完成一次落子锁定。
"""

from __future__ import annotations

import copy

from bot import Bot, best_move, evaluate, landing_y
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
    return best_move(
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
    y = landing_y(grid, piece, x)
    if y is None:
        return None
    post = copy.deepcopy(grid)
    for gx, gy in cells_in_bounds(x, y, piece):
        post[gy][gx] = (1, 1, 1)
    return evaluate(post), post


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
                best_next = float("-inf")
                for r2 in range(4):
                    for x2 in range(GRID_WIDTH):
                        r2v = _naive_place(post, next_shape, r2, x2)
                        if r2v is not None:
                            best_next = max(best_next, r2v[0])
                total = s1 + 0.5 * best_next
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


def test_lookahead_changes_decision() -> None:
    """井 + T + 下一块 I：贪心把 T 塞进井 (2,5)，2-ply 平放留井 (0,8)。"""
    eng = make_engine(well_board(), "T", "I")
    plan = solve_engine(eng)
    greedy = _greedy(eng.grid, SHAPES_DATA["T"])
    assert greedy == (2, 5)
    assert plan == (0, 8)
    assert plan != greedy  # 前瞻必须真正影响决策（死代码回归保护）


def test_solver_does_not_mutate_board() -> None:
    eng = make_engine(well_board(), "T", "I")
    before = copy.deepcopy(eng.grid)
    solve_engine(eng)
    assert eng.grid == before


def test_no_legal_placement_returns_none() -> None:
    eng = make_engine(no_placement_board(), "O", "I")
    assert solve_engine(eng) is None


def test_bot_update_executes_plan_to_lock() -> None:
    """端到端：bot.update 逐帧驱动 求解→旋转→水平移动→硬降→锁定。

    执行阶段每帧只推进一格（旋转/移动），锁定发生在最后的硬降帧。
    """
    eng = TetrisEngine()
    eng.reset()
    bot = Bot()
    locked_before = sum(
        cell is not None for row in eng.grid for cell in row
    )
    for _ in range(200):
        bot.update(eng)
        locked_now = sum(cell is not None for row in eng.grid for cell in row)
        if locked_now > locked_before:
            break
    assert bot._plan is None
    locked_after = sum(cell is not None for row in eng.grid for cell in row)
    assert locked_after == locked_before + 4  # 空盘无消行，锁定 4 格
