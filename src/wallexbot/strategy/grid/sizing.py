"""Order sizing for grid strategy."""

from decimal import Decimal

from wallexbot.domain.fees import MinNotionalRule
from wallexbot.domain.market import Market, Side
from wallexbot.domain.money import quantize_down
from wallexbot.strategy.grid.parameters import Level


def calculate_equal_quote_qty(
    levels: list[Level],
    total_quote: Decimal,
    market: Market,
) -> list[Decimal]:
    """
    Calculate quantities for equal-quote-per-grid sizing.

    Each active level gets total_quote / num_active_levels quote value.
    Quantity = quote_per_level / level_price, rounded down to amount_precision.
    """
    active_levels = [lvl for lvl in levels if lvl.side in ("buy", "sell")]
    if not active_levels:
        return [Decimal("0") for _ in levels]

    quote_per_level = total_quote / len(active_levels)
    step = Decimal("1") / (Decimal("10") ** market.amount_precision)

    result = []
    for level in levels:
        if level.side in ("buy", "sell"):
            raw_qty = quote_per_level / level.price
            qty = quantize_down(raw_qty, step)
            result.append(qty)
        else:
            result.append(Decimal("0"))
    return result


def calculate_equal_base_qty(
    levels: list[Level],
    per_grid_qty: Decimal,
    market: Market,
) -> list[Decimal]:
    """
    Calculate quantities for equal-base-qty-per-grid sizing.

    Each active level gets the same base quantity.
    """
    step = Decimal("1") / (Decimal("10") ** market.amount_precision)
    qty = quantize_down(per_grid_qty, step)

    result = []
    for level in levels:
        if level.side in ("buy", "sell"):
            result.append(qty)
        else:
            result.append(Decimal("0"))
    return result


def validate_order_sizes(
    levels: list[Level],
    qtys: list[Decimal],
    market: Market,
    rule: MinNotionalRule,
) -> tuple[bool, list[str]]:
    """
    Validate that all orders meet minimum notional and quantity requirements.

    Returns:
        (ok, errors): ok is True if all pass, errors list if any fail
    """
    errors = []
    for level, qty in zip(levels, qtys, strict=True):
        if level.side not in ("buy", "sell"):
            continue
        ok, msg = rule.validate(level.price, qty)
        if not ok:
            errors.append(f"Level {level.index} ({level.price}): {msg}")
    return (len(errors) == 0, errors)


def compute_initial_inventory(
    levels: list[Level],
    qtys: list[Decimal],
    side: Side,
) -> Decimal:
    """
    Compute initial inventory needed for sell orders (base asset) or buy orders (quote asset).

    For BUY side: returns quote value needed (not base quantity)
    For SELL side: returns base quantity needed
    """
    total = Decimal("0")
    for level, qty in zip(levels, qtys, strict=True):
        if level.side == side.value.lower():
            if side == Side.SELL:
                total += qty
            else:  # BUY
                total += level.price * qty
    return total
