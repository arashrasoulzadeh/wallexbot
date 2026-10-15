"""Same candles, three ways: a fixed grid, a grid that follows the price, and simply holding.

This is how to judge whether turning on `recenter_after_minutes` would have paid on a period, before using it.
"""

from dataclasses import dataclass
from decimal import Decimal

from wallexbot.analytics.backtest import Backtester, BacktestMetrics
from wallexbot.analytics.replay import candles_to_ticks
from wallexbot.setup import GridSetup
from wallexbot.wallex.models import Candle
from wallexbot.wallex.price_feed import PriceFeedReplay


@dataclass(frozen=True)
class CompareRow:
    label: str  # "static", "recentering" or "buy_and_hold"
    return_pct: Decimal
    realized: Decimal
    max_drawdown: Decimal
    cycles: int
    recenters: int


def _row(label: str, m: BacktestMetrics) -> CompareRow:
    return CompareRow(
        label=label,
        return_pct=m.total_return_pct,
        realized=m.realized_pnl,
        max_drawdown=m.max_drawdown,
        cycles=m.completed_cycles,
        recenters=m.recenters,
    )


def _run(setup: GridSetup, candles: list[Candle], minutes: int | None) -> BacktestMetrics:
    """One backtest on a fresh exchange and strategy."""
    backtester = Backtester(
        strategy=setup.new_strategy(),
        exchange=setup.new_exchange(),
        price_feed=PriceFeedReplay(candles_to_ticks(candles)),
        recenter_after_minutes=minutes,
    )
    return backtester.run().metrics


def compare_strategies(
    setup: GridSetup, candles: list[Candle], recenter_after_minutes: int
) -> list[CompareRow]:
    """[static grid, grid that re-centers after `recenter_after_minutes`, buy and hold]."""
    static = _run(setup, candles, None)
    moving = _run(setup, candles, recenter_after_minutes)

    prices = [t.price for t in candles_to_ticks(candles)]
    peak, drawdown = Decimal(0), Decimal(0)
    for price in prices:
        peak = max(peak, price)
        drawdown = max(drawdown, (peak - price) / peak * 100)
    hold = CompareRow(
        label="buy_and_hold",
        return_pct=(prices[-1] / prices[0] - 1) * 100,
        realized=Decimal(0),
        max_drawdown=drawdown,
        cycles=0,
        recenters=0,
    )
    return [_row("static", static), _row("recentering", moving), hold]
