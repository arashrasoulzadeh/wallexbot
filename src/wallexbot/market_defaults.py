"""A sensible starting grid for any Wallex spot market.

The grid is built from the coin's own numbers: its price, its price and quantity precision, the
swing of the last 24 hours and Wallex's minimum order hint. It is a *starting point to look at*, not
a recommendation: the user reviews and edits it on the Configure page, and the same validation
(fee break-even, minimum order size) applies as to any hand-written config.
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any

from wallexbot.config.defaults import default_config
from wallexbot.wallex.models import Market

TARGET_SPACING = Decimal("0.0045")  # about 0.45% between levels, ~3x the round-trip fee
MIN_HALF_WIDTH = Decimal("0.01")  # the range is at least +-1% ...
MAX_HALF_WIDTH = Decimal("0.05")  # ... and at most +-5% around the price
DEFAULT_HALF_WIDTH = Decimal("0.02")  # used when Wallex gives no 24 h high/low
MIN_LEVELS = 3
MAX_LEVELS = 20
SPARE_CAPITAL = Decimal("1.2")  # capital kept 20% above the bare minimum for the chosen levels
DEFAULT_CAPITAL = {"TMN": Decimal(2_000_000), "USDT": Decimal(100)}
FALLBACK_MIN_NOTIONAL = {"TMN": Decimal(90_000), "USDT": Decimal(5)}


def _plain(value: Decimal) -> str:
    """No exponent notation: configs hold plain decimal strings."""
    return format(value, "f")


def suggest_config(info: Market) -> dict[str, Any]:
    """{"config": <full config dict>, "notes": [{"code", "params"}]} for this market."""
    symbol = str(info.symbol)
    price = info.price
    if price is None or price <= 0:
        raise ValueError(f"{symbol} has no price (inactive market?)")

    quote = info.quote_asset
    tick = Decimal(1).scaleb(-info.price_precision)
    step = Decimal(1).scaleb(-info.amount_precision)
    min_notional = info.min_notional_hint or FALLBACK_MIN_NOTIONAL.get(quote, Decimal(5))
    notes: list[dict[str, Any]] = []

    half = DEFAULT_HALF_WIDTH
    if info.high_24h and info.low_24h and info.high_24h >= info.low_24h:
        observed = (info.high_24h - info.low_24h) / (2 * price)
        half = min(max(observed * Decimal("1.5"), MIN_HALF_WIDTH), MAX_HALF_WIDTH)

    def at_tick(value: Decimal) -> Decimal:
        return value.quantize(tick, rounding=ROUND_HALF_UP)

    lower, upper = at_tick(price * (1 - half)), at_tick(price * (1 + half))
    # coins priced in a few ticks need a range wide enough to hold distinct levels
    needed = tick * 2 * (MIN_LEVELS - 1)
    if upper - lower < needed or lower <= 0:
        lower = max(at_tick(price - needed), tick)
        upper = at_tick(price + needed)
        notes.append({"code": "range_widened_for_tick", "params": {"tick": tick}})

    range_pct = (upper - lower) / price
    count = int((range_pct / TARGET_SPACING).to_integral_value(rounding=ROUND_HALF_UP)) + 1
    count = max(MIN_LEVELS, min(MAX_LEVELS, count))
    count = min(count, int((upper - lower) / (2 * tick)) + 1)  # at least 2 ticks between levels
    count = max(count, MIN_LEVELS)

    capital = DEFAULT_CAPITAL.get(quote, Decimal(100))
    # An order is rounded DOWN to the quantity step, which can cost up to one step of value. Leave
    # room for it, or a coin with a coarse step ends up below the minimum order size.
    per_level_floor = min_notional + price * step
    needed_capital = (per_level_floor * count * SPARE_CAPITAL).to_integral_value(
        rounding=ROUND_CEILING
    )
    if needed_capital > capital:
        capital = needed_capital
        notes.append(
            {"code": "capital_raised", "params": {"capital": capital, "min_notional": min_notional}}
        )

    cfg = default_config()
    cfg["market"]["symbol"] = symbol
    cfg["strategy"]["grid"].update(
        lower_price=_plain(lower),
        upper_price=_plain(upper),
        grid_count=count,
        total_investment=_plain(capital),
    )
    cfg["simulation"].update(
        initial_balance_quote=_plain(capital),
        initial_balance_base="0",
        min_notional=_plain(min_notional),
        min_quantity=_plain(step),
    )
    cfg["risk"].update(
        max_exposure_quote=_plain(capital),
        max_exposure_base=_plain((capital / price * 2).quantize(step, rounding=ROUND_CEILING)),
    )
    return {"config": cfg, "notes": notes}
