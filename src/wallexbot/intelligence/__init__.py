"""Intelligence package for adaptive grid strategies."""

from wallexbot.intelligence.adaptive import (
    AdaptiveAction,
    AdaptiveDecision,
    anomaly_guard,
    dynamic_spacing,
    recenter_grid,
    trend_guard,
)
from wallexbot.intelligence.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_donchian,
    calculate_percentile_in_range,
    calculate_std_returns,
    check_liquidity,
    detect_regime,
)
from wallexbot.intelligence.optimizer import (
    OptimizationResult,
    grid_search_optimizer,
    monte_carlo_simulation,
    random_search_optimizer,
    walk_forward_validation,
)
from wallexbot.intelligence.smart_grid import (
    CapitalAllocation,
    GridRunDecision,
    RangeSuggestion,
    SpacingSuggestion,
    should_run_grid,
    suggest_capital_allocation,
    suggest_range,
    suggest_spacing,
)

__all__ = [
    # Indicators
    "calculate_atr",
    "calculate_std_returns",
    "calculate_adx",
    "detect_regime",
    "calculate_donchian",
    "calculate_percentile_in_range",
    "check_liquidity",
    # Smart grid
    "suggest_range",
    "suggest_spacing",
    "suggest_capital_allocation",
    "should_run_grid",
    "RangeSuggestion",
    "SpacingSuggestion",
    "CapitalAllocation",
    "GridRunDecision",
    # Adaptive
    "recenter_grid",
    "dynamic_spacing",
    "trend_guard",
    "anomaly_guard",
    "AdaptiveAction",
    "AdaptiveDecision",
    # Optimizer
    "grid_search_optimizer",
    "random_search_optimizer",
    "walk_forward_validation",
    "monte_carlo_simulation",
    "OptimizationResult",
]
