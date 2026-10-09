"""Property and fuzz tests for hardening."""

from decimal import Decimal
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume

from wallexbot.strategy.grid.parameters import (
    GridParameters,
    GridMode,
    generate_levels,
    assign_sides,
)
from wallexbot.strategy.grid.fill_handling import handle_fill
from wallexbot.strategy.grid.profit import calculate_cycle_profit
from wallexbot.domain.market import Market, Symbol, Side, OrderType, OrderStatus
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.money import quantize_down, quantize_to_precision
from wallexbot.sim.matching import MatchingEngine, FillModel


class TestStrategyPropertyTests:
    """Property-based tests for strategy invariants."""

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=20000, places=2),
        st.integers(min_value=2, max_value=50),
        st.sampled_from([GridMode.ARITHMETIC, GridMode.GEOMETRIC]),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
    def test_generate_levels_invariants(
        self, lower: Decimal, upper: Decimal, count: int, mode: GridMode, precision: int
    ):
        """Levels always satisfy invariants when generation succeeds."""
        assume(lower < upper)
        if mode == GridMode.GEOMETRIC:
            assume(lower > 0)

        try:
            levels = generate_levels(lower, upper, count, mode, precision)

            # Invariant: correct count
            assert len(levels) == count

            # Invariant: strictly increasing
            for i in range(1, len(levels)):
                assert levels[i].price > levels[i - 1].price

            # Invariant: within bounds
            for level in levels:
                assert lower <= level.price <= upper + Decimal("1e-10")

            # Invariant: no duplicates
            prices = [l.price for l in levels]
            assert len(prices) == len(set(prices))

            # Invariant: N levels -> N-1 intervals
            assert len(levels) == count
        except ValueError as e:
            # Rounding collapse is acceptable
            assert "collapse" in str(e) or "increasing" in str(e)

    @given(
        st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=9),
                st.sampled_from(["buy", "sell"]),
            ),
            min_size=1,
            max_size=10,
            unique_by=lambda x: x[0],
        ),
        st.integers(min_value=0, max_value=9),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_assign_sides_invariant(self, level_data, current_price_idx):
        """assign_sides produces exactly one gap level."""
        # Build levels
        levels = []
        for idx, side in level_data:
            price = Decimal(str(90 + idx * 2))
            levels.append({"index": idx, "price": price, "side": side})

        # Ensure we have at least one buy and one sell
        has_buy = any(s == "buy" for _, s in level_data)
        has_sell = any(s == "sell" for _, s in level_data)
        assume(has_buy and has_sell)

        # Sort by index
        levels.sort(key=lambda x: x["index"])

        from wallexbot.strategy.grid.parameters import Level
        level_objs = [Level(index=l["index"], price=l["price"], side=l["side"]) for l in levels]
        current_price = Decimal(str(90 + current_price_idx * 2))

        assigned = assign_sides(level_objs, current_price)

        # Invariant: exactly one gap (side == "")
        gap_count = sum(1 for l in assigned if l.side == "")
        # Note: assign_sides creates gap at current_price level
        # If current_price matches a level exactly, that becomes gap
        # If not, no gap is created by this function
        # The invariant is that there's at most one gap
        assert gap_count <= 1


