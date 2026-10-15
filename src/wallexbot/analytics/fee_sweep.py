"""One grid, one set of candles, several fee tiers.

The real Wallex fee is only visible with an API key, so instead of guessing one number this shows
what the grid would earn at each plausible fee and the fee above which it stops being worth running.
"""

import dataclasses
from dataclasses import dataclass
from decimal import Decimal

from wallexbot.analytics.backtest import Backtester
from wallexbot.analytics.replay import candles_to_ticks
from wallexbot.config.schema import Config
from wallexbot.domain.fees import FeeSchedule
from wallexbot.setup import GridSetup
from wallexbot.strategy.grid.parameters import GridParameters
from wallexbot.wallex.models import Candle
from wallexbot.wallex.price_feed import PriceFeedReplay

DEFAULT_FEES = [Decimal("0.0005"), Decimal("0.001"), Decimal("0.002"), Decimal("0.0035")]


@dataclass(frozen=True)
class FeeRow:
    fee: Decimal
    clears_break_even: bool  # the config check (spacing > round trip x margin) would accept it
    cycles: int
    realized: Decimal
    fees_paid: Decimal
    total_return_pct: Decimal
    max_drawdown: Decimal


def _spacing_pct(params: GridParameters) -> Decimal:
    count = params.grid_count
    mid = (params.lower_price + params.upper_price) / 2
    return (params.upper_price - params.lower_price) / (count - 1) / mid


def break_even_fee(params: GridParameters) -> Decimal:
    """The highest per-trade fee the validator accepts for this grid: spacing / (2 x margin)."""
    return _spacing_pct(params) / (2 * Config.BREAKEVEN_MARGIN)


def fee_sweep(setup: GridSetup, candles: list[Candle], fees: list[Decimal]) -> list[FeeRow]:
    """Backtest `setup` at each fee (maker = taker), cheapest first; [] if the grid cannot start."""
    limit = break_even_fee(setup.params)
    rows: list[FeeRow] = []
    for fee in sorted(fees):
        variant = dataclasses.replace(
            setup,
            fees=FeeSchedule(maker_rate=fee, taker_rate=fee),
            maker=fee,
            taker=fee,
        )
        backtester = Backtester(
            strategy=variant.new_strategy(),
            exchange=variant.new_exchange(),
            price_feed=PriceFeedReplay(candles_to_ticks(candles)),
        )
        try:
            m = backtester.run().metrics
        except ValueError:  # orders below the minimum size: the same for every fee
            return []
        rows.append(
            FeeRow(
                fee=fee,
                clears_break_even=fee <= limit,
                cycles=m.completed_cycles,
                realized=m.realized_pnl,
                fees_paid=m.fees_paid,
                total_return_pct=m.total_return_pct,
                max_drawdown=m.max_drawdown,
            )
        )
    return rows
