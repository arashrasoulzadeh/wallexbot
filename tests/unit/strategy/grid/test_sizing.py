"""Tests for order sizing and initial placement."""

from decimal import Decimal
import pytest

from wallexbot.strategy.grid.sizing import (
    calculate_equal_quote_qty,
    calculate_equal_base_qty,
    validate_order_sizes,
    compute_initial_inventory,
)
from wallexbot.strategy.grid.parameters import GridParameters, GridMode, Level, assign_sides, generate_levels
from wallexbot.domain.market import Market, Symbol
from wallexbot.domain.fees import MinNotionalRule


class TestEqualQuoteSizing:
    """Tests for equal-quote-per-grid sizing."""

    def test_equal_quote_per_grid(self):
        # 10,000 TMN total, 10 grids -> 1,000 TMN per grid
        # At price 100, qty = 1000/100 = 10 USDT
        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side="buy"),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        qtys = calculate_equal_quote_qty(
            levels=levels,
            total_quote=Decimal("10000.00"),
            market=market,
        )
        # Buy levels (below 100): 90, 95 -> 2 levels
        # Sell levels (above 100): 105, 110 -> 2 levels
        # Level at 100 skipped
        # 4 active levels, 10000/4 = 2500 per level
        # Buy at 90: 2500/90 = 27.777... -> 27.7777 (rounded down to 4 decimals)
        # Buy at 95: 2500/95 = 26.315... -> 26.3157
        # Sell at 105: 2500/105 = 23.809... -> 23.8095
        # Sell at 110: 2500/110 = 22.727... -> 22.7272
        assert qtys[0] == Decimal("27.7777")  # 2500/90
        assert qtys[1] == Decimal("26.3157")  # 2500/95
        assert qtys[3] == Decimal("23.8095")  # 2500/105
        assert qtys[4] == Decimal("22.7272")  # 2500/110

    def test_equal_quote_qty_rounded_down(self):
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        levels = [Level(index=0, price=Decimal("100.00"), side="buy")]
        qtys = calculate_equal_quote_qty(
            levels=levels,
            total_quote=Decimal("1000.00"),
            market=market,
        )
        # 1000/100 = 10.0000 exactly
        assert qtys[0] == Decimal("10.0000")


class TestEqualBaseSizing:
    """Tests for equal-base-qty-per-grid sizing."""

    def test_equal_base_qty_per_grid(self):
        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        qtys = calculate_equal_base_qty(
            levels=levels,
            per_grid_qty=Decimal("10.0000"),
            market=market,
        )
        # All active levels get 10.0000
        assert qtys[0] == Decimal("10.0000")
        assert qtys[1] == Decimal("10.0000")
        assert qtys[3] == Decimal("10.0000")
        assert qtys[4] == Decimal("10.0000")
        # Skipped level gets 0
        assert qtys[2] == Decimal("0")


class TestValidateOrderSizes:
    """Tests for min-notional/min-qty validation."""

    def test_validate_passes(self):
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        rule = MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))
        levels = [
            Level(index=0, price=Decimal("100.00"), side="buy"),
            Level(index=1, price=Decimal("105.00"), side="sell"),
        ]
        qtys = [Decimal("1.0000"), Decimal("1.0000")]
        ok, errors = validate_order_sizes(levels, qtys, market, rule)
        assert ok is True
        assert errors == []

    def test_validate_fails_min_notional(self):
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        rule = MinNotionalRule(min_notional=Decimal("100.00"), min_quantity=Decimal("0.0001"))
        levels = [
            Level(index=0, price=Decimal("100.00"), side="buy"),
            Level(index=1, price=Decimal("105.00"), side="sell"),
        ]
        qtys = [Decimal("0.5000"), Decimal("0.5000")]  # 50 notional each < 100
        ok, errors = validate_order_sizes(levels, qtys, market, rule)
        assert ok is False
        assert len(errors) == 2
        assert all("notional" in e.lower() for e in errors)

    def test_validate_fails_min_qty(self):
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        rule = MinNotionalRule(min_notional=Decimal("1.00"), min_quantity=Decimal("1.0000"))
        levels = [
            Level(index=0, price=Decimal("100.00"), side="buy"),
        ]
        qtys = [Decimal("0.5000")]  # Below min qty
        ok, errors = validate_order_sizes(levels, qtys, market, rule)
        assert ok is False
        assert len(errors) == 1
        assert "quantity" in errors[0].lower() or "qty" in errors[0].lower()


class TestComputeInitialInventory:
    """Tests for initial inventory calculation."""

    def test_compute_initial_inventory_sell_levels(self):
        # Need base asset for sell orders
        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side="sell"),
            Level(index=4, price=Decimal("110.00"), side="sell"),
        ]
        qtys = [Decimal("10.0000"), Decimal("10.0000"), Decimal("0"), Decimal("10.0000"), Decimal("10.0000")]
        # 2 sell levels * 10 USDT each = 20 USDT needed
        needed = compute_initial_inventory(levels, qtys, Side.SELL)
        assert needed == Decimal("20.0000")

    def test_compute_initial_inventory_buy_levels(self):
        # Need quote asset for buy orders
        levels = [
            Level(index=0, price=Decimal("90.00"), side="buy"),
            Level(index=1, price=Decimal("95.00"), side="buy"),
        ]
        qtys = [Decimal("10.0000"), Decimal("10.0000")]
        # Buy orders lock quote, not base
        needed = compute_initial_inventory(levels, qtys, Side.BUY)
        assert needed == Decimal("0")  # No base needed for buys