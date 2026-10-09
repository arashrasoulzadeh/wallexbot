"""Property-based tests for grid strategy invariants."""

from decimal import Decimal
from hypothesis import given, strategies as st, assume, settings, HealthCheck
import pytest

from wallexbot.strategy.grid.parameters import (
    GridParameters,
    GridMode,
    Level,
    generate_levels,
    assign_sides,
)
from wallexbot.domain.market import Market, Symbol
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.money import quantize_down


# Hypothesis strategies
@st.composite
def market_strategy(draw):
    """Generate valid market configurations."""
    return Market(
        symbol=Symbol("USDTTMN"),
        base="USDT",
        quote="TMN",
        price_precision=draw(st.integers(min_value=0, max_value=8)),
        amount_precision=draw(st.integers(min_value=0, max_value=8)),
        is_spot=True,
    )


@st.composite
def grid_params_strategy(draw, market):
    """Generate valid grid parameters."""
    lower = draw(st.decimals(min_value=1, max_value=10000, places=market.price_precision))
    upper = draw(st.decimals(min_value=lower + Decimal("0.01"), max_value=20000, places=market.price_precision))
    count = draw(st.integers(min_value=2, max_value=50))
    mode = draw(st.sampled_from([GridMode.ARITHMETIC, GridMode.GEOMETRIC]))
    investment = draw(st.decimals(min_value=100, max_value=1000000, places=2))

    # For geometric mode, lower must be positive
    if mode == GridMode.GEOMETRIC and lower <= 0:
        lower = Decimal("1")

    return GridParameters(
        lower_price=lower,
        upper_price=upper,
        grid_count=count,
        mode=mode,
        total_investment=investment,
    )


