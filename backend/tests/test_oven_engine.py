from app.services.oven_engine import (
    Interval,
    Occupancy,
    RecipeDurations,
    build_occupancies,
    find_conflicts,
    next_free_window,
)


def test_half_open_no_touch_conflict():
    a = Occupancy(1, Interval(0, 30), "bake", 1)
    b = Occupancy(1, Interval(30, 60), "bake", 2)
    assert find_conflicts([a], [b]) == []


def test_overlap_detected():
    recipe = RecipeDurations(20, 30)
    cand = build_occupancies(1, 9, 10, recipe)
    existing = [Occupancy(1, Interval(25, 40), "bake", 1)]
    assert find_conflicts(existing, cand)


def test_next_free_window_after_busy():
    existing = [
        Occupancy(1, Interval(0, 40), "ferment", 1),
        Occupancy(1, Interval(40, 70), "bake", 1),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(70, 100)


def test_next_free_in_gap():
    existing = [
        Occupancy(1, Interval(0, 20), "bake", 1),
        Occupancy(1, Interval(80, 100), "bake", 2),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(20, 50)


def test_cooling_tail_emitted_only_when_positive():
    recipe = RecipeDurations(20, 30)
    with_cool = build_occupancies(1, 1, 0, recipe, cool_min=15)
    assert [o.phase for o in with_cool] == ["ferment", "bake", "cool"]
    assert with_cool[-1].interval == Interval(50, 65)  # 0+20+30 -> +15
    no_cool = build_occupancies(1, 1, 0, recipe, cool_min=0)
    assert [o.phase for o in no_cool] == ["ferment", "bake"]


def test_cooling_does_not_change_ferment_bake_ends():
    recipe = RecipeDurations(20, 30)
    a = build_occupancies(1, 1, 10, recipe, cool_min=45)
    assert a[0].interval == Interval(10, 30)
    assert a[1].interval == Interval(30, 60)


def test_next_batch_touches_bake_end_when_no_cooling():
    recipe = RecipeDurations(20, 30)
    existing = build_occupancies(1, 1, 0, recipe, cool_min=0)
    # starts exactly at bake end 50 — half-open, must be allowed
    cand = build_occupancies(1, 2, 50, recipe, cool_min=0)
    assert find_conflicts(existing, cand) == []


def test_next_batch_may_touch_cooling_end():
    recipe = RecipeDurations(20, 30)
    existing = build_occupancies(1, 1, 0, recipe, cool_min=15)
    # cooling = [50, 65); next batch may start exactly at 65
    ok = build_occupancies(1, 2, 65, recipe, cool_min=15)
    assert find_conflicts(existing, ok) == []


def test_overlap_with_cooling_tail_rejected():
    recipe = RecipeDurations(20, 30)
    existing = build_occupancies(1, 1, 0, recipe, cool_min=20)  # cool [50,70)
    # start at 60: ferment [60,80) cuts into the cooling tail
    cand = build_occupancies(1, 2, 60, recipe, cool_min=20)
    hits = find_conflicts(existing, cand)
    assert hits
    assert any(ex.phase == "cool" for ex, _c in hits)


def test_window_skips_cooling_tail():
    # bake [0,40), cool [40,60): gap during cool must not be offered;
    # a 30-min job from 0 fits starting at 0 itself, so search from 40
    existing = [
        Occupancy(1, Interval(0, 40), "bake", 1),
        Occupancy(1, Interval(40, 60), "cool", 1),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=40)
    assert w == Interval(60, 90)


def test_window_no_gap_inside_cooling():
    existing = [
        Occupancy(1, Interval(0, 100), "bake", 1),
        Occupancy(1, Interval(100, 140), "cool", 1),
    ]
    # a 20-min job searching right after bake: [100,120) is cooling, rejected
    assert next_free_window(existing, 1, duration=20, search_from=100) == Interval(140, 160)
