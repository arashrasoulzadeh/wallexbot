"""Tests for grid strategy parameters and level generation."""

from decimal import Decimal
import pytest
from hypothesis import given, strategies as st, assume

from wallexbot.strategy.grid.parameters import GridParameters, GridMode
from wallexbot.strategy.grid.levels import generate_levels, Level
from wallexbot.domain.market import Market, Symbol


class TestGridParameters:
    """Tests for GridParameters model."""

    def test_grid_parameters_creation(self):
        params = GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=10,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
        )
        assert params.lower_price == Decimal("90.00")
        assert params.upper_price == Decimal("110.00")
        assert params.grid_count == 10
        assert params.mode == GridMode.ARITHMETIC
        assert params.total_investment == Decimal("10000.00")
        assert params.per_grid_qty is None
        assert params.stop_loss_price is None
        assert params.take_profit_price is None

    def test_grid_parameters_with_optional(self):
        params = GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=10,
            mode=GridMode.GEOMETRIC,
            total_investment=Decimal("10000.00"),
            per_grid_qty=Decimal("1.0000"),
            stop_loss_price=Decimal("85.00"),
            take_profit_price=Decimal("115.00"),
        )
        assert params.per_grid_qty == Decimal("1.0000")
        assert params.stop_loss_price == Decimal("85.00")
        assert params.take_profit_price == Decimal("115.00")

    def test_grid_parameters_lower_ge_upper_raises(self):
        with pytest.raises(ValueError, match="lower.*upper"):
            GridParameters(
                lower_price=Decimal("110.00"),
                upper_price=Decimal("90.00"),
                grid_count=10,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            )

    def test_grid_parameters_count_too_small(self):
        with pytest.raises(ValueError, match="grid_count"):
            GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=1,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("10000.00"),
            )

    def test_grid_parameters_investment_non_positive(self):
        with pytest.raises(ValueError, match="investment"):
            GridParameters(
                lower_price=Decimal("90.00"),
                upper_price=Decimal("110.00"),
                grid_count=10,
                mode=GridMode.ARITHMETIC,
                total_investment=Decimal("0"),
            )

    def test_grid_parameters_stop_loss_outside_range(self):
        # Stop loss below lower - valid
        params = GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=10,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
            stop_loss_price=Decimal("85.00"),
        )
        assert params.stop_loss_price == Decimal("85.00")

        # Stop loss above lower but below upper - should this be allowed?
        # For now, allow it but it's unusual
        params2 = GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=10,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
            stop_loss_price=Decimal("95.00"),
        )
        assert params2.stop_loss_price == Decimal("95.00")


class TestGridMode:
    """Tests for GridMode enum."""

    def test_modes(self):
        assert GridMode.ARITHMETIC.value == "arithmetic"
        assert GridMode.GEOMETRIC.value == "geometric"


class TestGenerateLevelsArithmetic:
    """Tests for arithmetic level generation."""

    def test_arithmetic_equal_spacing(self):
        levels = generate_levels(
            lower=Decimal("90.00"),
            upper=Decimal("110.00"),
            count=5,
            mode=GridMode.ARITHMETIC,
            price_precision=2,
        )
        # 5 levels: 90, 95, 100, 105, 110
        assert len(levels) == 5
        assert levels[0].price == Decimal("90.00")
        assert levels[1].price == Decimal("95.00")
        assert levels[2].price == Decimal("100.00")
        assert levels[3].price == Decimal("105.00")
        assert levels[4].price == Decimal("110.00")

    def test_arithmetic_endpoints_included(self):
        levels = generate_levels(
            lower=Decimal("90.00"),
            upper=Decimal("110.00"),
            count=3,
            mode=GridMode.ARITHMETIC,
            price_precision=2,
        )
        assert levels[0].price == Decimal("90.00")
        assert levels[-1].price == Decimal("110.00")

    def test_arithmetic_count_correct(self):
        for count in [2, 3, 5, 10, 20]:
            levels = generate_levels(
                lower=Decimal("90.00"),
                upper=Decimal("110.00"),
                count=count,
                mode=GridMode.ARITHMETIC,
                price_precision=2,
            )
            assert len(levels) == count

    def test_arithmetic_rounded_to_precision(self):
        levels = generate_levels(
            lower=Decimal("90.00"),
            upper=Decimal("110.00"),
            count=7,
            mode=GridMode.ARITHMETIC,
            price_precision=1,  # 1 decimal place
        )
        # Step = 20/6 = 3.333... -> rounded to 3.3
        # 90.0, 93.3, 96.7, 100.0, 103.3, 106.7, 110.0
        for level in levels:
            # Check price has at most 1 decimal place
            assert level.price.as_tuple().exponent >= -1

    def test_arithmetic_strictly_increasing(self):
        levels = generate_levels(
            lower=Decimal("90.00"),
            upper=Decimal("110.00"),
            count=10,
            mode=GridMode.ARITHMETIC,
            price_precision=2,
        )
        for i in range(1, len(levels)):
            assert levels[i].price > levels[i - 1].price

    def test_arithmetic_no_duplicates_after_rounding(self):
        # This should work fine with reasonable parameters
        levels = generate_levels(
            lower=Decimal("100.00"),
            upper=Decimal("100.10"),
            count=5,
            mode=GridMode.ARITHMETIC,
            price_precision=2,
        )
        # 100.00, 100.02, 100.05, 100.07, 100.10 - all distinct
        prices = [l.price for l in levels]
        assert len(prices) == len(set(prices))

    def test_arithmetic_rounding_collapse_raises(self):
        # Very tight range with many levels and low precision -> collapse
        with pytest.raises(ValueError, match="rounding collapse"):
            generate_levels(
                lower=Decimal("100.00"),
                upper=Decimal("100.01"),
                count=10,
                mode=GridMode.ARITHMETIC,
                price_precision=2,
            )

    def test_arithmetic_property_intervals(self):
        levels = generate_levels(
            lower=Decimal("90.00"),
            upper=Decimal("110.00"),
            count=10,
            mode=GridMode.ARITHMETIC,
            price_precision=2,
        )
        # N levels -> N-1 intervals
        assert len(levels) == 10
        # All within [lower, upper]
        for level in levels:
            assert Decimal("90.00") <= level.price <= Decimal("110.00")


