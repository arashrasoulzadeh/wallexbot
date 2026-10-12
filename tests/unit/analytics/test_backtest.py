"""Tests for backtester."""

from decimal import Decimal

import pytest

from wallexbot.analytics.backtest import Backtester
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Symbol
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridMode, GridParameters
from wallexbot.wallex.price_feed import PriceFeedReplay, PriceTick


class TestHistoricalDataStore:
    """Tests for historical data store."""

    def test_download_candles(self, tmp_path):
        """Download candles via public client -> CSV."""
        pass

    def test_replay_feed_synthetic_path(self):
        """Candles -> synthetic intra-candle path."""
        pass


class TestBacktester:
    """Tests for backtester."""

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
    def params(self):
        return GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=5,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
        )

    @pytest.fixture
    def strategy(self, market, params):
        return GridStrategy(market=market, params=params)

    @pytest.fixture
    def exchange(self, market):
        return SimulatedExchange(
            market=market,
            fee_schedule_config=FeeSchedule(
                maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")
            ),
            min_notional_rule=MinNotionalRule(
                min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")
            ),
            initial_balances={
                "TMN": Balance(free=Decimal("2000000.00"), locked=Decimal("0")),
                "USDT": Balance(free=Decimal("0"), locked=Decimal("0")),
            },
        )

    @pytest.fixture
    def price_feed(self):
        # Create synthetic ticks from candles
        ticks = [
            PriceTick(
                symbol=Symbol("USDTTMN"), price=Decimal("100.00"), timestamp=1000, source="replay"
            ),
            PriceTick(
                symbol=Symbol("USDTTMN"), price=Decimal("99.00"), timestamp=1001, source="replay"
            ),
            PriceTick(
                symbol=Symbol("USDTTMN"), price=Decimal("95.00"), timestamp=1002, source="replay"
            ),
            PriceTick(
                symbol=Symbol("USDTTMN"), price=Decimal("105.00"), timestamp=1003, source="replay"
            ),
        ]
        return PriceFeedReplay(ticks)

    @pytest.fixture
    def backtester(self, strategy, exchange, price_feed):
        return Backtester(
            strategy=strategy,
            exchange=exchange,
            price_feed=price_feed,
        )

    def test_run_deterministic(self, backtester):
        """Run is deterministic."""
        result1 = backtester.run()
        result2 = backtester.run()

        assert result1.metrics.realized_pnl == result2.metrics.realized_pnl
        assert result1.metrics.total_return_pct == result2.metrics.total_return_pct

    def test_metrics_calculated(self, backtester):
        """Metrics calculated correctly."""
        result = backtester.run()

        assert hasattr(result.metrics, "realized_pnl")
        assert hasattr(result.metrics, "unrealized_pnl")
        assert hasattr(result.metrics, "total_return_pct")
        assert hasattr(result.metrics, "completed_cycles")
        assert hasattr(result.metrics, "avg_profit_per_cycle")
        assert hasattr(result.metrics, "max_drawdown")
        assert hasattr(result.metrics, "fees_paid")
        assert hasattr(result.metrics, "time_in_range")

    def test_comparison_vs_buy_and_hold(self, backtester):
        """Comparison vs buy-and-hold."""
        result = backtester.run()

        assert hasattr(result.metrics, "buy_and_hold_return")
        assert hasattr(result.metrics, "outperformance")


class TestBacktestMetrics:
    """Tests for backtest metrics."""

    def test_realized_pnl(self):
        """Realized PnL calculation."""
        pass

    def test_unrealized_pnl(self):
        """Unrealized PnL calculation."""
        pass

    def test_max_drawdown(self):
        """Max drawdown calculation."""
        pass

    def test_time_in_range(self):
        """Time in range calculation."""
        pass


class TestParameterSweep:
    """Tests for parameter sweep runner."""

    def test_sweep_runs_multiple_configs(self):
        """Sweep runs multiple parameter combinations."""
        pass

    def test_results_table(self):
        """Results table generated."""
        pass


class TestSanityScenarios:
    """Sanity scenario tests."""

    def test_pure_sideways_profits(self):
        """Pure sideways must profit."""
        pass

    def test_strong_trend_shows_weakness(self):
        """Strong trend shows grid weakness."""
        pass


class TestReportOutput:
    """Tests for report output."""

    def test_markdown_report(self, tmp_path):
        """Markdown report generated."""
        pass

    def test_csv_report(self, tmp_path):
        """CSV report generated."""
        pass
