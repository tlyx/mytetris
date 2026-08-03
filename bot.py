# bot.py — 自动游戏机器人，独立于 TetrisApp
# 使用 TetrisEngine 提供的接口进行规划、移动与锁定。
#
# 决策：2-ply 前瞻，一次性求解（无跨帧状态）。对当前块的每个
# (rotation, x) 候选，先把候选落定到盘面快照上形成 post 盘面，再在
# post 盘面上搜索下一块的最佳落点（copy-on-write：写入 → 求值 → 撤销，
# 避免内层深拷贝）。评分 = 当前块落定得分 + 0.5 × 下一块最佳得分。
#
# 求解基于盘面快照与 engine 的共享几何原语（rotate_shape / spawn_y /
# collides / drop_y / cells_in_bounds），碰撞检查作用于模拟盘面而非
# 引擎实时网格，保证 2-ply 模拟语义正确（历史 bug：旧版内层模拟用
# engine.can_place 检查实时网格，与 post 盘面不一致）。

from __future__ import annotations

import copy

from engine import (
    GRID_HEIGHT,
    GRID_WIDTH,
    SHAPES_DATA,
    TetrisEngine,
    cells_in_bounds,
    collides,
    drop_y,
    rotate_shape,
    spawn_y,
)

# 模拟落子时的占位颜色（启发式只关心单元格是否被占用）
_OCCUPIED: tuple[int, int, int] = (1, 1, 1)


def best_move(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
    next_shape: list[tuple[int, int]] | None,
) -> tuple[int, int] | None:
    """2-ply 前瞻求解：返回当前块最优 (rotation, target_x)，无合法落点返回 None。

    对每个 (rotation, x) 候选：
      1. 将候选落定到盘面快照，得到 post 盘面（每候选一次深拷贝）；
      2. 在 post 盘面上穷举下一块的最佳落点（copy-on-write，免内层深拷贝）；
      3. 按 score1 + 0.5 * best_next 选取最优候选。
    """
    best_score = float("-inf")
    best: tuple[int, int] | None = None
    for rotation in range(4):
        piece = rotate_shape(shape, rotation)
        for x in range(GRID_WIDTH):
            y = landing_y(grid, piece, x)
            if y is None:
                continue
            # post 盘面：候选落定后的结果（每候选一次深拷贝）
            post = copy.deepcopy(grid)
            for gx, gy in cells_in_bounds(x, y, piece):
                post[gy][gx] = _OCCUPIED
            score = evaluate(post)
            if next_shape is not None:
                score += 0.5 * best_next(post, next_shape)
            if score > best_score:
                best_score = score
                best = (rotation, x)
    return best


def best_next(
    grid: list[list[tuple[int, int, int] | None]],
    shape: list[tuple[int, int]],
) -> float:
    """在 grid（post 盘面）上穷举下一块的最佳落点得分（copy-on-write）。

    写入仅 4 个单元格，求值后原位撤销，避免为每个内层候选做深拷贝。
    """
    best = float("-inf")
    for rotation in range(4):
        piece = rotate_shape(shape, rotation)
        for x in range(GRID_WIDTH):
            y = landing_y(grid, piece, x)
            if y is None:
                continue
            cells = cells_in_bounds(x, y, piece)
            saved = [grid[gy][gx] for gx, gy in cells]
            for gx, gy in cells:
                grid[gy][gx] = _OCCUPIED
            score = evaluate(grid)
            for (gx, gy), prev in zip(cells, saved):
                grid[gy][gx] = prev
            best = max(best, score)
    return best


def landing_y(
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


def evaluate(grid: list[list[tuple[int, int, int] | None]]) -> float:
    """根据启发式规则返回分数（越高越好）。"""
    heights: list[int] = []
    holes = 0
    bumpiness = 0
    lines = 0

    # 计算完整行数
    for y in range(GRID_HEIGHT):
        if all(cell is not None for cell in grid[y]):
            lines += 1

    # 计算每列高度与空洞（底部原点：grid[0] 为底）
    for x in range(GRID_WIDTH):
        col_height = 0
        block_found = False
        # 从最高行向下扫描（top -> bottom）
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


class Bot:
    """自动方块机器人：2-ply 前瞻求解，逐帧执行计划。"""

    def __init__(self) -> None:
        self._plan: tuple[int, int] | None = None  # (rotation, target_x)
        self._step: int = 0
        self._last_piece_type: str | None = None

    def reset(self) -> None:
        """重置内部状态（当游戏重新开始时调用）。"""
        self._plan = None
        self._step = 0
        self._last_piece_type = None

    def update(self, engine: TetrisEngine) -> None:
        """每帧调用一次，驱动机器人的决策与动作。"""
        if engine.game_over:
            return

        # 检测方块类型变化，重置计划
        if engine.current_type != self._last_piece_type:
            self._plan = None
            self._step = 0
            self._last_piece_type = engine.current_type

        if self._plan is None:
            # 生成新计划（一次性求解，约 20~100ms，单帧内完成）
            shape = SHAPES_DATA[engine.current_type]
            next_shape = SHAPES_DATA.get(engine.next_type)
            self._plan = best_move(engine.grid, shape, next_shape)
            if self._plan is None:
                # 无合法放置；放弃当前尝试，下一帧重试（由重力下落接管）
                return

        rotation, target_x = self._plan

        # ---- 旋转阶段 ----
        if self._step < rotation:
            rotated = engine.rotate()
            if rotated:
                self._step += 1
            else:
                # rotation failed (kicks couldn't resolve) — abandon plan and
                # replan immediately next frame.
                self._plan = None
                self._step = 0
            return

        # ---- 水平移动阶段 ----
        # compute delta in engine-local x (plan stores the desired engine.x)
        # Previously we compared against the piece's min absolute x which caused
        # an off-by-min_px error when min_px != 0. Use engine.x directly.
        dx = target_x - engine.x

        if dx > 0:
            if not engine.move(1, 0):
                # blocked; abandon plan and replan immediately next frame
                self._plan = None
            return

        if dx < 0:
            if not engine.move(-1, 0):
                # blocked; abandon plan and replan immediately next frame
                self._plan = None
            return

        # ---- 硬降 ----
        while engine.move(0, -1):
            pass

        # ---- 锁定并消除行 ----
        engine.lock_and_clear_lines()

        self._plan = None
        self._step = 0
