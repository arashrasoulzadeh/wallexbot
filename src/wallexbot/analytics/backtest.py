"""Backtester for the grid strategy.

Replays a price path through `GridStrategy` and `SimulatedExchange` (paper trading, no API keys):

1. At the first price it places the initial grid. The coins needed for the sell levels are bought
   as a simulated taker at that price (decision D2).
2. Every later tick is offered to the exchange as a trade; filled orders are reported to the
   strategy and its counter-orders are placed, exactly like a live run would.
3. Equity is marked to market at every tick; metrics are computed from that curve and the ledger.

Modelling limits (kept deliberately simple): every tick offers unlimited liquidity, so a limit
order fills completely as soon as price trades through it; there is no queue position and no
slippage. A "pause" from the strategy (price left the grid range) is recorded as an event but does
not stop counter-orders, since the grid has no other way to order.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from wallexbot.domain.order import Fill
from wallexbot.engine.session import TradingSession
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.wallex.price_feed import PriceFeed, PriceFeedReplay, PriceTick


@dataclass
class BacktestMetrics:
    """Backtest performance metrics (money in quote asset, percentages in %)."""

    realized_pnl: Decimal = Decimal("0")  # completed grid cycles, net of maker fees
    unrealized_pnl: Decimal = Decimal("0")  # everything else: held inventory, entry fee
    total_return_pct: Decimal = Decimal("0")
    completed_cycles: int = 0
    avg_profit_per_cycle: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")  # largest peak-to-trough equity fall
    fees_paid: Decimal = Decimal("0")  # all fees, valued in quote asset
    time_in_range: Decimal = Decimal("0")
    buy_and_hold_return: Decimal = Decimal("0")  # price change over the run
    outperformance: Decimal = Decimal("0")
    rejected_orders: int = 0

    # Equity (quote asset) after every tick
    equity_curve: list[Decimal] = field(default_factory=list)


@dataclass
class BacktestResult:
    """Backtest result."""

    metrics: BacktestMetrics
    config_snapshot: dict[str, Any]
    start_time: int
    end_time: int
    fills: list[Fill] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


class _SimClock:
    """Clock that only moves when the backtester sets it (simulated time)."""

    def __init__(self) -> None:
        self._time = 0.0

    def now(self) -> float:
        return self._time

    def sleep(self, seconds: float) -> None:
        self._time += seconds

    async def async_sleep(self, seconds: float) -> None:
        self._time += seconds

    def set_time(self, timestamp: float) -> None:
        self._time = timestamp


class Backtester:
    """Runs a backtest of `strategy` on `exchange` over the ticks of `price_feed`."""

    def __init__(
        self,
        strategy: GridStrategy,
        exchange: SimulatedExchange,
        price_feed: PriceFeed,
    ) -> None:
        self.strategy = strategy
        self.exchange = exchange
        self.price_feed = price_feed
        self._clock = _SimClock()
        self.exchange.use_clock(self._clock)  # rate limits run on simulated time
        self.session = TradingSession(strategy, exchange)
        self._last_price = Decimal(0)
        self._has_run = False

    @property
    def _ticks(self) -> list[PriceTick]:
        if isinstance(self.price_feed, PriceFeedReplay):
            return self.price_feed.recorded_ticks
        return []

    def run(self) -> BacktestResult:
        """Replay all ticks and return the result. A Backtester runs once; build a new one to rerun."""
        if self._has_run:
            raise RuntimeError(
                "this Backtester already ran; create a new one (exchange state is used up)"
            )
        self._has_run = True
        ticks = self._ticks
        if not ticks:
            return BacktestResult(BacktestMetrics(), {}, 0, 0)

        first = ticks[0]
        self._clock.set_time(first.timestamp / 1000.0)
        self._last_price = first.price
        initial_equity = self.session.equity(first.price)

        self.session.start(first.price, first.timestamp)

        params = self.strategy.params
        curve: list[Decimal] = [self.session.equity(first.price)]
        in_range_time = 0
        total_time = 0

        for previous, tick in zip(ticks, ticks[1:], strict=False):
            self._clock.set_time(tick.timestamp / 1000.0)
            self._last_price = tick.price
            span = tick.timestamp - previous.timestamp
            total_time += span
            if params.lower_price <= tick.price <= params.upper_price:
                in_range_time += span

            self.session.on_tick(tick.price, tick.timestamp)
            curve.append(self.session.equity(tick.price))

        metrics = self._metrics(initial_equity, curve, first.price, in_range_time, total_time)
        return BacktestResult(
            metrics=metrics,
            config_snapshot={},
            start_time=first.timestamp,
            end_time=ticks[-1].timestamp,
            fills=self.session.fills,
            events=self.session.events,
        )

    def _metrics(
        self,
        initial_equity: Decimal,
        curve: list[Decimal],
        first_price: Decimal,
        in_range_time: int,
        total_time: int,
    ) -> BacktestMetrics:
        final_equity = curve[-1]
        total_pnl = final_equity - initial_equity
        total_return = total_pnl / initial_equity * 100 if initial_equity > 0 else Decimal(0)

        peak = Decimal(0)
        max_dd = Decimal(0)
        for equity in curve:
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak * 100)

        tracker = self.strategy.profit_tracker
        realized = tracker.total_profit
        cycles = tracker.total_cycles
        buy_hold = (self._last_price / first_price - 1) * 100 if first_price > 0 else Decimal(0)
        in_range = (
            Decimal(in_range_time) / Decimal(total_time) * 100 if total_time > 0 else Decimal(0)
        )

        return BacktestMetrics(
            realized_pnl=realized,
            unrealized_pnl=total_pnl - realized,
            total_return_pct=total_return,
            completed_cycles=cycles,
            avg_profit_per_cycle=realized / cycles if cycles else Decimal(0),
            max_drawdown=max_dd,
            fees_paid=self.session.fees_quote,
            time_in_range=in_range,
            buy_and_hold_return=buy_hold,
            outperformance=total_return - buy_hold,
            rejected_orders=self.session.rejected,
            equity_curve=curve,
        )
