"""A coin's last week from hourly candles: how far it ranged and how much it moves per hour."""

from decimal import Decimal
from typing import Any

from wallexbot.wallex.models import Candle

HUNDRED = Decimal(100)


def week_stats(candles: list[Candle], price: Decimal) -> dict[str, Any] | None:
    """Range and per-hour movement over `candles`; None when there are none."""
    if not candles:
        return None
    high = max(c.high for c in candles)
    low = min(c.low for c in candles)
    spans = [(c.high - c.low) / c.open * HUNDRED for c in candles if c.open > 0]
    span = high - low
    position = (price - low) / span * HUNDRED if span > 0 else Decimal(50)
    return {
        "hours": len(candles),
        "high": high,
        "low": low,
        "range_pct": span / low * HUNDRED if low > 0 else Decimal(0),
        "avg_hour_range_pct": sum(spans, Decimal(0)) / len(spans) if spans else Decimal(0),
        "max_hour_range_pct": max(spans) if spans else Decimal(0),
        "position_pct": min(max(position, Decimal(0)), HUNDRED),
    }
