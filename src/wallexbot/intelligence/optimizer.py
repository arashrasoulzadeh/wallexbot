"""Parameter optimizer and validation."""

import math
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from wallexbot.analytics.backtest import Backtester, BacktestMetrics, BacktestResult
from wallexbot.analytics.replay import candles_to_ticks
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Symbol
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridParameters
from wallexbot.wallex.price_feed import PriceFeedReplay


@dataclass
class OptimizationResult:
    """Result of parameter optimization."""

    params: GridParameters
    metrics: BacktestMetrics
    score: Decimal


def grid_search_optimizer(
    param_grid: dict[str, Any],
    candles: list[Any],
    base_config: dict[str, Any],
    objective: str = "risk_adjusted_return",
    max_workers: int = 4,
) -> list[OptimizationResult]:
    """
    Grid search over parameter space.

    param_grid: dict of param_name -> list of values
    """
    results = []

    # Generate all combinations
    import itertools

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))

    for combo in combinations:
        params_dict = dict(zip(keys, combo, strict=True))

        # Create grid parameters
        grid_params = GridParameters(
            lower_price=params_dict.get("lower_price", base_config["lower_price"]),
            upper_price=params_dict.get("upper_price", base_config["upper_price"]),
            grid_count=params_dict.get("grid_count", base_config["grid_count"]),
            mode=params_dict.get("mode", base_config["mode"]),
            total_investment=params_dict.get("total_investment", base_config["total_investment"]),
        )

        # Run backtest
        result = _run_single_backtest(grid_params, candles, base_config)

        if result:
            score = _calculate_score(result, objective)
            results.append(
                OptimizationResult(
                    params=grid_params,
                    metrics=result.metrics,
                    score=score,
                )
            )

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def random_search_optimizer(
    param_ranges: dict[str, Any],
    candles: list[Any],
    base_config: dict[str, Any],
    n_iterations: int = 100,
    objective: str = "risk_adjusted_return",
    max_workers: int = 4,
) -> list[OptimizationResult]:
    """
    Random search over parameter space.

    More efficient than grid search for high-dimensional spaces.
    """
    results = []

    for _ in range(n_iterations):
        # Sample random parameters
        params_dict = {}
        for key, (min_val, max_val) in param_ranges.items():
            if isinstance(min_val, int):
                params_dict[key] = random.randint(min_val, max_val)
            elif isinstance(min_val, Decimal):
                # Log-uniform for prices, uniform for others
                if "price" in key:
                    # Log-uniform sampling between the bounds
                    sampled = Decimal(
                        str(math.exp(random.uniform(math.log(min_val), math.log(max_val))))
                    )
                    params_dict[key] = min(max(sampled, min_val), max_val)
                else:
                    params_dict[key] = min_val + (max_val - min_val) * Decimal(str(random.random()))
            else:
                params_dict[key] = random.choice(min_val) if isinstance(min_val, list) else min_val

        # Create grid parameters
        grid_params = GridParameters(
            lower_price=params_dict.get("lower_price", base_config["lower_price"]),
            upper_price=params_dict.get("upper_price", base_config["upper_price"]),
            grid_count=params_dict.get("grid_count", base_config["grid_count"]),
            mode=params_dict.get("mode", base_config["mode"]),
            total_investment=params_dict.get("total_investment", base_config["total_investment"]),
        )

        # Run backtest
        result = _run_single_backtest(grid_params, candles, base_config)

        if result:
            score = _calculate_score(result, objective)
            results.append(
                OptimizationResult(
                    params=grid_params,
                    metrics=result.metrics,
                    score=score,
                )
            )

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def walk_forward_validation(
    param_ranges: dict[str, Any],
    candles: list[Any],
    base_config: dict[str, Any],
    train_window: int = 500,
    test_window: int = 100,
    step: int = 50,
    objective: str = "risk_adjusted_return",
) -> list[dict[str, Any]]:
    """
    Walk-forward validation.

    Optimize on train window, test on test window, roll forward.
    Reports in-sample vs out-of-sample performance gap.
    """
    results = []
    n = len(candles)

    for start in range(0, n - train_window - test_window, step):
        train_candles = candles[start : start + train_window]
        test_candles = candles[start + train_window : start + train_window + test_window]

        # Optimize on training window
        opt_results = random_search_optimizer(
            param_ranges=param_ranges,
            candles=train_candles,
            base_config=base_config,
            n_iterations=20,
            objective=objective,
        )

        if not opt_results:
            continue

        best_params = opt_results[0].params

        # Test on out-of-sample window
        test_result = _run_single_backtest(best_params, test_candles, base_config)

        if test_result:
            # Also get in-sample performance
            train_result = _run_single_backtest(best_params, train_candles, base_config)

            results.append(
                {
                    "window_start": start,
                    "train_window": train_candles,
                    "test_window": test_candles,
                    "best_params": best_params,
                    "in_sample_score": opt_results[0].score if opt_results else None,
                    "out_of_sample_score": _calculate_score(test_result, objective)
                    if test_result
                    else None,
                    "in_sample_metrics": train_result.metrics if train_result else None,
                    "out_of_sample_metrics": test_result.metrics if test_result else None,
                }
            )

    return results


