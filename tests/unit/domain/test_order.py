"""Tests for Order, Fill, Trade, Balance, OrderRequest, FeeSchedule models."""

from decimal import Decimal
import pytest

from wallexbot.domain.order import Order, OrderRequest, Fill, Trade
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Symbol, Side, OrderType, OrderStatus
from wallexbot.domain.money import quantize_down


class TestOrder:
    """Tests for Order dataclass."""

    def test_order_creation(self):
        order = Order(
            id="ord_123",
            client_id="GRID_1_0_1",
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
            created_at=1234567890,
            updated_at=1234567890,
        )
        assert order.id == "ord_123"
        assert order.client_id == "GRID_1_0_1"
        assert order.symbol == Symbol("USDTTMN")
        assert order.side == Side.BUY
        assert order.type == OrderType.LIMIT
        assert order.price == Decimal("100.00")
        assert order.quantity == Decimal("10.0000")
        assert order.status == OrderStatus.NEW

    def test_order_client_id_validation(self):
        # Valid client_id
        Order(
            id="ord_123",
            client_id="GRID_1_0_1",
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
            created_at=1234567890,
            updated_at=1234567890,
        )

        # Invalid client_id (contains special chars)
        with pytest.raises(ValueError, match="client_id"):
            Order(
                id="ord_123",
                client_id="GRID_1_0_1!",  # invalid char
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
                created_at=1234567890,
                updated_at=1234567890,
            )

        # Empty client_id
        with pytest.raises(ValueError, match="client_id"):
            Order(
                id="ord_123",
                client_id="",
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
                created_at=1234567890,
                updated_at=1234567890,
            )

    def test_order_remaining_quantity(self):
        order = Order(
            id="ord_123",
            client_id="GRID_1_0_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=Decimal("3.0000"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1234567890,
            updated_at=1234567890,
        )
        assert order.remaining_quantity == Decimal("7.0000")

    def test_order_filled_percent(self):
        order = Order(
            id="ord_123",
            client_id="GRID_1_0_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=Decimal("3.0000"),
            fee=Decimal("0"),
            fee_asset="TMN",
            is_maker=True,
            created_at=1234567890,
            updated_at=1234567890,
        )
        assert order.filled_percent == Decimal("0.3")

    def test_order_is_active(self):
        # Active orders
        for status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]:
            order = Order(
                id="ord_123",
                client_id="GRID_1_0_1",
                symbol=Symbol("USDTTMN"),
                side=Side.BUY,
                type=OrderType.LIMIT,
                price=Decimal("100.00"),
                quantity=Decimal("10.0000"),
                status=status,
                filled_quantity=Decimal("0"),
                fee=Decimal("0"),
                fee_asset="TMN",
                is_maker=True,
                created_at=1234567890,
                updated_at=1234567890,
            )
            assert order.is_active is True

        # Inactive orders
        for status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.UNKNOWN]:
            order = Order(
                id="ord_123",
                client_id="GRID_1_0_1",
                symbol=Symbol("USDTTMN"),
                side=Side.BUY,
                type=OrderType.LIMIT,
                price=Decimal("100.00"),
                quantity=Decimal("10.0000"),
                status=status,
                filled_quantity=Decimal("10.0000") if status == OrderStatus.FILLED else Decimal("0"),
                fee=Decimal("0"),
                fee_asset="TMN",
                is_maker=True,
                created_at=1234567890,
                updated_at=1234567890,
            )
            assert order.is_active is False

    def test_order_immutable_transition(self):
        order = Order(
            id="ord_123",
            client_id="GRID_1_0_1",
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
            created_at=1234567890,
            updated_at=1234567890,
        )

        # Transition to partially filled
        updated = order.with_filled(Decimal("3.0000"), Decimal("0.3"), 1234567891)
        assert updated.filled_quantity == Decimal("3.0000")
        assert updated.fee == Decimal("0.3")
        assert updated.status == OrderStatus.PARTIALLY_FILLED
        assert updated.updated_at == 1234567891
        # Original unchanged
        assert order.filled_quantity == Decimal("0")
        assert order.status == OrderStatus.NEW

        # Transition to filled
        filled = updated.with_filled(Decimal("7.0000"), Decimal("0.7"), 1234567892)
        assert filled.filled_quantity == Decimal("10.0000")
        assert filled.fee == Decimal("1.0")
        assert filled.status == OrderStatus.FILLED
        assert filled.updated_at == 1234567892

        # Transition to canceled
        canceled = order.with_canceled(1234567893)
        assert canceled.status == OrderStatus.CANCELED
        assert canceled.updated_at == 1234567893


