"""Pick which of many simultaneous signals actually get funded.

The universe is ~503 names and the SMA crossover has no notion of magnitude, so
it puts roughly 500 of them into an active long or short state at once. Capital
funds about five (max_position_pct 20%). Before this module the pipeline sized
every one of those signals at the full cap and submitted an order for each, so
which five you ended up holding was decided by dict iteration order and whatever
cash was left when the broker got there, not by conviction. The 2026-07-28 cycle
submitted 466 orders against funding for five.

Selection lives under risk/ because that is what it is: holding the best five
rather than the first five is a concentration decision, and max_positions sits
naturally beside max_position_pct, which at 20% already implies five slots.

Ranking-metric agnostic on purpose. The caller supplies {symbol: score} and this
decides who gets a slot, so changing how conviction is measured never touches
this file.
"""

import heapq


def select_positions(
    scores: dict[str, float],
    held: set[str],
    max_positions: int,
    hysteresis_rank: int,
) -> set[str]:
    """Return the symbols that should carry a position this cycle.

    `scores` holds every candidate, meaning a non-flat signal that survived the
    sentiment gate, mapped to its conviction with higher being stronger. `held`
    is the subset already in the book whose signal still points the same way.

    An incumbent keeps its slot while it ranks inside `hysteresis_rank`. That is
    what stops a name which slipped from 5th to 6th being sold today and bought
    back tomorrow, paying costs both ways for no change of view. A newcomer must
    rank inside `max_positions` to take a free slot, so the buffer only ever
    lets a good name stay, never lets a mediocre one in.

    Ties break on symbol so the result is deterministic. Two names with equal
    conviction must not produce different books on different runs.
    """
    if max_positions <= 0:
        return set()

    # Only the top max(max_positions, hysteresis_rank) ever matters: an incumbent
    # outside hysteresis_rank loses its slot whatever its exact rank, and an
    # entrant outside max_positions can never take one. Fully sorting ~500
    # candidates to read the first 10 of them was the single hottest line in a
    # walk-forward, which runs this once per symbol-day across hundreds of
    # backtests. nsmallest is O(n log k) and returns them in the same order the
    # sort did, so the selected set is unchanged.
    depth = max(max_positions, hysteresis_rank)
    ranked = heapq.nsmallest(depth, scores, key=lambda symbol: (-scores[symbol], symbol))
    rank_of = {symbol: i + 1 for i, symbol in enumerate(ranked)}

    # A held name absent from `scores` has gone flat or been vetoed this cycle,
    # so it is not a candidate and keeps no slot: it gets wound down.
    keep = {s for s in held if s in rank_of and rank_of[s] <= hysteresis_rank}

    # More incumbents than slots is possible after a config change or a shrunken
    # candidate set. Drop the weakest rather than quietly exceed max_positions.
    if len(keep) > max_positions:
        keep = set(sorted(keep, key=lambda s: rank_of[s])[:max_positions])

    free = max_positions - len(keep)
    if free <= 0:
        return keep

    entrants = [s for s in ranked[:max_positions] if s not in keep][:free]
    return keep | set(entrants)