def monte_carlo_simulation(
    params: GridParameters,
    candles: list[Any],
    base_config: dict[str, Any],
    n_simulations: int = 1000,
    block_size: int = 20,
) -> dict[str, Any]:
    """
    Monte Carlo robustness test.

    Bootstrap/shuffle return paths to get distribution of outcomes.
    """
    # Extract returns from candles
    returns = []
    for i in range(1, len(candles)):
        ret = float(candles[i].close / candles[i - 1].close - 1)
        returns.append(ret)

    if not returns:
        return {}

    results = []

    for _ in range(n_simulations):
        # Bootstrap sample returns
        sampled_returns = random.choices(returns, k=len(returns))

        # Reconstruct price path
        price = float(candles[0].close)
        sim_candles = []
        for r in sampled_returns:
            price = price * (1 + r)
            # Create mock candle
            from wallexbot.wallex.models import Candle

            sim_candles.append(
                Candle(
                    symbol=Symbol("USDTTMN"),
                    resolution="60",
                    open_time=0,
                    open=Decimal(str(price)),
                    high=Decimal(str(price * 1.001)),
                    low=Decimal(str(price * 0.999)),
                    close=Decimal(str(price)),
                    volume=Decimal("1000"),
                )
            )

        result = _run_single_backtest(params, sim_candles, base_config)
        if result:
            results.append(
                {
                    "realized_pnl": float(result.metrics.realized_pnl),
                    "max_drawdown": float(result.metrics.max_drawdown),
                    "total_return": float(result.metrics.total_return_pct),
                }
            )

    if not results:
        return {}

    # Calculate statistics
    pnls = [r["realized_pnl"] for r in results]
    drawdowns = [r["max_drawdown"] for r in results]
    returns_list = [r["total_return"] for r in results]

    pnls.sort()
    drawdowns.sort()
    returns_list.sort()

    return {
        "mean_pnl": sum(pnls) / len(pnls),
        "median_pnl": pnls[len(pnls) // 2],
        "p5_pnl": pnls[int(len(pnls) * 0.05)],
        "p95_pnl": pnls[int(len(pnls) * 0.95)],
        "mean_drawdown": sum(drawdowns) / len(drawdowns),
        "max_drawdown_95": drawdowns[int(len(drawdowns) * 0.95)],
        "prob_profit": sum(1 for p in pnls if p > 0) / len(pnls),
        "prob_drawdown_gt_5pct": sum(1 for d in drawdowns if d > 5) / len(drawdowns),
        "mean_return": sum(returns_list) / len(returns_list),
    }


def _run_single_backtest(
    params: GridParameters,
    candles: list[Any],
    base_config: dict[str, Any],
) -> BacktestResult | None:
    """Run a single backtest with given parameters."""
    try:
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )

        strategy = GridStrategy(market=market, params=params)

        exchange = SimulatedExchange(
            market=market,
            fee_schedule_config=FeeSchedule(
                maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")
            ),
            min_notional_rule=MinNotionalRule(
                min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")
            ),
            initial_balances={
                "TMN": Balance(
                    free=base_config.get("initial_balance_quote", Decimal("2000000.00")),
                    locked=Decimal("0"),
                ),
                "USDT": Balance(
                    free=base_config.get("initial_balance_base", Decimal("0")),
                    locked=Decimal("0"),
                ),
            },
        )

        # Four ticks per candle (open, extremes, close), not just the close
        ticks = candles_to_ticks(candles)

        price_feed = PriceFeedReplay(ticks)

        backtester = Backtester(
            strategy=strategy,
            exchange=exchange,
            price_feed=price_feed,
        )

        return backtester.run()

    except ValueError:
        # Invalid parameter combination (e.g. orders below the minimum size): skip it.
        # Anything else is a bug and must surface, not be swallowed.
        return None


def _calculate_score(result: BacktestResult, objective: str) -> Decimal:
    """Calculate optimization score from backtest result."""
    m = result.metrics

    if objective == "total_return":
        return m.total_return_pct
    elif objective == "risk_adjusted_return":
        # Return / max drawdown
        if m.max_drawdown > 0:
            return m.total_return_pct / m.max_drawdown
        return Decimal("0")
    elif objective == "sharpe":
        # Simplified Sharpe (return / volatility proxy)
        if m.max_drawdown > 0:
            return m.total_return_pct / m.max_drawdown
        return Decimal("0")
    elif objective == "profit_factor":
        # Would need gross profit / gross loss
        return m.total_return_pct
    else:
        return m.total_return_pct
