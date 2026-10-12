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

        # Check stop price for STOP_* orders
        if request.type in (OrderType.STOP_LIMIT, OrderType.STOP_MARKET):
            if request.stop_price is None:
                raise ValueError(f"{request.type} order requires stop_price")

    def _lock_funds(self, request: OrderRequest) -> None:
        """Lock funds for order."""
        if request.side == Side.BUY:
            # Lock quote currency
            required = request.price * request.quantity if request.price else Decimal("0")
            # Add estimated fee
            fee = self._fee_schedule.calculate_fee_quote(required, is_maker=True)
            total = required + fee
            quote_asset = self.market.quote
            if quote_asset not in self._balances:
                self._balances[quote_asset] = Balance(free=Decimal("0"), locked=Decimal("0"))
            self._balances[quote_asset] = self._balances[quote_asset].lock(total)
        else:
            # Lock base currency
            base_asset = self.market.base
            if base_asset not in self._balances:
                self._balances[base_asset] = Balance(free=Decimal("0"), locked=Decimal("0"))
            # Add estimated fee in base
            fee = self._fee_schedule.calculate_fee_base(request.quantity, is_maker=True)
            total = request.quantity + fee
            self._balances[base_asset] = self._balances[base_asset].lock(total)

    @staticmethod
    def _limit_price(order: Order) -> Decimal:
        """Price of a resting order; MARKET orders have none and are not simulated yet."""
        if order.price is None:
            raise NotImplementedError("market orders are not simulated yet (see docs/AUDIT.md)")
        return order.price

    def _unlock_funds(self, order: Order) -> None:
        """Unlock funds for canceled order."""
        if order.side == Side.BUY:
            quote_asset = self.market.quote
            locked_value = self._limit_price(order) * order.remaining_quantity
            fee = self._fee_schedule.calculate_fee_quote(locked_value, is_maker=True)
            total = locked_value + fee
            self._balances[quote_asset] = self._balances[quote_asset].unlock(total)
        else:
            base_asset = self.market.base
            locked_qty = order.remaining_quantity
            fee = self._fee_schedule.calculate_fee_base(locked_qty, is_maker=True)
            total = locked_qty + fee
            self._balances[base_asset] = self._balances[base_asset].unlock(total)

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
            fee_asset=self.market.quote if request.side == Side.BUY else self.market.base,
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

        # Check stop triggers
        triggered = self._matching_engine.check_stop_triggers(price)
        for order in triggered:
            # Re-lock funds for the now-active order
            self._lock_funds_for_active_order(order)

        return fills

    def _apply_fill(self, fill: Fill, order: Order) -> None:
        """Apply fill to balances."""
        if order.side == Side.BUY:
            # Received base, paid quote (already locked)
            # Unlock remaining quote
            remaining_quote = self._limit_price(order) * order.remaining_quantity
            fee = self._fee_schedule.calculate_fee_quote(remaining_quote, is_maker=True)
            total_locked = remaining_quote + fee
            self._balances[self.market.quote] = self._balances[self.market.quote].unlock(
                total_locked
            )

            # Add base to free
            base_asset = self.market.base
            if base_asset not in self._balances:
                self._balances[base_asset] = Balance(free=Decimal("0"), locked=Decimal("0"))
            self._balances[base_asset] = self._balances[base_asset].add(fill.quantity)

            # Deduct fee from quote (already accounted in unlock)
        else:
            # Received quote, paid base (already locked)
            # Unlock remaining base
            remaining_base = order.remaining_quantity
            fee = self._fee_schedule.calculate_fee_base(remaining_base, is_maker=True)
            total_locked = remaining_base + fee
            self._balances[self.market.base] = self._balances[self.market.base].unlock(total_locked)

            # Add quote to free
            quote_value = fill.price * fill.quantity
            quote_asset = self.market.quote
            if quote_asset not in self._balances:
                self._balances[quote_asset] = Balance(free=Decimal("0"), locked=Decimal("0"))
            self._balances[quote_asset] = self._balances[quote_asset].add(quote_value)

            # Deduct fee from base (already accounted in unlock)

    def _lock_funds_for_active_order(self, order: Order) -> None:
        """Lock funds for an activated stop order."""
        # Similar to _lock_funds but for already-created order
        if order.side == Side.BUY:
            required = self._limit_price(order) * order.quantity
            fee = self._fee_schedule.calculate_fee_quote(required, is_maker=True)
            total = required + fee
            quote_asset = self.market.quote
            if quote_asset not in self._balances:
                self._balances[quote_asset] = Balance(free=Decimal("0"), locked=Decimal("0"))
            self._balances[quote_asset] = self._balances[quote_asset].lock(total)
        else:
            base_asset = self.market.base
            if base_asset not in self._balances:
                self._balances[base_asset] = Balance(free=Decimal("0"), locked=Decimal("0"))
            fee = self._fee_schedule.calculate_fee_base(order.quantity, is_maker=True)
            total = order.quantity + fee
            self._balances[base_asset] = self._balances[base_asset].lock(total)

    # Event stream for Phase 5.9
    def event_stream(self) -> None:
        """Generate event stream (OrderUpdated, FillOccurred, BalanceUpdated)."""
        # This would be implemented as an async generator
        pass
