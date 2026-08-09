# pyright: reportPrivateUsage=false
# test_engine_extra.py — 引擎扩展行为与共享几何原语契约测试
# 覆盖 wall-kick、多行消分、Game Over、纯几何函数契约。

from engine import (
    _WALL_KICKS_I,
    _WALL_KICKS_OTHERS,
    GRID_HEIGHT,
    GRID_WIDTH,
    LOCK_DELAY_MS,
    LOCK_RESET_LIMIT,
    MAX_SCORE,
    SHAPES_DATA,
    GameEngine,
    cells_in_bounds,
    collides,
    drop_y,
    rotate_shape,
    spawn_y,
)

# SHAPES_DATA was previously imported but is not needed here

def make_empty_engine():
    eng = GameEngine()
    eng.reset()
    return eng


def test_rotate_fails_when_blocked():
    eng = make_empty_engine()
    eng.next_type = "T"
    eng._spawn_piece()
    old_shape = list(eng.current_shape)
    old_rot = eng.rotation

    # compute the rotated shape as engine does
    new_shape = [(-dy, dx) for dx, dy in eng.current_shape]

    # choose kick set
    kicks = _WALL_KICKS_I if eng.current_type == "I" else _WALL_KICKS_OTHERS

    # Fill the grid at all candidate positions for the rotated shape with each kick
    for ox, oy in kicks:
        for dx, dy in new_shape:
            tx = eng.x + ox + dx
            ty = eng.y + oy + dy
            if 0 <= tx < GRID_WIDTH and 0 <= ty < GRID_HEIGHT:
                eng.grid[ty][tx] = (9, 9, 9)

    eng.rotate()
    # rotation should not have been applied
    assert eng.current_shape == old_shape
    assert eng.rotation == old_rot


def test_rotation_uses_kicks_to_succeed():
    eng = make_empty_engine()
    eng.next_type = "J"
    eng._spawn_piece()
    old_x = eng.x
    old_rot = eng.rotation

    new_shape = [(-dy, dx) for dx, dy in eng.current_shape]
    # block the direct rotation at (0,0) but leave the (1,0) kick free
    # fill direct positions
    for dx, dy in new_shape:
        tx = eng.x + dx
        ty = eng.y + dy
        if 0 <= tx < GRID_WIDTH and 0 <= ty < GRID_HEIGHT:
            eng.grid[ty][tx] = (8, 8, 8)

    # ensure kick (1,0) positions are free
    kick_ok = True
    for dx, dy in new_shape:
        tx = eng.x + 1 + dx
        ty = eng.y + 0 + dy
        if not (0 <= tx < GRID_WIDTH and 0 <= ty < GRID_HEIGHT):
            kick_ok = False
            break
        if eng.grid[ty][tx] is not None:
            kick_ok = False
            break

    if not kick_ok:
        # if the designed kick isn't possible at spawn location, move piece right one
        eng.move(1, 0)
        old_x = eng.x - 1

    eng.rotate()
    # rotation should have been applied (rotation increments)
    assert eng.rotation == (old_rot + 1) % 4
    assert eng.x >= old_x


def test_lock_and_clear_multiple_lines_scoring():
    eng = make_empty_engine()
    # pre-fill bottom 3 rows to simulate multiple full lines (engine grid is bottom-origin)
    for r in range(3):
        eng.grid[r] = [(1, 1, 1)] * GRID_WIDTH

    prev_total = eng.total_lines
    prev_score = eng.score
    eng.current_shape = []
    eng.lock_and_clear_lines()
    assert eng.total_lines == prev_total + 3
    assert eng.score == prev_score + GameEngine.SCORE_TABLE.get(3, 800) * eng.level


def test_get_piece_cells_after_move_and_rotate():
    eng = make_empty_engine()
    eng.next_type = "L"
    eng._spawn_piece()
    eng.move(1, 0)
    eng.rotate()
    cells = eng.get_piece_cells()
    assert len(cells) == 4
    for gx, gy in cells:
        assert 0 <= gy < GRID_HEIGHT
        assert 0 <= gx < GRID_WIDTH


