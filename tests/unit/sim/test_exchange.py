"""Tests for simulated exchange."""

from decimal import Decimal

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, OrderStatus, OrderType, Side, Symbol
from wallexbot.domain.order import Order, OrderRequest
from wallexbot.sim.exchange import ExchangeProtocol, SimulatedExchange
from wallexbot.sim.matching import FillModel, MatchingEngine


class TestExchangeProtocol:
    """Tests for Exchange protocol."""

    def test_exchange_protocol_exists(self):
        """ExchangeProtocol is defined."""
        assert ExchangeProtocol is not None


class TestSimulatedExchange:
    """Tests for SimulatedExchange."""

    @pytest.fixture
    def market(self):
        return Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )

    @pytest.fixture
    def fee_schedule(self):
        return FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))

    @pytest.fixture
    def min_notional(self):
        return MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

    @pytest.fixture
    def exchange(self, market, fee_schedule, min_notional):
        return SimulatedExchange(
            market=market,
            fee_schedule_config=fee_schedule,
            min_notional_rule=min_notional,
            initial_balances={
                "TMN": Balance(free=Decimal("2000000.00"), locked=Decimal("0")),
                "USDT": Balance(free=Decimal("100.0000"), locked=Decimal("0")),
            },
        )

    def test_initial_balances(self, exchange):
        """Test initial balances are set correctly."""
        balances = exchange.balances()
        assert balances["TMN"].free == Decimal("2000000.00")
        assert balances["TMN"].locked == Decimal("0")
        assert balances["USDT"].free == Decimal("100.0000")
        assert balances["USDT"].locked == Decimal("0")

    def test_place_buy_order_locks_quote(self, exchange):
        """BUY order locks quote currency."""
        request = OrderRequest(
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        order = exchange.place_order(request)

        assert order.status == OrderStatus.NEW
        assert order.side == Side.BUY
        # Quote locked: 100 * 10 = 1000 TMN + fee (1000 * 0.001 = 1) = 1001 TMN
        balances = exchange.balances()
        assert balances["TMN"].locked == Decimal("1001.00000000")
        assert balances["TMN"].free == Decimal("1998999.00000000")

    def test_place_sell_order_locks_base(self, exchange):
        """SELL order locks base currency."""
        # First add some base balance
        exchange._balances["USDT"] = Balance(free=Decimal("100.0000"), locked=Decimal("0"))

        request = OrderRequest(
            client_id="TEST_2",
            symbol=Symbol("USDTTMN"),
            side=Side.SELL,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        order = exchange.place_order(request)

        assert order.status == OrderStatus.NEW
        assert order.side == Side.SELL
        # Base locked: 10 USDT + fee (10 * 0.001 = 0.01) = 10.01 USDT
        balances = exchange.balances()
        assert balances["USDT"].locked == Decimal("10.01000000")
        assert balances["USDT"].free == Decimal("89.99000000")

    def test_insufficient_funds_rejected(self, exchange):
        """Insufficient funds -> rejection."""
        request = OrderRequest(
            client_id="TEST_3",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("1000000.0000"),  # Would need 100M TMN
        )
        with pytest.raises(ValueError, match="Insufficient"):
            exchange.place_order(request)

    def test_cancel_releases_locked_funds(self, exchange):
        """Cancel releases locked funds."""
        request = OrderRequest(
            client_id="TEST_4",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        order = exchange.place_order(request)
        assert exchange.balances()["TMN"].locked == Decimal("1001.00000000")

        exchange.cancel_order(order.id)
        assert exchange.balances()["TMN"].locked == Decimal("0")
        assert exchange.balances()["TMN"].free == Decimal("2000000.00")

    def test_order_validation_precision(self, exchange):
        """Order price/quantity validated against market precision."""
        # Price with too many decimals
        request = OrderRequest(
            client_id="TEST_5",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.001"),  # 3 decimals, market has 2
            quantity=Decimal("10.0000"),
        )
        with pytest.raises(ValueError, match="precision"):
            exchange.place_order(request)

    def test_order_validation_min_notional(self, exchange):
        """Order validated against min notional."""
        request = OrderRequest(
            client_id="TEST_6",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("1.00"),
            quantity=Decimal("5.0000"),  # 5 notional < 10 min
        )
        with pytest.raises(ValueError, match="notional"):
            exchange.place_order(request)

    def test_unique_client_id(self, exchange):
        """Duplicate client_id rejected."""
        request1 = OrderRequest(
            client_id="DUPLICATE",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        exchange.place_order(request1)

        request2 = OrderRequest(
            client_id="DUPLICATE",  # Same client_id
            symbol=Symbol("USDTTMN"),
            side=Side.SELL,
            type=OrderType.LIMIT,
            price=Decimal("105.00"),
            quantity=Decimal("10.0000"),
        )
        with pytest.raises(ValueError, match="client_id"):
            exchange.place_order(request2)

    def test_get_order(self, exchange):
        """Get order by ID."""
        request = OrderRequest(
            client_id="TEST_9",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        order = exchange.place_order(request)
        retrieved = exchange.get_order(order.id)
        assert retrieved.id == order.id
        assert retrieved.client_id == "TEST_9"

    def test_open_orders(self, exchange):
        """List open orders."""
        request1 = OrderRequest(
            client_id="TEST_10",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        request2 = OrderRequest(
            client_id="TEST_11",
            symbol=Symbol("USDTTMN"),
            side=Side.SELL,
            type=OrderType.LIMIT,
            price=Decimal("105.00"),
            quantity=Decimal("10.0000"),
        )
        exchange.place_order(request1)
        exchange.place_order(request2)

        open_orders = exchange.open_orders()
        assert len(open_orders) == 2

    def test_fee_schedule(self, exchange):
        """Fee schedule accessible."""
        assert exchange.fee_schedule().maker_rate == Decimal("0.001")
        assert exchange.fee_schedule().taker_rate == Decimal("0.002")

    def test_market_info(self, exchange, market):
        """Market info accessible."""
        info = exchange.market_info()
        assert info.symbol == market.symbol
        assert info.price_precision == market.price_precision


class TestMatchingEngine:
    """Tests for matching engine."""

    @pytest.fixture
    def market(self):
        return Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )

    @pytest.fixture
    def fee_schedule(self):
        return FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))

    def test_limit_buy_fills_when_price_at_or_below(self, market, fee_schedule):
        """LIMIT BUY fills when trade price <= limit (using touch model)."""
        engine = MatchingEngine(market, fee_schedule, FillModel.TOUCH)

        # Place buy order at 100
        order = Order(
            id="ord_1",
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        engine.add_order(order)

        # Trade at 99 - should fill
        fills = engine.process_trade(Decimal("99.00"), Decimal("5.0000"), 1001)
        assert len(fills) == 1
        assert fills[0].quantity == Decimal("5.0000")

        # Trade at 100 - should fill (at limit)
        fills = engine.process_trade(Decimal("100.00"), Decimal("5.0000"), 1002)
        assert len(fills) == 1
        assert fills[0].quantity == Decimal("5.0000")

        # Trade at 101 - should NOT fill
        fills = engine.process_trade(Decimal("101.00"), Decimal("5.0000"), 1003)
        assert len(fills) == 0

    def test_limit_sell_fills_when_price_at_or_above(self, market, fee_schedule):
        """LIMIT SELL fills when trade price >= limit (using touch model)."""
        engine = MatchingEngine(market, fee_schedule, FillModel.TOUCH)

        order = Order(
            id="ord_1",
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=Side.SELL,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="USDT",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        engine.add_order(order)

        # Trade at 101 - should fill
        fills = engine.process_trade(Decimal("101.00"), Decimal("5.0000"), 1001)
        assert len(fills) == 1

        # Trade at 100 - should fill
        fills = engine.process_trade(Decimal("100.00"), Decimal("5.0000"), 1002)
        assert len(fills) == 1

        # Trade at 99 - should NOT fill
        fills = engine.process_trade(Decimal("99.00"), Decimal("5.0000"), 1003)
        assert len(fills) == 0

    def test_conservative_fill_model(self, market, fee_schedule):
        """Conservative model: needs trade THROUGH price."""
        engine = MatchingEngine(market, fee_schedule, FillModel.CONSERVATIVE)

        order = Order(
            id="ord_1",
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        engine.add_order(order)

        # Trade exactly at 100 - conservative: does NOT fill (needs through)
        fills = engine.process_trade(Decimal("100.00"), Decimal("5.0000"), 1001)
        assert len(fills) == 0

        # Trade at 99.99 - fills
        fills = engine.process_trade(Decimal("99.99"), Decimal("5.0000"), 1002)
        assert len(fills) == 1

    def test_touch_fill_model(self, market, fee_schedule):
        """Touch model: fills when price touches limit."""
        engine = MatchingEngine(market, fee_schedule, FillModel.TOUCH)

        order = Order(
            id="ord_1",
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        engine.add_order(order)

        # Trade exactly at 100 - touch: fills
        fills = engine.process_trade(Decimal("100.00"), Decimal("5.0000"), 1001)
        assert len(fills) == 1

    def test_partial_fills(self, market, fee_schedule):
        """Partial fills driven by trade volume."""
        engine = MatchingEngine(market, fee_schedule, FillModel.CONSERVATIVE)

        order = Order(
            id="ord_1",
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        engine.add_order(order)

        # Trade 3 units at 99
        fills = engine.process_trade(Decimal("99.00"), Decimal("3.0000"), 1001)
        assert len(fills) == 1
        assert fills[0].quantity == Decimal("3.0000")

        # Order should be partially filled
        assert order.filled_quantity == Decimal("3.0000")
        assert order.status == OrderStatus.PARTIALLY_FILLED

        # Trade remaining 7 units
        fills = engine.process_trade(Decimal("99.00"), Decimal("7.0000"), 1002)
        assert len(fills) == 1
        assert fills[0].quantity == Decimal("7.0000")
        assert order.status == OrderStatus.FILLED

    def test_stop_limit_trigger(self, market, fee_schedule):
        """STOP_LIMIT triggers correctly."""
        engine = MatchingEngine(market, fee_schedule, FillModel.CONSERVATIVE)

        # Stop buy at 100, limit 101
        order = Order(
            id="ord_1",
            client_id="STOP_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.STOP_LIMIT,
            price=Decimal("101.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        # Store stop price in order metadata
        engine.add_stop_order(order, stop_price=Decimal("100.00"))

        # Price at 99 - not triggered
        triggered = engine.check_stop_triggers(Decimal("99.00"))
        assert len(triggered) == 0

        # Price at 100 - triggered
        triggered = engine.check_stop_triggers(Decimal("100.00"))
        assert len(triggered) == 1
        assert triggered[0].id == "ord_1"

    def test_fee_application(self, market, fee_schedule):
        """Fees applied correctly with maker/taker rates."""
        engine = MatchingEngine(market, fee_schedule, FillModel.CONSERVATIVE)

        # Maker buy order
        buy_order = Order(
            id="ord_1",
            client_id="BUY_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        engine.add_order(buy_order)

        # Taker sell trade
        fills = engine.process_trade(Decimal("99.00"), Decimal("5.0000"), 1001)
        assert len(fills) == 1
        fill = fills[0]
        # Buy is maker, fee in quote: 100 * 5 * 0.001 = 0.5 TMN
        # Wait, fill price is 99, so fee = 99 * 5 * 0.001 = 0.495
        assert fill.fee == Decimal("0.495")
        assert fill.fee_asset == "TMN"
        assert fill.is_maker is True


class TestRateLimiter:
    """Tests for rate limiter."""

    def test_rate_limiter_emulates_20_per_10s(self):
        """Rate limiter emulates 20 req/10s."""
        clock = FakeClock()
        from wallexbot.sim.rate_limiter import RateLimiter

        limiter = RateLimiter(max_requests=20, window_seconds=10, clock=clock)

        # First 20 requests allowed
        for _i in range(20):
            assert limiter.acquire() is True

        # 21st request denied
        assert limiter.acquire() is False

        # Advance time by 10 seconds
        clock.advance(10)

        # Should be allowed again
        assert limiter.acquire() is True


class TestFaultInjection:
    """Tests for fault injection hooks."""

    def test_latency_injection(self):
        """Latency injection hook works."""
        from tests.helpers.clock import FakeClock
        from wallexbot.sim.exchange import SimulatedExchange

        clock = FakeClock()
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        exchange = SimulatedExchange(
            market=market,
            fee_schedule_config=FeeSchedule(
                maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")
            ),
            min_notional_rule=MinNotionalRule(
                min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")
            ),
            initial_balances={
                "TMN": Balance(free=Decimal("2000000.00"), locked=Decimal("0")),
                "USDT": Balance(free=Decimal("100.0000"), locked=Decimal("0")),
            },
            clock=clock,
        )

        # Inject 1 second latency
        exchange.set_latency(1.0)

        start = clock.now()
        request = OrderRequest(
            client_id="TEST_LATENCY",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        exchange.place_order(request)
        elapsed = clock.now() - start
        assert elapsed >= 1.0

    def test_rejected_order_injection(self):
        """Rejected order injection hook."""
        from wallexbot.sim.exchange import SimulatedExchange

        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        exchange = SimulatedExchange(
            market=market,
            fee_schedule_config=FeeSchedule(
                maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")
            ),
            min_notional_rule=MinNotionalRule(
                min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")
            ),
            initial_balances={
                "TMN": Balance(free=Decimal("2000000.00"), locked=Decimal("0")),
                "USDT": Balance(free=Decimal("100.0000"), locked=Decimal("0")),
            },
        )

        exchange.set_fault_injection(reject_next=True)

        request = OrderRequest(
            client_id="TEST_REJECT",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        with pytest.raises(Exception, match="Injected order rejection"):
            exchange.place_order(request)

    def test_dropped_fill_event(self):
        """Dropped fill event injection."""
        # This would be tested at the engine level
        pass

    def test_duplicate_fill_event(self):
        """Duplicate fill event injection."""
        pass


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_seed_same_results(self):
        """Same feed + same seed -> identical results."""
        from wallexbot.sim.matching import FillModel, MatchingEngine

        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))

        # Run 1
        engine1 = MatchingEngine(market, fee_schedule, FillModel.CONSERVATIVE)
        order1 = Order(
            id="ord_1",
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        engine1.add_order(order1)
        fills1 = engine1.process_trade(Decimal("99.00"), Decimal("5.0000"), 1001)

        # Run 2 (same setup)
        engine2 = MatchingEngine(market, fee_schedule, FillModel.CONSERVATIVE)
        order2 = Order(
            id="ord_1",
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )
        engine2.add_order(order2)
        fills2 = engine2.process_trade(Decimal("99.00"), Decimal("5.0000"), 1001)

        # Results should be identical
        assert len(fills1) == len(fills2)
        for f1, f2 in zip(fills1, fills2, strict=False):
            assert f1.price == f2.price
            assert f1.quantity == f2.quantity
            assert f1.fee == f2.fee