class TestGenerateLevelsGeometric:
    """Tests for geometric level generation."""

    def test_geometric_equal_ratio(self):
        levels = generate_levels(
            lower=Decimal("100.00"),
            upper=Decimal("200.00"),
            count=5,
            mode=GridMode.GEOMETRIC,
            price_precision=2,
        )
        assert len(levels) == 5
        assert levels[0].price == Decimal("100.00")
        assert levels[-1].price == Decimal("200.00")

        # Check ratio is roughly constant
        ratios = []
        for i in range(1, len(levels)):
            ratio = levels[i].price / levels[i - 1].price
            ratios.append(ratio)
        # All ratios should be approximately equal
        for r in ratios[1:]:
            assert abs(r - ratios[0]) < Decimal("0.01")

    def test_geometric_rounded_to_precision(self):
        levels = generate_levels(
            lower=Decimal("100.00"),
            upper=Decimal("200.00"),
            count=5,
            mode=GridMode.GEOMETRIC,
            price_precision=1,
        )
        for level in levels:
            assert level.price.as_tuple().exponent >= -1

    def test_geometric_strictly_increasing(self):
        levels = generate_levels(
            lower=Decimal("100.00"),
            upper=Decimal("200.00"),
            count=10,
            mode=GridMode.GEOMETRIC,
            price_precision=2,
        )
        for i in range(1, len(levels)):
            assert levels[i].price > levels[i - 1].price

    def test_geometric_no_duplicates_after_rounding(self):
        levels = generate_levels(
            lower=Decimal("100.00"),
            upper=Decimal("101.00"),
            count=5,
            mode=GridMode.GEOMETRIC,
            price_precision=2,
        )
        prices = [l.price for l in levels]
        assert len(prices) == len(set(prices))

    def test_geometric_rounding_collapse_raises(self):
        with pytest.raises(ValueError, match="rounding collapse"):
            generate_levels(
                lower=Decimal("100.00"),
                upper=Decimal("100.01"),
                count=10,
                mode=GridMode.GEOMETRIC,
                price_precision=2,
            )


class TestLevel:
    """Tests for Level dataclass."""

    def test_level_creation(self):
        from wallexbot.strategy.grid.levels import Level
        level = Level(index=0, price=Decimal("100.00"), side="buy")
        assert level.index == 0
        assert level.price == Decimal("100.00")
        assert level.side == "buy"

    def test_level_side_assignment(self):
        from wallexbot.strategy.grid.levels import Level, assign_sides
        levels = [
            Level(index=0, price=Decimal("90.00"), side=""),
            Level(index=1, price=Decimal("95.00"), side=""),
            Level(index=2, price=Decimal("100.00"), side=""),
            Level(index=3, price=Decimal("105.00"), side=""),
            Level(index=4, price=Decimal("110.00"), side=""),
        ]
        # Current price at 100.00
        assigned = assign_sides(levels, Decimal("100.00"))
        # Levels below price -> buy, above -> sell, at price -> skipped (empty)
        assert assigned[0].side == "buy"
        assert assigned[1].side == "buy"
        assert assigned[2].side == ""  # at price
        assert assigned[3].side == "sell"
        assert assigned[4].side == "sell"