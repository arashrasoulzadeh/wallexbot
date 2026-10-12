"""Backtester for grid strategy."""

from dataclasses import dataclass, field
from decimal import Decimal

from wallexbot.domain.market import Side
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.wallex.price_feed import PriceFeed, PriceFeedReplay, PriceTick


@dataclass
class BacktestMetrics:
    """Backtest performance metrics."""

    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_return_pct: Decimal = Decimal("0")
    completed_cycles: int = 0
    avg_profit_per_cycle: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    fees_paid: Decimal = Decimal("0")
    time_in_range: Decimal = Decimal("0")
    buy_and_hold_return: Decimal = Decimal("0")
    outperformance: Decimal = Decimal("0")

    # Equity curve for drawdown calculation
    equity_curve: list[Decimal] = field(default_factory=list)


@dataclass
class BacktestResult:
    """Backtest result."""

    metrics: BacktestMetrics
    config_snapshot: dict
    start_time: int
    end_time: int


class _BacktestClock:
    """Simple clock for backtesting."""

    def __init__(self) -> None:
        self._time = 0.0

    def now(self) -> float:
        return self._time

    def sleep(self, seconds: float) -> None:
        self._time += seconds

    def set_time(self, timestamp: float) -> None:
        self._time = timestamp


class Backtester:
    """Runs backtests on historical data."""

    def __init__(
        self,
        strategy: GridStrategy,
        exchange: SimulatedExchange,
        price_feed: PriceFeed,
    ) -> None:
        self.strategy = strategy
        self.exchange = exchange
        self.price_feed = price_feed
        self._clock = _BacktestClock()
        self._initial_equity: Decimal | None = None
        self._peak_equity: Decimal | None = None
        self._in_range_time = 0
        self._total_time = 0
        self._last_price: Decimal | None = None

    def run(self) -> BacktestResult:
        """Run backtest and return results."""
        # Initialize
        self._clock.set_time(0)
        self._initial_equity = self._calculate_equity()
        self._peak_equity = self._initial_equity

        # Get first price for strategy initialization
        first_tick = None
        ticks = []

        # Collect all ticks first (for replay feed)
        if isinstance(self.price_feed, PriceFeedReplay):
            ticks = self.price_feed._ticks

        if ticks:
            first_tick = ticks[0]
            # Initialize strategy with first price
            self.strategy.on_start(current_price=first_tick.price, timestamp=first_tick.timestamp)

        # Process each tick
        for i, tick in enumerate(ticks):
            self._clock.set_time(tick.timestamp / 1000.0)  # Convert ms to seconds
            self._last_price = tick.price

            # Update time tracking
            if i > 0:
                time_diff = tick.timestamp - ticks[i-1].timestamp
                self._total_time += time_diff
                # Check if in range
                params = self.strategy.params
                if params.lower_price <= tick.price <= params.upper_price:
                    self._in_range_time += time_diff

            # Handle price update
            actions = self.strategy.on_price(current_price=tick.price, timestamp=tick.timestamp)
            # Execute actions on exchange
            for action in actions:
                self._execute_action(action)

            # Process any fills from exchange
            # In backtest, fills happen immediately on price touch
            self._process_fills(tick.price, tick.timestamp)

            # Update equity curve
            equity = self._calculate_equity()
            self._update_drawdown(equity)

        # Final calculations
        final_equity = self._calculate_equity()
        metrics = self._calculate_metrics(final_equity)

        return BacktestResult(
            metrics=metrics,
            config_snapshot={},
            start_time=ticks[0].timestamp if ticks else 0,
            end_time=ticks[-1].timestamp if ticks else 0,
        )

    def _execute_action(self, action) -> None:
        """Execute action on exchange."""
        from wallexbot.domain.order import OrderRequest
        from wallexbot.strategy.grid.interface import CancelAction, PlaceAction

        if isinstance(action, PlaceAction):
            request = OrderRequest(
                client_id=action.client_id,
                symbol=action.symbol,
                side=action.side,
                type=action.order_type,
                price=action.price,
                quantity=action.quantity,
            )
            self.exchange.place_order(request)
        elif isinstance(action, CancelAction):
            self.exchange.cancel_order(action.client_id)

    def _process_fills(self, current_price: Decimal, timestamp: int) -> None:
        """Process fills at current price."""
        # Get open orders
        open_orders = self.exchange.open_orders()

        for order in open_orders:
            if not order.is_active:
                continue

            # Check if order should fill
            should_fill = False
            if order.side == Side.BUY and current_price <= order.price:
                should_fill = True
            elif order.side == Side.SELL and current_price >= order.price:
                should_fill = True

            if should_fill:
                # Calculate fill quantity
                fill_qty = order.remaining_quantity
                fill_fee = self.exchange.fee_schedule().calculate_fee(
                    order.price, fill_qty, order.side, order.is_maker
                )
                fee_asset = order.fee_asset

                # Handle fill in strategy
                # Find level index for this order
                level_index = self._find_level_for_order(order.id)
                if level_index is not None:
                    self.strategy.on_fill(
                        level_index=level_index,
                        fill_qty=fill_qty,
                        fill_fee=fill_fee,
                        fill_fee_asset=fee_asset,
                        timestamp=timestamp,
                    )

                # Update order in exchange
                self.exchange.process_trade(order.price, fill_qty, timestamp)

    def _find_level_for_order(self, order_id: str) -> int | None:
        """Find level index for order."""
        # This would need access to strategy state
        # For now, return None
        return None

    def _calculate_equity(self) -> Decimal:
        """Calculate current equity in quote currency."""
        balances = self.exchange.balances()
        quote = self.exchange.market_info().quote
        base = self.exchange.market_info().base

        quote_balance = balances.get(quote, None)
        base_balance = balances.get(base, None)

        equity = Decimal("0")
        if quote_balance:
            equity += quote_balance.total
        if base_balance and self._last_price:
            equity += base_balance.total * self._last_price

        return equity

    def _update_drawdown(self, equity: Decimal) -> None:
        """Update peak equity and drawdown."""
        if equity > self._peak_equity:
            self._peak_equity = equity

    def _calculate_metrics(self, final_equity: Decimal) -> BacktestMetrics:
        """Calculate final metrics."""
        realized = final_equity - self._initial_equity
        total_return = (realized / self._initial_equity * 100) if self._initial_equity > 0 else Decimal("0")

        # Max drawdown
        if self._peak_equity > 0:
            max_dd = (self._peak_equity - final_equity) / self._peak_equity * 100
        else:
            max_dd = Decimal("0")

        # Time in range
        time_in_range = (self._in_range_time / self._total_time * 100) if self._total_time > 0 else Decimal("0")

        # Buy and hold
        buy_hold = Decimal("0")
        if self._last_price and len(self._ticks) > 1:
            first_price = self._ticks[0].price
            buy_hold = (self._last_price - first_price) / first_price * 100

        return BacktestMetrics(
            realized_pnl=realized,
            total_return_pct=total_return,
            max_drawdown=max_dd,
            time_in_range=time_in_range,
            buy_and_hold_return=buy_hold,
            outperformance=total_return - buy_hold,
        )

    @property
    def _ticks(self) -> list[PriceTick]:
        if isinstance(self.price_feed, PriceFeedReplay):
            return self.price_feed._ticks
        return []
