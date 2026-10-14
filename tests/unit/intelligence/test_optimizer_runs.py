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


def test_random_search_samples_prices_inside_the_requested_range():
    """Regression: 'log-uniform' sampling used random.expovariate and produced prices near 0.2."""
    import random

    from wallexbot.intelligence.optimizer import random_search_optimizer

    random.seed(7)
    results = random_search_optimizer(
        param_ranges={
            "lower_price": (D("80"), D("95")),
            "upper_price": (D("105"), D("120")),
            "grid_count": (3, 8),
        },
        candles=candles(),
        base_config=BASE,
        n_iterations=15,
    )

    assert results, "random search found nothing to score"
    for r in results:
        assert D("80") <= r.params.lower_price <= D("95")
        assert D("105") <= r.params.upper_price <= D("120")
        assert 3 <= r.params.grid_count <= 8


def longer_candles(n=60) -> list[Candle]:
    out = []
    for i in range(n):
        c = D(100) + D((i % 8) - 4)  # a price that keeps swinging 96..103
        out.append(
            Candle(
                symbol=Symbol("USDTTMN"),
                resolution="60",
                open_time=1_700_000_000 + i * 3600,
                open=c,
                high=c + 1,
                low=c - 1,
                close=c,
                volume=D("1000"),
            )
        )
    return out


def test_walk_forward_scores_each_window_on_data_it_never_saw():
    import random

    from wallexbot.intelligence.optimizer import walk_forward_validation

    random.seed(3)
    windows = walk_forward_validation(
        param_ranges={"grid_count": (3, 6)},
        candles=longer_candles(60),
        base_config=BASE,
        train_window=30,
        test_window=10,
        step=10,
    )
    assert windows, "no walk-forward window produced a result"
    for w in windows:
        assert w["in_sample_score"] is not None and w["out_of_sample_score"] is not None
        assert (
            w["train_window"][-1].open_time < w["test_window"][0].open_time
        )  # test comes after train
        assert w["out_of_sample_metrics"] is not None


def test_monte_carlo_summarises_many_shuffled_paths():
    import random

    from wallexbot.intelligence.optimizer import monte_carlo_simulation

    random.seed(5)
    summary = monte_carlo_simulation(params(), longer_candles(40), BASE, n_simulations=8)
    assert {"mean_pnl", "median_pnl", "p5_pnl", "p95_pnl", "prob_profit", "max_drawdown_95"} <= set(
        summary
    )
    assert 0 <= summary["prob_profit"] <= 1 and summary["p5_pnl"] <= summary["p95_pnl"]


def test_monte_carlo_without_prices_is_empty():
    from wallexbot.intelligence.optimizer import monte_carlo_simulation

    assert monte_carlo_simulation(params(), longer_candles(1), BASE, n_simulations=3) == {}


def test_every_objective_gives_a_score():
    from wallexbot.intelligence.optimizer import _calculate_score

    result = _run_single_backtest(params(), longer_candles(40), BASE)
    assert result is not None
    for objective in (
        "total_return",
        "risk_adjusted_return",
        "sharpe",
        "profit_factor",
        "anything-else",
    ):
        assert isinstance(_calculate_score(result, objective), D)
