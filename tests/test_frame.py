from launchpad_lights.launchpad.frame import N_LEDS, SIDE, TOP, Frame


def test_diff_against_none_is_everything():
    assert Frame().diff(None) == list(range(N_LEDS))


def test_diff_only_changed():
    a = Frame()
    b = a.copy()
    assert b.diff(a) == []
    b.set(2, 1, (3, 0))
    b.set_side(0, (0, 3))
    b.set_top(7, (3, 3))
    assert b.diff(a) == [10, SIDE, TOP + 7]


def test_copy_is_independent_and_set_ignores_out_of_range():
    a = Frame()
    b = a.copy()
    b.set(0, 0, (1, 1))
    b.set(8, 0, (1, 1))
    b.set(-1, 3, (1, 1))
    assert a.get(0, 0) == (0, 0)
    assert b.diff(a) == [0]


def test_fill_only_touches_grid():
    f = Frame()
    f.fill((3, 3))
    assert all(c == (3, 3) for c in f.leds[:SIDE])
    assert all(c == (0, 0) for c in f.leds[SIDE:])
