"""Market status: neutral facts about the price, the grid and the order book.

This module describes; it never recommends. There is no "buy" or "sell" verdict anywhere in its
output. It reports where the price sits in the configured grid, which of the grid's own orders
are the next to trigger, how the price moved recently, how balanced the order book is, and a
list of plain conditions that make a grid more or less likely to trade or to hold up
(`warnings`, each a code plus numbers that the UI words in the user's language).
"""

from decimal import Decimal
from typing import Any

from wallexbot.strategy.grid.parameters import GridParameters, generate_levels
from wallexbot.wallex.models import Candle, Depth

HOUR = 3600
DAY = 86400
RESAMPLE_MINUTES = 15  # the trend is judged on 15-minute steps, not 1-minute noise
MIN_TREND_SAMPLES = 8
SIDEWAYS_BELOW = Decimal("0.15")  # efficiency ratio under this: the price went nowhere
STRONG_TREND_FROM = Decimal("0.4")
STALE_AFTER_MS = 10 * 60_000
MIN_CANDLES_FOR_HOUR_CHECK = 30


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return part / whole * 100


def grid_position(price: Decimal, params: GridParameters, price_precision: int) -> dict[str, Any]:
    """Where `price` sits in the grid, and the grid's nearest orders on each side."""
    levels = sorted(
        lv.price
        for lv in generate_levels(
            params.lower_price,
            params.upper_price,
            params.grid_count,
            params.mode,
            price_precision,
        )
    )
    lower, upper = params.lower_price, params.upper_price
    state = "below" if price < lower else "above" if price > upper else "inside"
    position = min(max(_pct(price - lower, upper - lower), Decimal(0)), Decimal(100))

    def neighbour(value: Decimal | None) -> dict[str, Decimal] | None:
        if value is None:
            return None
        distance = abs(price - value)
        return {"price": value, "distance": distance, "distance_pct": _pct(distance, price)}

    below = [p for p in levels if p < price]
    above = [p for p in levels if p > price]
    # spacing of the interval the price is in (constant for an arithmetic grid)
    gaps = [(b - a, a, b) for a, b in zip(levels, levels[1:], strict=False)]
    gap = next(
        (g for g, a, b in gaps if a <= price <= b), gaps[0][0] if price < lower else gaps[-1][0]
    )
    return {
        "state": state,
        "levels": len(levels),
        "lower": lower,
        "upper": upper,
        "position_pct": position,
        "next_buy": neighbour(max(below) if below else None),
        "next_sell": neighbour(min(above) if above else None),
        "spacing": gap,
        "spacing_pct": _pct(gap, price),
        "level_prices": levels,
    }


def change_over(candles: list[Candle], seconds: int) -> Decimal | None:
    """Percent change over the last `seconds`, or None if the history does not cover it."""
    if not candles:
        return None
    last = candles[-1]
    start = next((c for c in candles if c.open_time >= last.open_time - seconds), None)
    if start is None or last.open_time - start.open_time < 0.9 * seconds or start.open <= 0:
        return None
    return _pct(last.close - start.open, start.open)


def _range_pct(candles: list[Candle]) -> Decimal | None:
    if not candles:
        return None
    low = min(c.low for c in candles)
    high = max(c.high for c in candles)
    return _pct(high - low, low) if low > 0 else None


def price_trend(candles: list[Candle]) -> dict[str, Any]:
    """Describe how directly the price travelled: sideways, up, down or unclear.

    Uses the efficiency ratio on 15-minute steps: net move divided by total distance travelled.
    Near 0 the price wandered and came back (sideways); near 1 it went one way. This describes
    what already happened; it predicts nothing.
    """
    closes = [c.close for c in candles][::RESAMPLE_MINUTES]
    if candles and closes[-1] != candles[-1].close:
        closes.append(candles[-1].close)
    if len(closes) < MIN_TREND_SAMPLES:
        return {"label": "unclear", "efficiency": Decimal(0), "samples": len(closes)}
    travelled = sum((abs(b - a) for a, b in zip(closes, closes[1:], strict=False)), Decimal(0))
    net = closes[-1] - closes[0]
    efficiency = abs(net) / travelled if travelled > 0 else Decimal(0)
    if efficiency < SIDEWAYS_BELOW:
        label = "sideways"
    else:
        label = "up" if net > 0 else "down"
    return {"label": label, "efficiency": efficiency, "samples": len(closes)}


