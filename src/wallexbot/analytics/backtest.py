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
from decimal import ROUND_UP, Decimal
from typing import Any

from wallexbot.domain.market import OrderType, Side
from wallexbot.domain.order import Fill, OrderRequest
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import (
    Action,
    AlertAction,
    CancelAction,
    GridStrategy,
    PauseAction,
    PlaceAction,
)
from wallexbot.wallex.price_feed import PriceFeed, PriceFeedReplay, PriceTick

# Each tick offers this much volume, i.e. effectively unlimited liquidity.
UNLIMITED_VOLUME = Decimal("1000000000000")


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
        self._exchange_order_ids: dict[str, str] = {}  # strategy client_id -> exchange order id
        self._fills: list[Fill] = []
        self._events: list[str] = []
        self._rejected = 0
        self._fees_quote = Decimal(0)
        self._last_price = Decimal(0)
        self._has_run = False

    # --- helpers --------------------------------------------------------------------

    @property
    def _ticks(self) -> list[PriceTick]:
        if isinstance(self.price_feed, PriceFeedReplay):
            return self.price_feed.recorded_ticks
        return []

    def _equity(self, price: Decimal) -> Decimal:
        """Quote + base valued at `price` (locked funds count: they are still ours)."""
        balances = self.exchange.balances()
        market = self.exchange.market_info()
        quote = balances.get(market.quote)
        base = balances.get(market.base)
        return (quote.total if quote else Decimal(0)) + (base.total * price if base else Decimal(0))

    def _execute(self, actions: list[Action]) -> None:
        """Send strategy actions to the exchange; failures are counted, never fatal."""
        for action in actions:
            if isinstance(action, PlaceAction):
                self._place(action)
            elif isinstance(action, CancelAction):
                order_id = self._exchange_order_ids.get(action.client_id)
                if order_id is not None:
                    try:
                        self.exchange.cancel_order(order_id)
                    except ValueError:
                        pass  # already filled or cancelled
            elif isinstance(action, PauseAction):
                self._events.append(f"paused: {action.reason}")
            elif isinstance(action, AlertAction):
                self._events.append(f"{action.severity}: {action.message}")

    def _place(self, action: PlaceAction) -> None:
        request = OrderRequest(
            client_id=action.client_id,
            symbol=action.symbol,
            side=action.side,
            type=OrderType.LIMIT,
            price=action.price,
            quantity=action.quantity,
        )
        try:
            order = self.exchange.place_order(request)
        except (ValueError, RuntimeError) as exc:
            # Not enough funds, below the minimum size, rate limit...: the order never existed,
            # so the strategy must forget it, otherwise it would wait for a fill forever.
            self._rejected += 1
            self._events.append(f"rejected {action.side.value} level {action.level_index}: {exc}")
            self.strategy.on_cancel(action.level_index)
            return
        self._exchange_order_ids[action.client_id] = order.id

    def _seed_inventory(self, actions: list[Action], price: Decimal) -> None:
        """Decision D2: buy the coins the initial sell levels need, as a simulated taker."""
        needed = sum(
            (a.quantity for a in actions if isinstance(a, PlaceAction) and a.side == Side.SELL),
            Decimal(0),
        )
        if needed <= 0:
            return
        market = self.exchange.market_info()
        taker = self.exchange.fee_schedule().taker_rate
        step = market.amount_step
        # Buy a little extra so that what is left after the base-asset fee still covers the sells.
        gross = (needed / (1 - taker) / step).to_integral_value(rounding=ROUND_UP) * step
        try:
            fill = self.exchange.instant_buy(price, gross)
        except ValueError as exc:
            self._events.append(f"could not buy starting inventory: {exc}")
            return
        self._fees_quote += fill.fee * price

    def _fee_in_quote(self, fill: Fill) -> Decimal:
        if fill.fee_asset == self.exchange.market_info().base:
            return fill.fee * fill.price
        return fill.fee

    def _on_fills(self, fills: list[Fill]) -> None:
        for fill in fills:
            self._fills.append(fill)
            self._fees_quote += self._fee_in_quote(fill)
            order = self.exchange.get_order(fill.order_id)
            state = self.strategy.state
            level = state.get_level_for_order(order.client_id) if state else None
            if level is None:
                continue
            self._execute(
                self.strategy.on_fill(
                    level, fill.quantity, fill.fee, fill.fee_asset, fill.timestamp
                )
            )

    # --- main loop ------------------------------------------------------------------

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
        initial_equity = self._equity(first.price)

        start_actions = self.strategy.on_start(first.price, first.timestamp)
        self._seed_inventory(start_actions, first.price)
        self._execute(start_actions)

        params = self.strategy.params
        curve: list[Decimal] = [self._equity(first.price)]
        in_range_time = 0
        total_time = 0
        out_of_range = not (params.lower_price <= first.price <= params.upper_price)

        for previous, tick in zip(ticks, ticks[1:], strict=False):
            self._clock.set_time(tick.timestamp / 1000.0)
            self._last_price = tick.price
            span = tick.timestamp - previous.timestamp
            total_time += span

            inside = params.lower_price <= tick.price <= params.upper_price
            if inside:
                in_range_time += span
            if not inside and not out_of_range:
                self._events.append(
                    f"price {tick.price} left the grid range "
                    f"[{params.lower_price}, {params.upper_price}]"
                )
            out_of_range = not inside

            self._execute(self.strategy.on_price(tick.price, tick.timestamp))
            self._on_fills(
                self.exchange.process_trade(tick.price, UNLIMITED_VOLUME, tick.timestamp)
            )
            curve.append(self._equity(tick.price))

        metrics = self._metrics(initial_equity, curve, first.price, in_range_time, total_time)
        return BacktestResult(
            metrics=metrics,
            config_snapshot={},
            start_time=first.timestamp,
            end_time=ticks[-1].timestamp,
            fills=self._fills,
            events=self._events,
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
            fees_paid=self._fees_quote,
            time_in_range=in_range,
            buy_and_hold_return=buy_hold,
            outperformance=total_return - buy_hold,
            rejected_orders=self._rejected,
            equity_curve=curve,
        )
