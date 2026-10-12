"""The optimizer must actually run backtests (regression: wrong SimulatedExchange kwarg was
swallowed by a bare `except Exception`, so every run silently returned nothing)."""

from decimal import Decimal as D

from wallexbot.domain.market import Symbol
from wallexbot.intelligence.optimizer import _run_single_backtest, grid_search_optimizer
from wallexbot.strategy.grid.parameters import GridMode, GridParameters
from wallexbot.wallex.models import Candle


def candles() -> list[Candle]:
    closes = ["100", "98", "96", "99", "102", "104", "101", "98", "100", "103"]
    return [
        Candle(
            symbol=Symbol("USDTTMN"),
            resolution="60",
            open_time=1_700_000_000 + i * 3600,
            open=D(c),
            high=D(c) + 1,
            low=D(c) - 1,
            close=D(c),
            volume=D("1000"),
        )
        for i, c in enumerate(closes)
    ]


BASE = {
    "lower_price": D("90"),
    "upper_price": D("110"),
    "grid_count": 5,
    "mode": GridMode.ARITHMETIC,
    "total_investment": D("10000"),
    "initial_balance_quote": D("2000000"),
}


def params() -> GridParameters:
    return GridParameters(
        lower_price=D("90"),
        upper_price=D("110"),
        grid_count=5,
        mode=GridMode.ARITHMETIC,
        total_investment=D("10000"),
    )


def test_single_backtest_returns_a_result():
    result = _run_single_backtest(params(), candles(), BASE)
    assert result is not None
    assert result.metrics.time_in_range >= 0


def test_grid_search_returns_one_scored_result_per_combination():
    results = grid_search_optimizer(
        param_grid={"grid_count": [3, 5]},
        candles=candles(),
        base_config=BASE,
    )
    assert len(results) == 2
    assert [r.params.grid_count for r in results] != []
    assert results[0].score >= results[1].score
