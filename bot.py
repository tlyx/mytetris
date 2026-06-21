# bot.py — 自动游戏机器人，独立于 TetrisApp
# 使用 TetrisEngine 提供的接口进行规划、移动与锁定。

from __future__ import annotations

import copy
from typing import Optional

from engine import TetrisEngine, GRID_WIDTH, GRID_HEIGHT, SHAPES_DATA


class Bot:
    """具有简单乐高型评估的自动方块机器人。"""

    def __init__(self) -> None:
        self._plan: Optional[tuple[int, int]] = None  # (rotation, target_x)
        self._step: int = 0
        self._last_piece_type: Optional[str] = None

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
            # 生成新计划
            shape = SHAPES_DATA[engine.current_type]
            self._plan = self._solve(engine.grid, shape, engine)

        rotation, target_x = self._plan

        # ---- 旋转阶段 ----
        if self._step < rotation:
            engine.rotate()
            self._step += 1
            return

        # ---- 水平移动阶段 ----
        piece_cells = engine.get_piece_cells()
        if not piece_cells:
            return
        min_x = min(x for x, _ in piece_cells)
        dx = target_x - min_x

        if dx > 0:
            if not engine.move(1, 0):
                self._plan = None
            return

        if dx < 0:
            if not engine.move(-1, 0):
                self._plan = None
            return

        # ---- 硬降 ----
        while engine.move(0, 1):
            pass

        # ---- 锁定并消除行 ----
        engine.lock_and_clear_lines()

        self._plan = None
        self._step = 0

    # ------------------------------------------------------------------
    #  以下为启发式搜索与评估函数（从原 TetrisApp 直接迁移而来）
    # ------------------------------------------------------------------

    def _solve(
        self,
        grid: list[list[Optional[tuple[int, int, int]]]],
        shape: list[tuple[int, int]],
        engine: TetrisEngine,
    ) -> tuple[int, int]:
        """返回最佳移动 (rotation, target_x)。"""
        next_type = getattr(engine, "next_type", None)
        next_shape: Optional[list[tuple[int, int]]] = (
            SHAPES_DATA.get(next_type) if next_type else None
        )

        best_score: float = float("-inf")
        best_move: tuple[int, int] = (0, GRID_WIDTH // 2)

        for rotation1 in range(4):
            for x1 in range(GRID_WIDTH):
                score1 = self._simulate(grid, shape, rotation1, x1)
                if score1 is None:
                    continue

                # 如果没有下一块信息，则采用贪心
                if not next_shape:
                    total: float = score1
                else:
                    best_next: float = float("-inf")
                    for rotation2 in range(4):
                        for x2 in range(GRID_WIDTH):
                            score2 = self._simulate(grid, next_shape, rotation2, x2)
                            if score2 is None:
                                continue
                            if score2 > best_next:
                                best_next = score2
                    total = score1 + 0.5 * best_next

                if total > best_score:
                    best_score = total
                    best_move = (rotation1, x1)

        return best_move

    def _simulate(
        self,
        grid: list[list[Optional[tuple[int, int, int]]]],
        shape: list[tuple[int, int]],
        rotation: int,
        target_x: int,
    ) -> Optional[float]:
        """模拟放置并返回评估分数；若无法放置则返回 None。"""
        piece = list(shape)

        # 旋转
        for _ in range(rotation):
            piece = [(-py, px) for px, py in piece]

        # 归一化
        min_x = min(px for px, _ in piece)
        min_y = min(py for _, py in piece)
        piece = [(px - min_x, py - min_y) for px, py in piece]

        # 限制 x 在合法范围内
        target_x = max(0, min(GRID_WIDTH - 1, target_x))

        max_px = max(px for px, _ in piece)
        if target_x + max_px >= GRID_WIDTH:
            return None

        # 检查生成位置是否有碰撞
        if self._collides(grid, piece, target_x, 0):
            return None

        # 模拟下落
        y = 0
        while not self._collides(grid, piece, target_x, y + 1):
            y += 1

        new_grid: list[list[Optional[tuple[int, int, int]]]] = copy.deepcopy(grid)
        for px, py in piece:
            gx = target_x + px
            gy = y + py
            if 0 <= gx < GRID_WIDTH and 0 <= gy < GRID_HEIGHT:
                new_grid[gy][gx] = (1, 1, 1)  # 占位符，仅关心被占用

        return self._evaluate_grid(new_grid)

    @staticmethod
    def _collides(
        grid: list[list[Optional[tuple[int, int, int]]]],
        piece: list[tuple[int, int]],
        x: int,
        y: int,
    ) -> bool:
        """检查某个位置是否与已有方块或边界冲突。"""
        for px, py in piece:
            gx = x + px
            gy = y + py

            if gx < 0 or gx >= GRID_WIDTH:
                return True
            if gy >= GRID_HEIGHT:
                return True
            if gy >= 0 and grid[gy][gx] is not None:
                return True
        return False

    @staticmethod
    def _evaluate_grid(
        grid: list[list[Optional[tuple[int, int, int]]]],
    ) -> float:
        """根据启发式规则返回分数（越高越好）。"""
        heights: list[int] = []
        holes = 0
        bumpiness = 0
        lines = 0

        # 计算完整行数
        for y in range(GRID_HEIGHT):
            if all(cell is not None for cell in grid[y]):
                lines += 1

        # 计算每列高度与空洞
        for x in range(GRID_WIDTH):
            col_height = 0
            block_found = False
            for y in range(GRID_HEIGHT):
                if grid[y][x] is not None:
                    if not block_found:
                        col_height = GRID_HEIGHT - y
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