def test_check_collision_out_of_bounds_public():
    eng = make_empty_engine()
    eng.next_type = "I"
    eng._spawn_piece()
    assert eng._check_collision(-100, eng.y) is True
    # engine allows pieces above the top during spawn, so very large y should not be a collision
    assert eng._check_collision(eng.x, GRID_HEIGHT + 10) is False


def test_poll_cleared_rows_clears_record():
    eng = make_empty_engine()
    eng._last_cleared_rows = [0, 1]
    out = eng.poll_cleared_rows()
    assert out == [0, 1]
    assert eng.poll_cleared_rows() == []


def test_game_over_on_spawn_if_collides():
    eng = make_empty_engine()
    # fill top row so spawn likely collides
    eng.grid[GRID_HEIGHT - 1] = [(2, 2, 2)] * GRID_WIDTH
    eng.next_type = "I"
    eng._spawn_piece()
    assert eng.game_over is True


def test_piece_id_increments_on_each_spawn():
    """每次生成新块 piece_id 单调递增；同类型连块也区分（bot 换块依据）。"""
    eng = make_empty_engine()
    id1 = eng.piece_id
    eng.next_type = "T"
    eng._spawn_piece()
    assert eng.piece_id == id1 + 1
    eng.next_type = "T"
    eng._spawn_piece()
    assert eng.piece_id == id1 + 2  # 同类型新块 id 也不同


# ----------------------------------------------------------------------
# 共享纯几何原语（engine 模块级函数，供引擎方法与 bot 模拟共用）
# ----------------------------------------------------------------------

def test_rotate_shape_contract():
    """旋转 4 次回到原形；90° 顺时针变换与引擎约定一致。"""
    t = SHAPES_DATA["T"]
    assert rotate_shape(t, 4) == t
    assert rotate_shape(t, 0) == t
    # T 的 (0, 1) 单元（y 向上）顺时针转 90° 后应位于 (1, 0)
    assert (1, 0) in rotate_shape(t, 1)


def test_spawn_y_aligns_top():
    """生成位把 shape 最高单元对齐到顶部行。"""
    i = SHAPES_DATA["I"]      # max_py = 0 -> 顶行
    t = SHAPES_DATA["T"]      # max_py = 1 -> 顶行下方一行
    assert spawn_y(i) == GRID_HEIGHT - 1
    assert spawn_y(t) == GRID_HEIGHT - 2


def test_collides_contract():
    """边界/占用规则：越界、低于底部、占用均冲突；高于顶部放行。"""
    grid: list[list[tuple[int, int, int] | None]] = [
        [None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)
    ]
    one = [(0, 0)]
    assert collides(grid, 0, 0, one) is False
    assert collides(grid, -1, 0, one) is True          # 左越界
    assert collides(grid, GRID_WIDTH, 0, one) is True  # 右越界
    assert collides(grid, 0, -1, one) is True          # 低于底部
    assert collides(grid, 0, GRID_HEIGHT + 10, one) is False  # 高于顶部放行
    grid[0][3] = (9, 9, 9)
    assert collides(grid, 3, 0, one) is True           # 占用冲突


def test_drop_y_lands_on_bottom_or_stack():
    """垂直下落：空盘落到底部，遇到已锁定方块则停在其上。"""
    grid: list[list[tuple[int, int, int] | None]] = [
        [None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)
    ]
    i = SHAPES_DATA["I"]  # 水平 I，max_py=0，生成 y=19
    y = drop_y(grid, i, 3, spawn_y(i))
    assert y == 0  # 空盘直落到底
    # 在列 3 底部放一个方块，I 应停在它上面
    grid[0][3] = (9, 9, 9)
    y = drop_y(grid, i, 3, spawn_y(i))
    assert y == 1


def test_cells_in_bounds_filters_out_of_bounds():
    """只保留边界内的单元格（丢弃超出顶部的部分）。"""
    assert cells_in_bounds(0, 0, [(0, 0), (1, 0), (-1, 0)]) == [
        (0, 0), (1, 0),
    ]
    # 生成区允许 y 超出顶部：这些单元格不写入
    assert cells_in_bounds(0, GRID_HEIGHT, [(0, 1)]) == []


