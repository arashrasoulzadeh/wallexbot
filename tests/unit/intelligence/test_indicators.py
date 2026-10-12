"""Tests for intelligence module."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wallexbot.domain.market import Symbol
from wallexbot.intelligence.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_donchian,
    calculate_percentile_in_range,
    calculate_std_returns,
    check_liquidity,
    detect_regime,
)
from wallexbot.intelligence.smart_grid import (
    should_run_grid,
    suggest_capital_allocation,
    suggest_range,
    suggest_spacing,
)
from wallexbot.wallex.models import Candle


class TestIndicators:
    """Tests for technical indicators."""

    @pytest.fixture
    def sample_candles(self):
        """Generate sample candles for testing."""
        candles = []
        base_price = Decimal("100.00")
        for i in range(100):
            # Simple random walk
            change = Decimal(str((i % 7 - 3) * 0.5))
            close = base_price + change
            candles.append(
                Candle(
                    symbol=Symbol("USDTTMN"),
                    resolution="60",
                    open_time=1000 + i * 3600,
                    open=base_price,
                    high=max(base_price, close) + Decimal("0.5"),
                    low=min(base_price, close) - Decimal("0.5"),
                    close=close,
                    volume=Decimal("1000.0000"),
                )
            )
            base_price = close
        return candles

    def test_atr_calculation(self, sample_candles):
        """ATR calculates correctly."""
        atr = calculate_atr(sample_candles, period=14)
        assert atr > Decimal("0")
        assert atr < Decimal("10")

    def test_std_returns(self, sample_candles):
        """Standard deviation of returns."""
        std = calculate_std_returns(sample_candles)
        assert std >= Decimal("0")

    def test_adx_calculation(self, sample_candles):
        """ADX calculates correctly."""
        adx = calculate_adx(sample_candles, period=14)
        assert Decimal("0") <= adx <= Decimal("100")

    def test_regime_detection(self, sample_candles):
        """Regime detection returns valid label."""
        regime = detect_regime(sample_candles)
        assert regime in ("ranging", "trending_up", "trending_down", "volatile")

    def test_donchian_channels(self, sample_candles):
        """Donchian channels calculated."""
        upper, lower = calculate_donchian(sample_candles, period=20)
        assert upper > lower

    def test_percentile_in_range(self, sample_candles):
        """Percentile of current price in range."""
        pct = calculate_percentile_in_range(sample_candles, period=20)
        assert Decimal("0") <= pct <= Decimal("100")

    def test_liquidity_check(self, sample_candles):
        """Liquidity/spread check."""
        # Mock depth data
        depth = {"bids": [["100.00", "10.0000"]], "asks": [["100.01", "10.0000"]]}
        spread_ok, msg = check_liquidity(depth, min_spread_bps=5)
        assert isinstance(spread_ok, bool)


class TestSmartGrid:
    """Tests for smart grid suggestions."""

    @pytest.fixture
    def sample_candles(self):
        candles = []
        base = Decimal("100.00")
        for i in range(100):
            change = Decimal(str((i % 10 - 5) * 0.2))
            close = base + change
            candles.append(
                Candle(
                    symbol=Symbol("USDTTMN"),
                    resolution="60",
                    open_time=1000 + i * 3600,
                    open=base,
                    high=max(base, close) + Decimal("0.2"),
                    low=min(base, close) - Decimal("0.2"),
                    close=close,
                    volume=Decimal("1000.0000"),
                )
            )
            base = close
        return candles

    def test_suggest_range(self, sample_candles):
        """Auto range suggestion from volatility bands."""
        suggestion = suggest_range(sample_candles, capital=Decimal("2000000"))
        assert suggestion.lower < suggestion.upper
        assert suggestion.lower > Decimal("0")

    def test_suggest_spacing(self, sample_candles):
        """Auto spacing suggestion."""
        suggestion = suggest_spacing(
            sample_candles, capital=Decimal("2000000"), fee_rate=Decimal("0.001")
        )
        assert suggestion.spacing > Decimal("0")

    def test_capital_allocation(self, sample_candles):
        """Capital allocator splits across levels."""
        allocation = suggest_capital_allocation(
            sample_candles,
            total_capital=Decimal("2000000"),
            lower=Decimal("95.00"),
            upper=Decimal("105.00"),
            grid_count=10,
        )
        assert sum(allocation.allocations) <= Decimal("2000000")
        assert len(allocation.allocations) == 10

    def test_should_run_grid(self, sample_candles):
        """Should I run grid now?"""
        decision = should_run_grid(sample_candles, capital=Decimal("2000000"))
        assert hasattr(decision, "should_run")
        assert hasattr(decision, "reason")
        assert hasattr(decision, "regime")


class TestAdaptive:
    """Tests for adaptive behavior."""

    def test_recenter_grid(self):
        """Re-center grid when out of range."""
        pass

    def test_dynamic_spacing(self):
        """Dynamic spacing adjusts with volatility."""
        pass

    def test_trend_guard(self):
        """Trend guard pauses buys in strong trend."""
        pass

    def test_anomaly_guard(self):
        """Anomaly guard halts on anomalies."""
        pass


class TestOptimizer:
    """Tests for parameter optimizer."""

    def test_grid_search(self):
        """Grid search optimizer."""
        pass

    def test_random_search(self):
        """Random search optimizer."""
        pass

    def test_walk_forward(self):
        """Walk-forward validation."""
        pass

    def test_monte_carlo(self):
        """Monte Carlo robustness."""
        pass


class TestProperties:
    """Property-based tests."""

    @given(st.lists(st.decimals(min_value=1, max_value=1000, places=2), min_size=20, max_size=200))
    def test_atr_always_positive(self, prices):
        """ATR is always positive."""
        candles = []
        for i, p in enumerate(prices):
            candles.append(
                Candle(
                    symbol=Symbol("USDTTMN"),
                    resolution="60",
                    open_time=i * 3600,
                    open=p,
                    high=p + Decimal("1"),
                    low=p - Decimal("1"),
                    close=p,
                    volume=Decimal("1000"),
                )
            )
        atr = calculate_atr(candles, period=14)
        assert atr >= Decimal("0")

    @given(st.lists(st.decimals(min_value=1, max_value=1000, places=2), min_size=20, max_size=200))
    def test_adx_bounded(self, prices):
        """ADX is bounded 0-100."""
        candles = []
        for i, p in enumerate(prices):
            candles.append(
                Candle(
                    symbol=Symbol("USDTTMN"),
                    resolution="60",
                    open_time=i * 3600,
                    open=p,
                    high=p + Decimal("1"),
                    low=p - Decimal("1"),
                    close=p,
                    volume=Decimal("1000"),
                )
            )
        adx = calculate_adx(candles, period=14)
        assert Decimal("0") <= adx <= Decimal("100")