class TestFill:
    """Tests for Fill model."""

    def test_fill_creation(self):
        fill = Fill(
            order_id="ord_123",
            trade_id="trd_456",
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            fee=Decimal("0.1"),
            fee_asset="TMN",
            is_maker=True,
            timestamp=1234567890,
        )
        assert fill.order_id == "ord_123"
        assert fill.price == Decimal("100.00")
        assert fill.quantity == Decimal("10.0000")
        assert fill.fee == Decimal("0.1")
        assert fill.fee_asset == "TMN"
        assert fill.is_maker is True

    def test_fill_quote_value(self):
        fill = Fill(
            order_id="ord_123",
            trade_id="trd_456",
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            fee=Decimal("0.1"),
            fee_asset="TMN",
            is_maker=True,
            timestamp=1234567890,
        )
        assert fill.quote_value == Decimal("1000.00")


class TestTrade:
    """Tests for public Trade model."""

    def test_trade_creation(self):
        trade = Trade(
            symbol=Symbol("USDTTMN"),
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            side=Side.BUY,
            timestamp=1234567890,
            trade_id="trd_456",
        )
        assert trade.symbol == Symbol("USDTTMN")
        assert trade.price == Decimal("100.00")
        assert trade.side == Side.BUY


class TestBalance:
    """Tests for Balance model."""

    def test_balance_creation(self):
        balance = Balance(free=Decimal("1000.00"), locked=Decimal("500.00"))
        assert balance.free == Decimal("1000.00")
        assert balance.locked == Decimal("500.00")
        assert balance.total == Decimal("1500.00")

    def test_balance_never_negative(self):
        with pytest.raises(ValueError, match="negative"):
            Balance(free=Decimal("-100"), locked=Decimal("0"))

        with pytest.raises(ValueError, match="negative"):
            Balance(free=Decimal("100"), locked=Decimal("-50"))

    def test_balance_lock_unlock(self):
        balance = Balance(free=Decimal("1000.00"), locked=Decimal("0"))

        # Lock funds
        locked = balance.lock(Decimal("300.00"))
        assert locked.free == Decimal("700.00")
        assert locked.locked == Decimal("300.00")

        # Unlock funds
        unlocked = locked.unlock(Decimal("100.00"))
        assert unlocked.free == Decimal("800.00")
        assert unlocked.locked == Decimal("200.00")

    def test_balance_lock_insufficient(self):
        balance = Balance(free=Decimal("100.00"), locked=Decimal("0"))
        with pytest.raises(ValueError, match="insufficient"):
            balance.lock(Decimal("200.00"))


class TestOrderRequest:
    """Tests for OrderRequest (what strategy wants)."""

    def test_order_request_creation(self):
        req = OrderRequest(
            client_id="GRID_1_0_1",
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
        )
        assert req.client_id == "GRID_1_0_1"
        assert req.side == Side.BUY
        assert req.type == OrderType.LIMIT


class TestFeeSchedule:
    """Tests for FeeSchedule."""

    def test_fee_schedule_creation(self):
        fees = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        assert fees.maker_rate == Decimal("0.001")
        assert fees.taker_rate == Decimal("0.002")

    def test_fee_calc_quote_asset(self):
        fees = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        # BUY order: fee in quote asset (TMN)
        fee = fees.calculate_fee(Decimal("100.00"), Decimal("10.0000"), Side.BUY, is_maker=True)
        assert fee == Decimal("1.0")  # 100 * 10 * 0.001 = 1 TMN

        fee = fees.calculate_fee(Decimal("100.00"), Decimal("10.0000"), Side.BUY, is_maker=False)
        assert fee == Decimal("2.0")  # 100 * 10 * 0.002 = 2 TMN

    def test_fee_calc_base_asset(self):
        fees = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        # SELL order: fee in base asset (USDT)
        fee = fees.calculate_fee(Decimal("100.00"), Decimal("10.0000"), Side.SELL, is_maker=True)
        assert fee == Decimal("0.01")  # 10 * 0.001 = 0.01 USDT

        fee = fees.calculate_fee(Decimal("100.00"), Decimal("10.0000"), Side.SELL, is_maker=False)
        assert fee == Decimal("0.02")  # 10 * 0.002 = 0.02 USDT


class TestMinNotionalRule:
    """Tests for MinNotionalRule."""

    def test_min_notional_check(self):
        rule = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))
        assert rule.check(Decimal("100.00"), Decimal("0.1")) is True  # 10 notional
        assert rule.check(Decimal("100.00"), Decimal("0.05")) is False  # 5 notional < 10
        assert rule.check(Decimal("1000.00"), Decimal("0.00005")) is False  # qty < min

    def test_min_notional_error_message(self):
        rule = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))
        ok, msg = rule.validate(Decimal("100.00"), Decimal("0.05"))
        assert ok is False
        assert "notional" in msg.lower()

        ok, msg = rule.validate(Decimal("1000.00"), Decimal("0.00005"))
        assert ok is False
        assert "quantity" in msg.lower() or "qty" in msg.lower()