def test_hard_drop_returns_distance_to_bottom():
    """硬降返回落下的格数，块确实贴底（O/S/Z 因含 py=-1 单元停于 anchor y=1）。"""
    eng = GameEngine()
    eng.reset()
    start_y = eng.y
    start_x = eng.x
    distance = eng.hard_drop()
    assert distance == start_y - eng.y  # 距离 = 起降位置差
    assert not eng.move(0, -1)          # 确实贴底：不能再下
    assert eng.x == start_x             # 水平位置不变


def test_add_score_caps_at_max():
    """add_score 累加并封顶到 MAX_SCORE。"""
    eng = GameEngine()
    eng.reset()
    eng.add_score(100)
    assert eng.score == 100
    eng.add_score(MAX_SCORE)
    assert eng.score == MAX_SCORE
    eng.add_score(1)
    assert eng.score == MAX_SCORE


def test_combo_bonus_accumulates_and_resets():
    """连击（指南标准）：连续消行第 2 次起 +50×(N-1)×level；不消行则清零。"""
    eng = GameEngine()
    eng.reset()
    eng.score = 0

    # 两次连续消 1 行：row0 只缺 x0,x1，O 块补满
    for _ in range(2):
        eng.grid[0] = [(1, 1, 1)] * GRID_WIDTH
        eng.grid[0][0] = None
        eng.grid[0][1] = None
        eng.next_type = "O"
        eng._spawn_piece()
        eng.x = 0
        eng.y = 1
        eng.lock_and_clear_lines()

    assert eng.combo == 2
    # 第 1 次：100×1 + 0；第 2 次：100×1 + 50×(2-1)×1
    assert eng.score == 250

    # 放一个不消行的块 → 连击清零
    eng.next_type = "O"
    eng._spawn_piece()
    eng.x = 3
    eng.y = 1
    eng.lock_and_clear_lines()
    assert eng.combo == 0
    assert eng.score == 250  # 该块无消行，不加分


# ----------------------------------------------------------------------
# 贴地锁定规则（引擎级：窗口时长 / 重置预算 / 下落计分）
# ----------------------------------------------------------------------

def test_resting_window_locks_on_expiry():
    """贴地锁定：首次 handle_resting 记录时刻，满 LOCK_DELAY_MS 返回锁定信号。"""
    eng = GameEngine()
    eng.reset()
    while eng.move(0, -1):  # 贴底
        pass
    assert eng.handle_resting(0) is False
    assert eng.resting_since == 0
    assert eng.handle_resting(100) is False  # 窗口内
    assert eng.handle_resting(LOCK_DELAY_MS) is True  # 窗口满 → 应锁定
    assert eng.resting_since is None  # 信号发出后已清除


def test_lock_reset_budget_capped():
    """锁定重置预算：贴地期间 15 次移动重置后，第 16 次不再重置计时。"""
    eng = GameEngine()
    eng.reset()
    while eng.move(0, -1):  # 贴底
        pass
    eng.handle_resting(0)  # 开始贴地计时
    for _ in range(LOCK_RESET_LIMIT):
        eng.reset_lock_delay(count=True)
    assert eng.lock_resets == LOCK_RESET_LIMIT
    # 预算耗尽：第 16 次移动不再重置（resting_since 保持 0，计时继续走）
    eng.handle_resting(0)
    eng.reset_lock_delay(count=True)
    assert eng.resting_since == 0
    # 空中移动不计预算
    eng2 = GameEngine()
    eng2.reset()
    eng2.reset_lock_delay(count=True)
    assert eng2.lock_resets == 0


def test_drop_scoring_in_engine():
    """软降/硬降计分由引擎完成（指南标准：软降 +1/格，硬降 +2/格）。"""
    eng = GameEngine()
    eng.reset()
    assert eng.soft_drop() is True
    assert eng.score == 1  # 软降一格 +1
    s0 = eng.score
    distance = eng.hard_drop()
    assert eng.score == s0 + 2 * distance  # 硬降每格 +2
    assert eng.soft_drop() is False  # 已贴底，软降失败
