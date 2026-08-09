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


def _reference(scores, held, max_positions, hysteresis_rank):
    """The pre-2026-08-08 implementation: full sort, kept as the oracle.

    select_positions was changed to a top-k heap for speed, and "for speed" is
    exactly when a behaviour change slips through unnoticed. This is the old code
    verbatim, so the property test below compares against what actually shipped
    rather than against a restatement of the new logic.
    """
    if max_positions <= 0:
        return set()
    ranked = sorted(scores, key=lambda symbol: (-scores[symbol], symbol))
    rank_of = {symbol: i + 1 for i, symbol in enumerate(ranked)}
    keep = {s for s in held if s in rank_of and rank_of[s] <= hysteresis_rank}
    if len(keep) > max_positions:
        keep = set(sorted(keep, key=lambda s: rank_of[s])[:max_positions])
    free = max_positions - len(keep)
    if free <= 0:
        return keep
    entrants = [s for s in ranked[:max_positions] if s not in keep][:free]
    return keep | set(entrants)


def test_top_k_matches_the_full_sort_on_random_books():
    """Randomised equivalence, including ties, which is where a sort's order matters."""
    import random

    rng = random.Random(20260808)
    universe = [f"S{i:03d}" for i in range(120)]
    for _ in range(400):
        n = rng.randint(1, len(universe))
        symbols = rng.sample(universe, n)
        # Coarse scores on purpose: rounding forces frequent ties, so the
        # symbol-name tiebreak is genuinely exercised rather than assumed.
        scores = {s: round(rng.uniform(-2, 2), 1) for s in symbols}
        held = set(rng.sample(symbols, rng.randint(0, min(8, n))))
        max_positions = rng.randint(1, 8)
        hysteresis_rank = rng.randint(1, 20)

        assert select_positions(scores, held, max_positions, hysteresis_rank) == _reference(
            scores, held, max_positions, hysteresis_rank
        ), (scores, held, max_positions, hysteresis_rank)


def test_top_k_matches_when_hysteresis_is_deeper_than_the_universe():
    scores = {"A": 1.0, "B": 0.5}
    assert select_positions(scores, {"B"}, max_positions=1, hysteresis_rank=50) == _reference(
        scores, {"B"}, 1, 50
    )