def depth_summary(depth: Depth | None) -> dict[str, Any] | None:
    """Best prices, spread and how the visible volume splits between buyers and sellers."""
    if depth is None:
        return None
    bid = max((lv.price for lv in depth.bids), default=None)
    ask = min((lv.price for lv in depth.asks), default=None)
    bid_volume = sum((lv.quantity for lv in depth.bids), Decimal(0))
    ask_volume = sum((lv.quantity for lv in depth.asks), Decimal(0))
    total = bid_volume + ask_volume
    spread = ask - bid if bid is not None and ask is not None else None
    mid = (bid + ask) / 2 if bid is not None and ask is not None else None
    return {
        "best_bid": bid,
        "best_ask": ask,
        "spread": spread,
        "spread_pct": _pct(spread, mid) if spread is not None and mid else None,
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
        "bid_share_pct": _pct(bid_volume, total) if total > 0 else None,
    }


def build_market_status(
    symbol: str,
    price: Decimal,
    trade_ts: int,
    candles: list[Candle],
    depth: Depth | None,
    params: GridParameters,
    price_precision: int,
    maker_fee: Decimal,
    now_ms: int,
) -> dict[str, Any]:
    """Everything the Market status page shows, as Decimals (use `jsonable` to serialize)."""
    grid = grid_position(price, params, price_precision)
    grid["round_trip_fee_pct"] = 2 * maker_fee * 100
    grid["range_pct"] = _pct(params.upper_price - params.lower_price, params.lower_price)

    last_ts = candles[-1].open_time if candles else 0
    day = [c for c in candles if c.open_time >= last_ts - DAY]
    hour = [c for c in candles if c.open_time >= last_ts - HOUR]
    changes = {
        "h1_pct": change_over(candles, HOUR),
        "h24_pct": change_over(candles, DAY),
        "high_24h": max((c.high for c in day), default=None),
        "low_24h": min((c.low for c in day), default=None),
        "range_24h_pct": _range_pct(day),
        "range_1h_pct": _range_pct(hour),
    }
    trend = price_trend(candles)
    book = depth_summary(depth)

    warnings: list[dict[str, Any]] = []
    if grid["state"] != "inside":
        bound = params.upper_price if grid["state"] == "above" else params.lower_price
        warnings.append(
            {
                "code": "outside_range",
                "params": {"side": grid["state"], "price": price, "bound": bound},
            }
        )
    range_1h = changes["range_1h_pct"]
    if (
        grid["state"] == "inside"
        and range_1h is not None
        and len(hour) >= MIN_CANDLES_FOR_HOUR_CHECK
        and range_1h < grid["spacing_pct"]
    ):
        warnings.append(
            {
                "code": "moves_smaller_than_spacing",
                "params": {"hour_range_pct": range_1h, "spacing_pct": grid["spacing_pct"]},
            }
        )
    range_24h = changes["range_24h_pct"]
    if range_24h is not None and range_24h > grid["range_pct"]:
        warnings.append(
            {
                "code": "range_wider_than_grid",
                "params": {"day_range_pct": range_24h, "grid_range_pct": grid["range_pct"]},
            }
        )
    if trend["label"] in ("up", "down") and trend["efficiency"] >= STRONG_TREND_FROM:
        warnings.append(
            {
                "code": "strong_trend",
                "params": {"direction": trend["label"], "efficiency": trend["efficiency"]},
            }
        )
    if now_ms - trade_ts > STALE_AFTER_MS:
        warnings.append(
            {"code": "stale_price", "params": {"minutes": Decimal((now_ms - trade_ts) // 60_000)}}
        )

    return {
        "symbol": symbol,
        "price": price,
        "as_of_ms": trade_ts,
        "changes": changes,
        "trend": trend,
        "grid": grid,
        "depth": book,
        "warnings": warnings,
    }


def jsonable(value: Any) -> Any:
    """Decimals as strings (exact), recursively."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value
