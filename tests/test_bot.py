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

from bot import Bot, best_move, board_features, evaluate, landing_y
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
    landing_height = y + min(py for _, py in piece)
    post = copy.deepcopy(grid)
    for gx, gy in cells_in_bounds(x, y, piece):
        post[gy][gx] = (1, 1, 1)
    return evaluate(post, landing_height), post


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

    rows, holes, row_trans, col_trans, wells = board_features(grid)
    assert rows == 2        # y=0 与 y=3 两行完整
    assert holes == 2       # y=1 x9 与 y=2 x5 上方均有方块
    assert row_trans == 36  # y1:2 + y2:2 + 16 个空行×2
    assert col_trans == 4   # x5 与 x9 两列空洞各进出 2
    assert wells == 1       # y=2 x5 左右均为已填（x9 靠边不计）

    # 落点高度线性惩罚：每高 1 行，得分 -1
    assert evaluate(grid, 0) == rows - row_trans - col_trans - 4 * holes - wells
    assert evaluate(grid, 7) == evaluate(grid, 0) - 7


def _legacy_evaluate(
    grid: list[list[tuple[int, int, int] | None]],
) -> float:
    """旧版启发式（被 Dellacherie 替换前），用于对照决策差异。"""
    heights: list[int] = []
    holes = 0
    bumpiness = 0
    lines = 0
    for y in range(GRID_HEIGHT):
        if all(cell is not None for cell in grid[y]):
            lines += 1
    for x in range(GRID_WIDTH):
        col_height = 0
        block_found = False
        for y in range(GRID_HEIGHT - 1, -1, -1):
            if grid[y][x] is not None:
                if not block_found:
                    col_height = y + 1
                    block_found = True
            else:
                if block_found:
                    holes += 1
        heights.append(col_height)
    for i in range(GRID_WIDTH - 1):
        bumpiness += abs(heights[i] - heights[i + 1])
    aggregate_height = sum(heights)
    max_height = max(heights)
    return (
        lines * 800
        - aggregate_height * 6
        - holes * 120
        - bumpiness * 4
        - max_height * 2
        - abs(GRID_WIDTH // 2 - heights.index(max(heights))) * 3
    )


def _legacy_best(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
    next_shape: list[tuple[int, int]] | None,
) -> tuple[int, int] | None:
    """用旧启发式 + 朴素深拷贝跑 2-ply，与 Dellacherie 版对照。"""
    best = float("-inf")
    best_move_: tuple[int, int] | None = None
    for r1 in range(4):
        for x1 in range(GRID_WIDTH):
            res = _naive_place_legacy(grid, shape, r1, x1)
            if res is None:
                continue
            s1, post = res
            if next_shape is None:
                total = s1
            else:
                best_next_ = float("-inf")
                for r2 in range(4):
                    for x2 in range(GRID_WIDTH):
                        r2v = _naive_place_legacy(post, next_shape, r2, x2)
                        if r2v is not None:
                            best_next_ = max(best_next_, r2v[0])
                total = s1 + 0.5 * best_next_
            if total > best:
                best = total
                best_move_ = (r1, x1)
    return best_move_


def _naive_place_legacy(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
    rotation: int,
    x: int,
) -> tuple[float, list[list[tuple[int, int, int] | None]]] | None:
    """旧启发式版落定模拟（仅用于 _legacy_best 对照）。"""
    piece = rotate_shape(shape, rotation)
    y = landing_y(grid, piece, x)
    if y is None:
        return None
    post = copy.deepcopy(grid)
    for gx, gy in cells_in_bounds(x, y, piece):
        post[gy][gx] = (1, 1, 1)
    return _legacy_evaluate(post), post


def test_dellacherie_changes_decision() -> None:
    """对照：同一盘面，Dellacherie 与旧启发式的落点不同（换血保护）。"""
    eng = make_engine(well_board(), "T", "I")
    new = solve_engine(eng)
    legacy = _legacy_best(eng.grid, SHAPES_DATA["T"], SHAPES_DATA["I"])
    assert new != legacy
    assert legacy == (0, 8)  # 旧启发式把 T 平放留井给 I



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
