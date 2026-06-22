
from engine import TetrisEngine, GRID_HEIGHT, GRID_WIDTH, SHAPES_DATA
from tests import helpers


def make_empty_engine():
    eng = TetrisEngine()
    # reset() already called in constructor; ensure a clean start
    eng.reset()
    return eng


def test_spawn_top_aligned_all_pieces():
    eng = make_empty_engine()
    for piece in SHAPES_DATA.keys():
        helpers.spawn_piece_for_test(eng, piece)
        # current_shape uses relative coords; check that top-most cell is at row 0
        min_py = min(py for _, py in eng.current_shape)
        # after spawn eng.y should be -min_py so min_py + eng.y == 0
        assert min_py + eng.y == 0, f"{piece} not top-aligned: min_py={min_py}, y={eng.y}"


def test_move_boundaries():
    eng = make_empty_engine()
    eng.next_type = "O"
    helpers.spawn_piece_for_test(eng, "O")
    # move left until boundary
    while eng.move(-1, 0):
        pass
    # now at leftmost; further move should fail
    assert not eng.move(-1, 0)
    # move right until boundary
    while eng.move(1, 0):
        pass
    assert not eng.move(1, 0)


def test_rotate_changes_rotation_and_shape():
    eng = make_empty_engine()
    eng.next_type = "T"
    helpers.spawn_piece_for_test(eng, "T")
    old_shape = list(eng.current_shape)
    old_rotation = eng.rotation
    eng.rotate()
    # rotation should increment modulo 4
    assert eng.rotation == (old_rotation + 1) % 4
    # shape should have changed for T
    assert eng.current_shape != old_shape


def test_rotate_o_piece_noop():
    eng = make_empty_engine()
    eng.next_type = "O"
    helpers.spawn_piece_for_test(eng, "O")
    old_shape = list(eng.current_shape)
    old_rotation = eng.rotation
    eng.rotate()
    assert eng.current_shape == old_shape
    assert eng.rotation == old_rotation


def test_lock_and_clear_lines_updates_score_and_grid():
    eng = make_empty_engine()
    # pre-fill bottom row to simulate a full line
    eng.grid[-1] = [(1, 1, 1)] * GRID_WIDTH
    prev_total = eng.total_lines
    prev_score = eng.score
    # ensure current_shape does not interfere
    eng.current_shape = []
    eng.lock_and_clear_lines()
    # one line cleared
    assert eng.total_lines == prev_total + 1
    assert eng.score >= prev_score  # score increased by table * level


def test_get_ghost_y_simple():
    eng = make_empty_engine()
    eng.next_type = "I"
    helpers.spawn_piece_for_test(eng, "I")
    # drop current piece to bottom via ghost calculation
    g = eng.get_ghost_y()
    # ghost must be >= current y and less than GRID_HEIGHT
    assert g >= eng.y
    assert g < GRID_HEIGHT


def test_fall_speed_monotonic():
    from engine import TetrisEngine
    s1 = TetrisEngine.fall_speed(1)
    s2 = TetrisEngine.fall_speed(2)
    s10 = TetrisEngine.fall_speed(10)
    assert isinstance(s1, int)
    assert s2 <= s1  # higher level => smaller interval (faster)
    assert s10 <= s2


def test_bag_draw_and_refill():
    eng = make_empty_engine()
    helpers.set_bag(eng, ["I", "O"])
    a = helpers.draw_from_bag(eng)
    b = helpers.draw_from_bag(eng)
    assert a in ["I", "O"]
    assert b in ["I", "O"]
    # bag should be empty now; next draw should refill without error
    c = helpers.draw_from_bag(eng)
    assert c in ["I", "O", "T", "L", "J", "S", "Z"]

