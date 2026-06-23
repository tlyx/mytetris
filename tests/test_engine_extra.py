
from engine import (
    TetrisEngine,
    GRID_HEIGHT,
    GRID_WIDTH,
    WALL_KICKS_OTHERS,
    WALL_KICKS_I,
)
# SHAPES_DATA was previously imported but is not needed here
from tests import helpers


def make_empty_engine():
    eng = TetrisEngine()
    eng.reset()
    return eng


def test_rotate_fails_when_blocked():
    eng = make_empty_engine()
    helpers.spawn_piece_for_test(eng, "T")
    old_shape = list(eng.current_shape)
    old_rot = eng.rotation

    # compute the rotated shape as engine does
    new_shape = [(-dy, dx) for dx, dy in eng.current_shape]

    # choose kick set
    kicks = WALL_KICKS_I if eng.current_type == "I" else WALL_KICKS_OTHERS

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
    helpers.spawn_piece_for_test(eng, "J")
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
    for r in range(0, 3):
        eng.grid[r] = [(1, 1, 1)] * GRID_WIDTH

    prev_total = eng.total_lines
    prev_score = eng.score
    eng.current_shape = []
    eng.lock_and_clear_lines()
    assert eng.total_lines == prev_total + 3
    assert eng.score == prev_score + TetrisEngine.SCORE_TABLE.get(3, 800) * eng.level


def test_get_piece_cells_after_move_and_rotate():
    eng = make_empty_engine()
    helpers.spawn_piece_for_test(eng, "L")
    eng.move(1, 0)
    eng.rotate()
    cells = eng.get_piece_cells()
    assert len(cells) == 4
    for gx, gy in cells:
        assert 0 <= gy < GRID_HEIGHT
        assert 0 <= gx < GRID_WIDTH


def test_check_collision_out_of_bounds_public():
    eng = make_empty_engine()
    helpers.spawn_piece_for_test(eng, "I")
    assert helpers.check_collision(eng, -100, eng.y) is True
    # engine allows pieces above the top during spawn, so very large y should not be a collision
    assert helpers.check_collision(eng, eng.x, GRID_HEIGHT + 10) is False


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
    helpers.spawn_piece_for_test(eng, "I")
    assert eng.game_over is True

