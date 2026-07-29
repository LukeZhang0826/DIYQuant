from diyquant.risk.selection import select_positions


def scores(**kwargs: float) -> dict[str, float]:
    return dict(kwargs)


def test_funds_the_strongest_when_nothing_is_held():
    picked = select_positions(
        scores=scores(A=0.9, B=0.8, C=0.7, D=0.6, E=0.5, F=0.4),
        held=set(),
        max_positions=3,
        hysteresis_rank=6,
    )
    assert picked == {"A", "B", "C"}


def test_never_funds_more_than_max_positions():
    """The bug this layer exists for: ~500 live signals, capital for five."""
    picked = select_positions(
        scores={f"S{i:03d}": 1.0 - i / 1000 for i in range(500)},
        held=set(),
        max_positions=5,
        hysteresis_rank=10,
    )
    assert len(picked) == 5


def test_incumbent_inside_the_buffer_keeps_its_slot():
    """E slipped to 6th. Selling and rebuying it costs money for no change of view."""
    picked = select_positions(
        scores=scores(A=0.9, B=0.8, C=0.7, D=0.6, F=0.55, E=0.5),
        held={"E"},
        max_positions=5,
        hysteresis_rank=10,
    )
    assert "E" in picked
    assert len(picked) == 5


def test_incumbent_outside_the_buffer_loses_its_slot():
    ranked = {f"S{i:02d}": 1.0 - i / 100 for i in range(20)}
    picked = select_positions(
        scores=ranked,
        held={"S15"},
        max_positions=5,
        hysteresis_rank=10,
    )
    assert "S15" not in picked


def test_a_newcomer_must_rank_inside_max_positions():
    """The buffer lets a good name stay; it must not let a mediocre one in."""
    picked = select_positions(
        scores=scores(A=0.9, B=0.8, C=0.7, D=0.6, E=0.5, F=0.4, G=0.3),
        held=set(),
        max_positions=3,
        hysteresis_rank=6,
    )
    assert picked == {"A", "B", "C"}
    assert "D" not in picked


def test_incumbents_fill_slots_before_newcomers():
    picked = select_positions(
        scores=scores(A=0.9, B=0.8, C=0.7, D=0.6, E=0.5),
        held={"D", "E"},
        max_positions=3,
        hysteresis_rank=5,
    )
    assert {"D", "E"}.issubset(picked)
    assert picked == {"D", "E", "A"}


def test_a_held_name_with_no_live_signal_is_dropped():
    """Absent from scores means it went flat or was vetoed, so it winds down."""
    picked = select_positions(
        scores=scores(A=0.9, B=0.8),
        held={"Z"},
        max_positions=5,
        hysteresis_rank=10,
    )
    assert "Z" not in picked
    assert picked == {"A", "B"}


def test_more_incumbents_than_slots_keeps_only_the_strongest():
    picked = select_positions(
        scores=scores(A=0.9, B=0.8, C=0.7),
        held={"A", "B", "C"},
        max_positions=2,
        hysteresis_rank=10,
    )
    assert picked == {"A", "B"}


def test_ties_break_deterministically_on_symbol():
    flat = scores(D=0.5, C=0.5, B=0.5, A=0.5)
    first = select_positions(flat, set(), max_positions=2, hysteresis_rank=4)
    second = select_positions(flat, set(), max_positions=2, hysteresis_rank=4)
    assert first == second == {"A", "B"}


def test_no_candidates_funds_nothing():
    assert select_positions({}, set(), max_positions=5, hysteresis_rank=10) == set()


def test_zero_max_positions_funds_nothing():
    picked = select_positions(scores(A=0.9), held={"A"}, max_positions=0, hysteresis_rank=10)
    assert picked == set()
