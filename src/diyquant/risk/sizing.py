"""Position sizing: turn a signal's target {-1, 0, +1} into a whole-share count.

Pure function. The cap comes from config (risk.max_position_pct); sizing to
the cap rather than full equity is what keeps any single symbol from sinking
the account.
"""


def target_shares(
    target: int,
    equity: float,
    price: float,
    max_position_pct: float,
) -> int:
    """Return the signed whole-share position for a signal target.

    Sizes to max_position_pct of equity at the given price, rounded down.
    Returns 0 when the target is flat or when even one share would breach
    the cap.
    """
    if target not in (-1, 0, 1):
        raise ValueError(f"target must be -1, 0, or 1, got {target}")
    if equity <= 0:
        raise ValueError(f"equity must be positive, got {equity}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")

    if target == 0:
        return 0

    budget = equity * max_position_pct / 100
    shares = int(budget / price)
    return target * shares
