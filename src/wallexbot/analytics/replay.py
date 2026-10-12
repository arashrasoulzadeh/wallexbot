"""Turn candles into a synthetic price path for replay."""

from decimal import Decimal

from wallexbot.wallex.models import Candle
from wallexbot.wallex.price_feed import PriceTick

_TICKS_PER_CANDLE = 4


def resolution_seconds(resolution: str) -> int:
    """Wallex UDF resolution -> seconds: '15' is minutes, '1D' / '2D' / '3D' are days."""
    if resolution.upper().endswith("D"):
        return int(resolution[:-1] or 1) * 86400
    return int(resolution) * 60


def candles_to_ticks(candles: list[Candle]) -> list[PriceTick]:
    """Four ticks per candle: open, then the two extremes, then close.

    The order of the extremes is unknown from OHLC alone, so a fixed assumption is used: a candle
    that closed up is assumed to have dipped first (open, low, high, close), one that closed down
    to have spiked first (open, high, low, close). Ticks are spread evenly inside the candle and
    timestamps are milliseconds.
    """
    ticks: list[PriceTick] = []
    for c in candles:
        step_ms = resolution_seconds(c.resolution) * 1000 // _TICKS_PER_CANDLE
        extremes: list[Decimal] = [c.low, c.high] if c.close >= c.open else [c.high, c.low]
        path = [c.open, *extremes, c.close]
        for i, price in enumerate(path):
            ticks.append(
                PriceTick(
                    symbol=c.symbol,
                    price=price,
                    timestamp=c.open_time * 1000 + i * step_ms,
                    source="replay",
                )
            )
    return ticks
