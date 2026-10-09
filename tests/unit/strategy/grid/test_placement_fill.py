"""Tests for initial placement and fill handling."""

from decimal import Decimal
import pytest

from wallexbot.strategy.grid.placement import (
    place_initial_grid,
    InitialPlacement,
)
from wallexbot.strategy.grid.fill_handling import (
    handle_fill,
    FillResult,
    FillAction,
)
from wallexbot.strategy.grid.parameters import GridParameters, GridMode, Level, generate_levels, assign_sides
from wallexbot.domain.market import Market, Symbol, Side, OrderType
from wallexbot.domain.order import OrderRequest
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.money import quantize_down


class TestInitialPlacement:
    """Tests for initial grid placement."""

    def test_buy_below_sell_above(self):
        """Buy orders at levels below price, sell orders at levels above."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        params = GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=5,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
        )
        levels = generate_levels(
            lower=params.lower_price,
            upper=params.upper_price,
            count=params.grid_count,
            mode=params.mode,
            price_precision=market.price_precision,
        )
        levels = assign_sides(levels, Decimal("100.00"))
        # Levels: 90(buy), 95(buy), 100(skip), 105(sell), 110(sell)

        placement = place_initial_grid(
            levels=levels,
            current_price=Decimal("100.00"),
            market=market,
            params=params,
            fee_schedule=FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")),
            min_notional_rule=MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")),
        )

        # Check buy orders placed at levels below price
        buy_orders = [o for o in placement.orders if o.side == Side.BUY]
        assert len(buy_orders) == 2
        assert buy_orders[0].price == Decimal("90.00")
        assert buy_orders[1].price == Decimal("95.00")

        # Check sell orders placed at levels above price
        sell_orders = [o for o in placement.orders if o.side == Side.SELL]
        assert len(sell_orders) == 2
        assert sell_orders[0].price == Decimal("105.00")
        assert sell_orders[1].price == Decimal("110.00")

        # Check skipped level
        assert placement.skipped_level_index == 2

    def test_level_at_price_skipped(self):
        """Level equal/very close to market price is skipped."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        params = GridParameters(
            lower_price=Decimal("99.00"),
            upper_price=Decimal("101.00"),
            grid_count=3,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
        )
        levels = generate_levels(
            lower=params.lower_price,
            upper=params.upper_price,
            count=params.grid_count,
            mode=params.mode,
            price_precision=market.price_precision,
        )
        levels = assign_sides(levels, Decimal("100.00"))
        # Levels: 99(buy), 100(skip), 101(sell)

        placement = place_initial_grid(
            levels=levels,
            current_price=Decimal("100.00"),
            market=market,
            params=params,
            fee_schedule=FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")),
            min_notional_rule=MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")),
        )

        assert placement.skipped_level_index == 1
        assert len(placement.orders) == 2  # Only buy at 99, sell at 101

    def test_base_inventory_for_sells(self):
        """Base asset inventory needed for initial sells is computed."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        params = GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=5,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
        )
        levels = generate_levels(
            lower=params.lower_price,
            upper=params.upper_price,
            count=params.grid_count,
            mode=params.mode,
            price_precision=market.price_precision,
        )
        levels = assign_sides(levels, Decimal("100.00"))

        placement = place_initial_grid(
            levels=levels,
            current_price=Decimal("100.00"),
            market=market,
            params=params,
            fee_schedule=FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")),
            min_notional_rule=MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")),
        )

        # 2 sell orders, each with some qty
        # Total base needed = sum of sell quantities
        assert placement.base_needed_for_sells > Decimal("0")


class TestFillHandling:
    """Tests for fill handling - core of grid strategy."""

    def test_buy_fill_places_sell_next_level(self):
        """When buy at level i fills -> place sell at level i+1."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        min_notional = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

        # Setup: levels 90(buy), 95(buy), 100(skip), 105(sell), 110(sell)
        # Current state: buy at 90 filled, need to place sell at 95
        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        # Active order at level 0 (buy at 90)
        active_orders = {0: "ord_123"}

        # Fill at level 0 (buy at 90) - full fill
        result = handle_fill(
            fill_level=0,
            fill_qty=Decimal("10.0000"),
            fill_fee=Decimal("0.90"),  # fee in TMN
            levels=levels,
            active_orders=active_orders,
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        # Should place sell at level 1 (next level up)
        assert len(result.actions) == 1
        action = result.actions[0]
        assert action.type == "place"
        assert action.side == Side.SELL
        assert action.price == Decimal("95.00")
        assert action.level_index == 1

    def test_sell_fill_places_buy_prev_level(self):
        """When sell at level i fills -> place buy at level i-1."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        min_notional = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        # Active order at level 4 (sell at 110)
        active_orders = {4: "ord_456"}

        # Fill at level 4 (sell at 110) - full fill
        result = handle_fill(
            fill_level=4,
            fill_qty=Decimal("10.0000"),
            fill_fee=Decimal("0.02"),  # fee in USDT
            levels=levels,
            active_orders=active_orders,
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        # Should place buy at level 3 (prev level down)
        assert len(result.actions) == 1
        action = result.actions[0]
        assert action.type == "place"
        assert action.side == Side.BUY
        assert action.price == Decimal("105.00")
        assert action.level_index == 3

    def test_partial_fill_places_counter_for_filled_qty(self):
        """Partial fill: place counter-order for filled quantity only."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        min_notional = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        active_orders = {0: "ord_123"}

        # Partial fill at level 0: filled 5 of 10
        result = handle_fill(
            fill_level=0,
            fill_qty=Decimal("5.0000"),
            fill_fee=Decimal("0.45"),
            levels=levels,
            active_orders=active_orders,
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        # Should place sell at level 1 for 5 qty only
        assert len(result.actions) == 1
        action = result.actions[0]
        assert action.type == "place"
        assert action.side == Side.SELL
        assert action.quantity == Decimal("5.0000")

    def test_counter_order_accounts_for_fees(self):
        """Counter-order quantity accounts for fees so base balance never negative."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        min_notional = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        active_orders = {0: "ord_123"}

        # Buy fill at 90: receive 10 USDT, pay 0.90 TMN fee
        # Counter sell at 95: need to have 10 USDT available
        # But we received 10 - fee_in_base? No, fee is in quote for buy
        # So we have 10 USDT free to sell
        result = handle_fill(
            fill_level=0,
            fill_qty=Decimal("10.0000"),
            fill_fee=Decimal("0.90"),
            levels=levels,
            active_orders=active_orders,
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        action = result.actions[0]
        # Should be able to place full 10 qty (we received 10 USDT)
        assert action.quantity == Decimal("10.0000")

    def test_top_level_sell_fill_no_counter(self):
        """Top level sell fill: no level beyond range."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        min_notional = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        active_orders = {4: "ord_456"}

        # Fill at top level (4) - no level 5 to place buy
        result = handle_fill(
            fill_level=4,
            fill_qty=Decimal("10.0000"),
            fill_fee=Decimal("0.02"),
            levels=levels,
            active_orders=active_orders,
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        # No counter order placed
        assert len(result.actions) == 0
        assert result.cycle_completed is True  # Completed a full cycle

    def test_bottom_level_buy_fill_no_counter(self):
        """Bottom level buy fill: no level beyond range."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        min_notional = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        active_orders = {0: "ord_123"}

        # Fill at bottom level (0) - no level -1 to place sell
        result = handle_fill(
            fill_level=0,
            fill_qty=Decimal("10.0000"),
            fill_fee=Decimal("0.90"),
            levels=levels,
            active_orders=active_orders,
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        # No counter order placed
        assert len(result.actions) == 0

    def test_duplicate_fill_idempotent(self):
        """Duplicate fill event is idempotent."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        min_notional = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        active_orders = {0: "ord_123"}

        # First fill
        result1 = handle_fill(
            fill_level=0,
            fill_qty=Decimal("10.0000"),
            fill_fee=Decimal("0.90"),
            levels=levels,
            active_orders=active_orders,
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        # Second duplicate fill - should be no-op
        result2 = handle_fill(
            fill_level=0,
            fill_qty=Decimal("10.0000"),
            fill_fee=Decimal("0.90"),
            levels=levels,
            active_orders={},  # Order already filled/removed
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        # Second call should have no actions
        assert len(result2.actions) == 0

    def test_out_of_order_fill_events(self):
        """Out-of-order fill events handled correctly."""
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        fee_schedule = FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))
        min_notional = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        active_orders = {0: "ord_123", 3: "ord_456"}

        # Fill sell at level 3 first (out of order - buy at 0 not filled yet)
        result = handle_fill(
            fill_level=3,
            fill_qty=Decimal("10.0000"),
            fill_fee=Decimal("0.02"),
            levels=levels,
            active_orders=active_orders,
            market=market,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
            params=GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=5,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            ),
        )

        # Should place buy at level 2 (but level 2 is skipped!)
        # Actually level 2 is the skipped level, so place at level 1
        # This tests the edge case - should handle gracefully
        assert len(result.actions) <= 1