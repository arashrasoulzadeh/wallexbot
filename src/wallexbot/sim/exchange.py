"""Simulated exchange for paper trading."""

from dataclasses import dataclass, field
from decimal import Decimal

from wallexbot.domain import Clock, SystemClock
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, OrderStatus, OrderType, Side
from wallexbot.domain.money import quantize_down
from wallexbot.domain.order import Fill, Order, OrderRequest
from wallexbot.sim.matching import FillModel, MatchingEngine
from wallexbot.sim.rate_limiter import RateLimiter


@dataclass
class SimulatedExchange:
    """In-memory simulated exchange with order matching."""

    market: Market
    initial_balances: dict[str, Balance]
    fee_schedule_config: FeeSchedule = field(
        default=FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.001"))
    )
    min_notional_rule: MinNotionalRule = field(
        default=MinNotionalRule(min_notional=Decimal("10"), min_quantity=Decimal("0.0001"))
    )
    fill_model: FillModel = FillModel.CONSERVATIVE
    clock: Clock = field(default_factory=SystemClock)

    # Internal fee schedule (set in __post_init__)
    _fee_schedule: FeeSchedule = field(init=False, repr=False)

    # Internal state
    _balances: dict[str, Balance] = field(default_factory=dict, init=False)
    _orders: dict[str, Order] = field(default_factory=dict, init=False)
    _client_ids: set[str] = field(default_factory=set, init=False)
    _matching_engine: MatchingEngine = field(init=False)
    _rate_limiter: RateLimiter = field(init=False)
    _order_sequence: int = field(default=0, init=False)

    # Fault injection
    _latency: float = field(default=0.0, init=False)
    _reject_next: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._fee_schedule = self.fee_schedule_config
        self._balances = self.initial_balances.copy()
        self._matching_engine = MatchingEngine(
            market=self.market,
            fee_schedule=self._fee_schedule,
            fill_model=self.fill_model,
        )
        self._rate_limiter = RateLimiter(
            max_requests=20,
            window_seconds=10,
            clock=self.clock,
        )

    # Fault injection methods
    def set_latency(self, seconds: float) -> None:
        """Set artificial latency for all operations."""
        self._latency = seconds

    def set_fault_injection(self, reject_next: bool = False) -> None:
        """Inject faults for testing."""
        self._reject_next = reject_next

    def _apply_latency(self) -> None:
        """Apply configured latency."""
        if self._latency > 0:
            self.clock.sleep(self._latency)
            # For async contexts, use async_sleep
            # This is a sync method so we use the sync sleep

    def _check_rate_limit(self) -> None:
        """Check rate limit, raise if exceeded."""
        if not self._rate_limiter.acquire():
            raise RuntimeError("Rate limit exceeded: 20 requests per 10 seconds")

    def _validate_order_request(self, request: OrderRequest) -> None:
        """Validate order request against exchange rules."""
        # Check client_id uniqueness
        if request.client_id in self._client_ids:
            raise ValueError(f"Duplicate client_id: {request.client_id}")

        # Check price precision
        if request.price is not None:
            price_step = self.market.price_step
            if request.price != quantize_down(request.price, price_step):
                raise ValueError(
                    f"Price precision exceeds market limit: {self.market.price_precision} decimals"
                )

        # Check quantity precision
        qty_step = self.market.amount_step
        if request.quantity != quantize_down(request.quantity, qty_step):
            raise ValueError(
                f"Quantity precision exceeds market limit: {self.market.amount_precision} decimals"
            )

        # Check min notional
        if request.price is not None:
            notional = request.price * request.quantity
            if notional < self.min_notional_rule.min_notional:
                raise ValueError(
                    f"Order notional {notional} below minimum {self.min_notional_rule.min_notional}"
                )

        # Check min quantity
        if request.quantity < self.min_notional_rule.min_quantity:
            raise ValueError(
                f"Order quantity {request.quantity} below minimum {self.min_notional_rule.min_quantity}"
            )

        if request.type in (OrderType.MARKET, OrderType.STOP_MARKET):
            raise ValueError("market orders are not supported by the simulator yet")

        # Check stop price for STOP_* orders
        if request.type in (OrderType.STOP_LIMIT, OrderType.STOP_MARKET):
            if request.stop_price is None:
                raise ValueError(f"{request.type} order requires stop_price")

    def _balance(self, asset: str) -> Balance:
        return self._balances.get(asset, Balance(free=Decimal("0"), locked=Decimal("0")))

    def _lock_funds(self, request: OrderRequest) -> None:
        """Lock the funds an order needs. Fees are taken from what is received, so nothing extra
        is locked: BUY locks price * quantity of quote, SELL locks quantity of base."""
        if request.price is None:
            raise ValueError("market orders are not supported by the simulator yet")
        if request.side == Side.BUY:
            asset, amount = self.market.quote, request.price * request.quantity
        else:
            asset, amount = self.market.base, request.quantity
        self._balances[asset] = self._balance(asset).lock(amount)

    @staticmethod
    def _limit_price(order: Order) -> Decimal:
        """Price of a resting order; MARKET orders have none and are not simulated yet."""
        if order.price is None:
            raise NotImplementedError("market orders are not simulated yet (see docs/AUDIT.md)")
        return order.price

    def _unlock_funds(self, order: Order) -> None:
        """Release what is still locked for the unfilled part of a cancelled order."""
        remaining = order.remaining_quantity
        if order.side == Side.BUY:
            asset, amount = self.market.quote, self._limit_price(order) * remaining
        else:
            asset, amount = self.market.base, remaining
        self._balances[asset] = self._balance(asset).unlock(amount)

    def place_order(self, request: OrderRequest) -> Order:
        """Place a new order."""
        self._apply_latency()
        self._check_rate_limit()

        if self._reject_next:
            self._reject_next = False
            raise RuntimeError("Injected order rejection")

        self._validate_order_request(request)
        self._lock_funds(request)

        # Create order
        order_id = f"ord_{self._order_sequence}"
        self._order_sequence += 1
        self._client_ids.add(request.client_id)

        now = int(self.clock.now() * 1000)

        order = Order(
            id=order_id,
            client_id=request.client_id,
            symbol=request.symbol,
            side=request.side,
            type=request.type,
            price=request.price,
            quantity=request.quantity,
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset=self.market.base if request.side == Side.BUY else self.market.quote,
            is_maker=(request.type == OrderType.LIMIT),
            created_at=now,
            updated_at=now,
        )

        # Add to matching engine
        if request.type in (OrderType.STOP_LIMIT, OrderType.STOP_MARKET):
            assert request.stop_price is not None  # checked in validation above
            self._matching_engine.add_stop_order(order, request.stop_price)
        else:
            self._matching_engine.add_order(order)

        self._orders[order_id] = order
        return order

    def use_clock(self, clock: Clock) -> None:
        """Drive the exchange (and its rate limiter) from another clock, e.g. simulated time."""
        self.clock = clock
        self._rate_limiter = RateLimiter(max_requests=20, window_seconds=10, clock=clock)

    def instant_buy(self, price: Decimal, quantity: Decimal) -> Fill:
        """Buy at a given price right now as a taker (used to seed starting inventory).

        Costs price * quantity of quote; the taker fee is charged in the base asset received.
        """
        base, quote = self.market.base, self.market.quote
        cost = price * quantity
        self._balances[quote] = self._balance(quote).subtract(cost)  # raises if insufficient
        fee = (quantity * self._fee_schedule.taker_rate).quantize(Decimal("0.00000001"))
        self._balances[base] = self._balance(base).add(quantity - fee)
        self._order_sequence += 1
        return Fill(
            order_id=f"instant_{self._order_sequence}",
            trade_id=f"instant_{self._order_sequence}",
            price=price,
            quantity=quantity,
            fee=fee,
            fee_asset=base,
            is_maker=False,
            timestamp=int(self.clock.now() * 1000),
        )

    def cancel_order(self, order_id: str) -> None:
        """Cancel an open order."""
        self._apply_latency()
        self._check_rate_limit()

        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")

        if not order.is_active:
            raise ValueError(f"Order not active: {order_id}")

        # Remove from matching engine
        self._matching_engine.remove_order(order_id)

        # Unlock funds
        self._unlock_funds(order)

        # Update order status
        now = int(self.clock.now() * 1000)
        object.__setattr__(order, "status", OrderStatus.CANCELED)
        object.__setattr__(order, "updated_at", now)

    def get_order(self, order_id: str) -> Order:
        """Get order by ID."""
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")
        return order

    def open_orders(self) -> list[Order]:
        """Get all open orders."""
        return self._matching_engine.get_open_orders()

    def balances(self) -> dict[str, Balance]:
        """Get current balances."""
        return self._balances.copy()

    def fee_schedule(self) -> FeeSchedule:
        """Get fee schedule."""
        return self._fee_schedule

    def market_info(self) -> Market:
        """Get market info."""
        return self.market

    def process_trade(self, price: Decimal, quantity: Decimal, timestamp: int) -> list[Fill]:
        """Process a trade through the matching engine."""
        fills = self._matching_engine.process_trade(price, quantity, timestamp)

        # Update balances based on fills
        for fill in fills:
            order = self._orders.get(fill.order_id)
            if order:
                self._apply_fill(fill, order)

        # Stop-limit orders were fully funded when placed; triggering just activates them.
        self._matching_engine.check_stop_triggers(price)

        return fills

    def _apply_fill(self, fill: Fill, order: Order) -> None:
        """Settle a fill: spend the locked funds exactly, credit what was received minus the fee
        (charged in the received asset, as Wallex does)."""
        base, quote = self.market.base, self.market.quote
        value = fill.price * fill.quantity
        if order.side == Side.BUY:
            self._balances[quote] = self._balance(quote).unlock(value).subtract(value)
            self._balances[base] = self._balance(base).add(fill.quantity - fill.fee)
        else:
            self._balances[base] = self._balance(base).unlock(fill.quantity).subtract(fill.quantity)
            self._balances[quote] = self._balance(quote).add(value - fill.fee)

    # Event stream for Phase 5.9
    def event_stream(self) -> None:
        """Generate event stream (OrderUpdated, FillOccurred, BalanceUpdated)."""
        # This would be implemented as an async generator
        pass