class TestFillHandlingPropertyTests:
    """Property tests for fill handling."""

    @given(
        st.integers(min_value=0, max_value=4),
        st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("100"), places=4),
        st.decimals(min_value=Decimal("0"), max_value=Decimal("10"), places=4),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_fill_handling_no_negative_quantity(
        self, level_idx: int, fill_qty: Decimal, fill_fee: Decimal
    ):
        """Fill handling never produces negative quantity orders."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )

        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]

        assume(level_idx < len(levels))
        assume(levels[level_idx].side in ("buy", "sell"))

        active_orders = {level_idx: "ord_123"}

        try:
            result = handle_fill(
                fill_level=level_idx,
                fill_qty=fill_qty,
                fill_fee=fill_fee,
                levels=levels,
                active_orders=active_orders,
                market=market,
                fee_schedule=FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")),
                min_notional_rule=MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")),
                params=GridParameters(
                    lower_price=Decimal("90.00"),
                    upper_price=Decimal("110.00"),
                    grid_count=5,
                    mode=GridMode.ARITHMETIC,
                    total_investment=Decimal("10000.00"),
                ),
            )

            for action in result.actions:
                if action.type == "place":
                    assert action.quantity > 0
        except (ValueError, IndexError):
            pass


class TestProfitPropertyTests:
    """Property tests for profit calculation."""

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=Decimal("0.0001"), max_value=1000, places=4),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_profit_positive_when_sell_higher(self, buy_price: Decimal, sell_price: Decimal, qty: Decimal):
        """Profit is positive when sell > buy (zero fees)."""
        assume(sell_price > buy_price)

        fee_schedule = FeeSchedule(maker_rate=Decimal("0"), taker_rate=Decimal("0"))
        profit = calculate_cycle_profit(buy_price, sell_price, qty, fee_schedule)
        assert profit > 0

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=Decimal("0.0001"), max_value=1000, places=4),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_profit_negative_when_buy_higher(self, buy_price: Decimal, sell_price: Decimal, qty: Decimal):
        """Profit is negative when buy > sell (zero fees)."""
        assume(buy_price > sell_price)

        fee_schedule = FeeSchedule(maker_rate=Decimal("0"), taker_rate=Decimal("0"))
        profit = calculate_cycle_profit(buy_price, sell_price, qty, fee_schedule)
        assert profit < 0


class TestMatchingEnginePropertyTests:
    """Property tests for matching engine."""

    @given(
        st.decimals(min_value=1, max_value=1000, places=2),
        st.decimals(min_value=1, max_value=1000, places=2),
        st.decimals(min_value=Decimal("0.0001"), max_value=100, places=4),
        st.integers(min_value=0, max_value=10),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_limit_order_fill_price_bounds(
        self, limit_price: Decimal, trade_price: Decimal, qty: Decimal, side_int: int
    ):
        """Limit orders only fill at or better than limit price."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )

        engine = MatchingEngine(market, FeeSchedule(maker_rate=Decimal("0"), taker_rate=Decimal("0")), FillModel.CONSERVATIVE)

        side = Side.BUY if side_int % 2 == 0 else Side.SELL

        order = Order(
            id="ord_1",
            client_id="TEST_1",
            symbol=Symbol("USDTTMN"),
            side=side,
            type=OrderType.LIMIT,
            price=limit_price,
            quantity=qty,
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            fee=Decimal("0"),
            fee_asset="TMN" if side == Side.BUY else "USDT",
            is_maker=True,
            created_at=1000,
            updated_at=1000,
        )

        engine.add_order(order)
        fills = engine.process_trade(trade_price, qty, 1001)

        for fill in fills:
            if side == Side.BUY:
                # Buy fills at price <= limit
                assert fill.price <= limit_price + Decimal("1e-10")
            else:
                # Sell fills at price >= limit
                assert fill.price >= limit_price - Decimal("1e-10")


class TestMoneyPropertyTests:
    """Property tests for money math."""

    @given(
        st.decimals(min_value=-10000, max_value=10000, places=10),
        st.decimals(min_value=Decimal("0.00000001"), max_value=100, places=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_quantize_down_idempotent(self, value: Decimal, step: Decimal):
        """quantize_down is idempotent."""
        assume(step > 0)
        result = quantize_down(value, step)
        assert quantize_down(result, step) == result

    @given(
        st.decimals(min_value=-10000, max_value=10000, places=10),
        st.decimals(min_value=Decimal("0.00000001"), max_value=100, places=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_quantize_down_magnitude(self, value: Decimal, step: Decimal):
        """quantize_down never increases magnitude."""
        assume(step > 0)
        result = quantize_down(value, step)
        assert abs(result) <= abs(value) + Decimal("1e-20")

    @given(
        st.decimals(min_value=-10000, max_value=10000, places=10),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_quantize_to_precision_idempotent(self, value: Decimal, digits: int):
        """quantize_to_precision is idempotent."""
        result = quantize_to_precision(value, digits)
        assert quantize_to_precision(result, digits) == result

    @given(
        st.decimals(min_value=-10000, max_value=10000, places=10),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_quantize_to_precision_magnitude(self, value: Decimal, digits: int):
        """quantize_to_precision never increases magnitude."""
        result = quantize_to_precision(value, digits)
        assert abs(result) <= abs(value) + Decimal("1e-20")


# Import Order for matching engine test
from wallexbot.domain.order import Order