class TestQuantizeProperties:
    """Property tests for quantize functions."""

    @given(
        st.decimals(min_value=-10000, max_value=10000, places=10),
        st.decimals(min_value=Decimal("0.00000001"), max_value=100, places=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_quantize_down_idempotent(self, value: Decimal, step: Decimal):
        """quantize_down is idempotent."""
        from wallexbot.domain.money import quantize_down
        assume(step > 0)
        result = quantize_down(value, step)
        assert quantize_down(result, step) == result

    @given(
        st.decimals(min_value=-10000, max_value=10000, places=10),
        st.decimals(min_value=Decimal("0.00000001"), max_value=100, places=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_quantize_down_never_increases_magnitude(self, value: Decimal, step: Decimal):
        """quantize_down never increases absolute value."""
        from wallexbot.domain.money import quantize_down
        assume(step > 0)
        result = quantize_down(value, step)
        assert abs(result) <= abs(value) + Decimal("1e-20")

    @given(
        st.decimals(min_value=-10000, max_value=10000, places=10),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_quantize_to_precision_idempotent(self, value: Decimal, digits: int):
        """quantize_to_precision is idempotent."""
        from wallexbot.domain.money import quantize_to_precision
        result = quantize_to_precision(value, digits)
        assert quantize_to_precision(result, digits) == result

    @given(
        st.decimals(min_value=-10000, max_value=10000, places=10),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_quantize_to_precision_never_increases_magnitude(self, value: Decimal, digits: int):
        """quantize_to_precision never increases absolute value."""
        from wallexbot.domain.money import quantize_to_precision
        result = quantize_to_precision(value, digits)
        assert abs(result) <= abs(value) + Decimal("1e-20")


class TestGridLevelProperties:
    """Property tests for grid level generation."""

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=20000, places=2),
        st.integers(min_value=2, max_value=20),
        st.sampled_from([GridMode.ARITHMETIC, GridMode.GEOMETRIC]),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
    def test_generate_levels_count(self, lower: Decimal, upper: Decimal, count: int, mode: GridMode, precision: int):
        """N levels generated for count=N."""
        assume(lower < upper)
        if mode == GridMode.GEOMETRIC:
            assume(lower > 0)

        try:
            levels = generate_levels(lower, upper, count, mode, precision)
            assert len(levels) == count
        except ValueError as e:
            # Rounding collapse is expected for some params
            assert "collapse" in str(e) or "increasing" in str(e)

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=20000, places=2),
        st.integers(min_value=2, max_value=20),
        st.sampled_from([GridMode.ARITHMETIC, GridMode.GEOMETRIC]),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
    def test_generate_levels_within_bounds(self, lower: Decimal, upper: Decimal, count: int, mode: GridMode, precision: int):
        """All levels within [lower, upper]."""
        assume(lower < upper)
        if mode == GridMode.GEOMETRIC:
            assume(lower > 0)

        try:
            levels = generate_levels(lower, upper, count, mode, precision)
            for level in levels:
                assert lower <= level.price <= upper + Decimal("1e-10")
        except ValueError:
            pass  # Collapse case

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=20000, places=2),
        st.integers(min_value=2, max_value=20),
        st.sampled_from([GridMode.ARITHMETIC, GridMode.GEOMETRIC]),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
    def test_generate_levels_strictly_increasing(self, lower: Decimal, upper: Decimal, count: int, mode: GridMode, precision: int):
        """Levels strictly increasing."""
        assume(lower < upper)
        if mode == GridMode.GEOMETRIC:
            assume(lower > 0)

        try:
            levels = generate_levels(lower, upper, count, mode, precision)
            for i in range(1, len(levels)):
                assert levels[i].price > levels[i - 1].price
        except ValueError:
            pass

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=20000, places=2),
        st.integers(min_value=2, max_value=20),
        st.sampled_from([GridMode.ARITHMETIC, GridMode.GEOMETRIC]),
        st.integers(min_value=0, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
    def test_generate_levels_no_duplicates(self, lower: Decimal, upper: Decimal, count: int, mode: GridMode, precision: int):
        """No duplicate prices after rounding."""
        assume(lower < upper)
        if mode == GridMode.GEOMETRIC:
            assume(lower > 0)

        try:
            levels = generate_levels(lower, upper, count, mode, precision)
            prices = [l.price for l in levels]
            assert len(prices) == len(set(prices))
        except ValueError:
            pass


class TestGridStateProperties:
    """Property tests for grid state invariants."""

    @given(
        st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=10),
                st.decimals(min_value=1, max_value=1000, places=2),
                st.sampled_from(["buy", "sell", ""]),
            ),
            min_size=2,
            max_size=20,
            unique_by=lambda x: x[0],  # unique indices
        )
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_grid_state_invariants(self, level_data):
        """Grid state invariants hold after operations."""
        # Filter to ensure exactly one gap
        buy_levels = [d for d in level_data if d[2] == "buy"]
        sell_levels = [d for d in level_data if d[2] == "sell"]
        gap_levels = [d for d in level_data if d[2] == ""]

        assume(len(gap_levels) == 1)
        assume(len(buy_levels) > 0)
        assume(len(sell_levels) > 0)

        # Sort by index
        level_data.sort(key=lambda x: x[0])

        levels = [Level(index=d[0], price=d[1], side=d[2]) for d in level_data]

        from wallexbot.strategy.grid.state import GridState, GridStateError

        state = GridState(levels=levels)

        # Test setting active orders
        for level in levels:
            if level.side in ("buy", "sell"):
                state.set_active_order(level.index, f"ord_{level.index}")
                assert state.is_level_active(level.index)

        # Test invariants
        state.validate_invariants()


class TestFillHandlingProperties:
    """Property tests for fill handling."""

    @given(
        st.integers(min_value=0, max_value=4),
        st.decimals(min_value=Decimal("0.0001"), max_value=100, places=4),
        st.decimals(min_value=Decimal("0"), max_value=10, places=4),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_fill_handling_no_negative_quantity(self, level_idx: int, fill_qty: Decimal, fill_fee: Decimal):
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

        from wallexbot.strategy.grid.fill_handling import handle_fill
        from wallexbot.strategy.grid.parameters import GridParameters, GridMode

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
            # Invalid parameters - skip
            pass


class TestProfitProperties:
    """Property tests for profit calculation."""

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=Decimal("0.0001"), max_value=1000, places=4),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_cycle_profit_sell_higher_than_buy(self, buy_price: Decimal, sell_price: Decimal, qty: Decimal):
        """Profit positive when sell > buy (ignoring fees)."""
        assume(sell_price > buy_price)

        from wallexbot.strategy.grid.profit import calculate_cycle_profit
        from wallexbot.domain.fees import FeeSchedule
        from wallexbot.domain.market import Side

        fee_schedule = FeeSchedule(maker_rate=Decimal("0"), taker_rate=Decimal("0"))
        profit = calculate_cycle_profit(buy_price, sell_price, qty, fee_schedule)
        assert profit > 0

    @given(
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=1, max_value=10000, places=2),
        st.decimals(min_value=Decimal("0.0001"), max_value=1000, places=4),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
    def test_cycle_profit_buy_higher_than_sell(self, buy_price: Decimal, sell_price: Decimal, qty: Decimal):
        """Profit negative when buy > sell (ignoring fees)."""
        assume(buy_price > sell_price)

        from wallexbot.strategy.grid.profit import calculate_cycle_profit
        from wallexbot.domain.fees import FeeSchedule
        from wallexbot.domain.market import Side

        fee_schedule = FeeSchedule(maker_rate=Decimal("0"), taker_rate=Decimal("0"))
        profit = calculate_cycle_profit(buy_price, sell_price, qty, fee_schedule)
        assert profit < 0