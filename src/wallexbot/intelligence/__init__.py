"""Intelligence package for adaptive grid strategies."""

from wallexbot.intelligence.indicators import (
    calculate_atr,
    calculate_std_returns,
    calculate_adx,
    detect_regime,
    calculate_donchian,
    calculate_percentile_in_range,
    check_liquidity,
)
from wallexbot.intelligence.smart_grid import (
    suggest_range,
    suggest_spacing,
    suggest_capital_allocation,
    should_run_grid,
    RangeSuggestion,
    SpacingSuggestion,
    CapitalAllocation,
    GridRunDecision,
)
from wallexbot.intelligence.adaptive import (
    recenter_grid,
    dynamic_spacing,
    trend_guard,
    anomaly_guard,
    AdaptiveAction,
    AdaptiveDecision,
)
from wallexbot.intelligence.optimizer import (
    grid_search_optimizer,
    random_search_optimizer,
    walk_forward_validation,
    monte_carlo_simulation,
    OptimizationResult,
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