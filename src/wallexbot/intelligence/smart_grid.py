"""Smart grid setup suggestions."""

from dataclasses import dataclass
from decimal import Decimal

from wallexbot.intelligence.indicators import (
    calculate_atr,
    calculate_percentile_in_range,
    detect_regime,
)
from wallexbot.wallex.models import Candle


@dataclass
class RangeSuggestion:
    """Suggested grid range."""

    lower: Decimal
    upper: Decimal
    confidence: Decimal
    reasoning: str


@dataclass
class SpacingSuggestion:
    """Suggested grid spacing."""

    spacing: Decimal
    grid_count: int
    min_profit_per_grid: Decimal
    reasoning: str


@dataclass
class CapitalAllocation:
    """Capital allocation per level."""

    allocations: list[Decimal]
    total: Decimal
    reasoning: str


@dataclass
class GridRunDecision:
    """Decision on whether to run grid."""

    should_run: bool
    reason: str
    regime: str
    confidence: Decimal


def suggest_range(
    candles: list[Candle],
    capital: Decimal,
    k_atr: Decimal = Decimal("2.0"),
    min_range_pct: Decimal = Decimal("0.02"),
    max_range_pct: Decimal = Decimal("0.10"),
) -> RangeSuggestion:
    """
    Suggest grid range based on volatility bands.

    Uses mean ± k * ATR to set bounds.
    """
    if len(candles) < 20:
        return RangeSuggestion(
            lower=Decimal("0"),
            upper=Decimal("0"),
            confidence=Decimal("0"),
            reasoning="Insufficient data",
        )

    atr = calculate_atr(candles, period=14)
    current_price = candles[-1].close

    # Mean price (simple average of recent closes)
    recent_closes = [c.close for c in candles[-20:]]
    mean_price = sum(recent_closes) / Decimal(str(len(recent_closes)))

    # Range based on ATR
    half_range = k_atr * atr
    lower = mean_price - half_range
    upper = mean_price + half_range

    # Ensure minimum range as percentage of price
    min_range = current_price * min_range_pct
    max_range = current_price * max_range_pct
    actual_range = upper - lower

    if actual_range < min_range:
        # Expand to minimum
        center = (upper + lower) / 2
        lower = center - min_range / 2
        upper = center + min_range / 2
    elif actual_range > max_range:
        # Contract to maximum
        center = (upper + lower) / 2
        lower = center - max_range / 2
        upper = center + max_range / 2

    # Ensure positive
    lower = max(Decimal("0.01"), lower)

    return RangeSuggestion(
        lower=lower,
        upper=upper,
        confidence=Decimal("0.7"),
        reasoning=f"Range based on {k_atr}×ATR ({atr:.4f}) around mean ({mean_price:.2f})",
    )


def suggest_spacing(
    candles: list[Candle],
    capital: Decimal,
    fee_rate: Decimal,
    min_profit_multiple: Decimal = Decimal("2.0"),
    min_grid_count: int = 5,
    max_grid_count: int = 50,
) -> SpacingSuggestion:
    """
    Suggest optimal grid spacing.

    Spacing must be >= min_profit_multiple × round-trip fees
    to be profitable after costs.
    """
    if len(candles) < 20:
        return SpacingSuggestion(
            spacing=Decimal("0"),
            grid_count=0,
            min_profit_per_grid=Decimal("0"),
            reasoning="Insufficient data",
        )

    atr = calculate_atr(candles, period=14)
    current_price = candles[-1].close

    # Minimum profitable spacing
    # Round-trip fee = 2 * fee_rate (buy + sell)
    round_trip_fee = fee_rate * 2
    min_spacing = current_price * round_trip_fee * min_profit_multiple

    # Optimal spacing based on volatility
    # Use ATR as proxy for typical price movement
    optimal_spacing = atr * Decimal("0.5")  # Half ATR per level

    spacing = max(min_spacing, optimal_spacing)

    # Determine grid count based on capital and spacing
    # Range = spacing * (grid_count - 1)
    # Grid count limited by capital (each level needs minimum notional)
    min_notional = Decimal("10.00")  # From config
    max_grids_by_capital = int(capital / min_notional)

    grid_count = min(max_grid_count, max(min_grid_count, max_grids_by_capital))

    # Adjust spacing to fit grid_count within reasonable range
    suggested_range = suggest_range(candles, capital)
    range_width = suggested_range.upper - suggested_range.lower
    if grid_count > 1:
        spacing = range_width / (grid_count - 1)

    return SpacingSuggestion(
        spacing=spacing,
        grid_count=grid_count,
        min_profit_per_grid=spacing - min_spacing,
        reasoning=f"Spacing {spacing:.4f} >= {min_profit_multiple}× fees ({min_spacing:.4f})",
    )


def suggest_capital_allocation(
    candles: list[Candle],
    total_capital: Decimal,
    lower: Decimal,
    upper: Decimal,
    grid_count: int,
    mode: str = "equal",
) -> CapitalAllocation:
    """
    Allocate capital across grid levels.

    Modes: "equal" (same per level), "weighted" (more near current price)
    """
    if lower >= upper or grid_count < 2:
        return CapitalAllocation(
            allocations=[],
            total=Decimal("0"),
            reasoning="Invalid parameters",
        )

    if mode == "equal":
        per_level = total_capital / grid_count
        allocations = [per_level] * grid_count
    elif mode == "weighted":
        # Weight toward center (current price)
        current = candles[-1].close if candles else (lower + upper) / 2
        allocations = []
        total_weight = Decimal("0")

        for i in range(grid_count):
            # Linear interpolation
            price = lower + (upper - lower) * Decimal(str(i)) / (grid_count - 1)
            # Weight inversely proportional to distance from current price
            distance = abs(price - current)
            max_distance = max(current - lower, upper - current)
            weight = Decimal("1") - (distance / max_distance * Decimal("0.5"))  # 0.5 to 1.0
            allocations.append(weight)
            total_weight += weight

        # Normalize
        allocations = [w / total_weight * total_capital for w in allocations]
    else:
        per_level = total_capital / grid_count
        allocations = [per_level] * grid_count

    return CapitalAllocation(
        allocations=allocations,
        total=sum(allocations),
        reasoning=f"Capital allocated {mode} across {grid_count} levels",
    )


def should_run_grid(
    candles: list[Candle],
    capital: Decimal,
    fee_rate: Decimal = Decimal("0.001"),
) -> GridRunDecision:
    """
    Decide whether to run a grid now.

    Analyzes regime, volatility, and profitability.
    """
    if len(candles) < 50:
        return GridRunDecision(
            should_run=False,
            reason="Insufficient historical data",
            regime="unknown",
            confidence=Decimal("0"),
        )

    regime = detect_regime(candles)

    # Grid works best in ranging markets with moderate volatility
    if regime in ("trending_up", "trending_down"):
        return GridRunDecision(
            should_run=False,
            reason=f"Market trending ({regime}) - grid will accumulate losing positions",
            regime=regime,
            confidence=Decimal("0.8"),
        )

    if regime == "volatile":
        # High volatility can be good IF spacing covers fees
        spacing_sugg = suggest_spacing(candles, capital, fee_rate)

        if spacing_sugg.min_profit_per_grid > 0:
            return GridRunDecision(
                should_run=True,
                reason="Volatile but spacing covers fees",
                regime=regime,
                confidence=Decimal("0.6"),
            )
        else:
            return GridRunDecision(
                should_run=False,
                reason="Volatile and spacing doesn't cover fees",
                regime=regime,
                confidence=Decimal("0.7"),
            )

    # Ranging market
    spacing_sugg = suggest_spacing(candles, capital, fee_rate)

    if spacing_sugg.min_profit_per_grid <= 0:
        return GridRunDecision(
            should_run=False,
            reason="Ranging but fees exceed profit per grid",
            regime=regime,
            confidence=Decimal("0.7"),
        )

    # Check if current price is in reasonable range
    pct = calculate_percentile_in_range(candles)
    if pct < 20 or pct > 80:
        return GridRunDecision(
            should_run=False,
            reason=f"Price at extreme of recent range ({pct:.0f}th percentile)",
            regime=regime,
            confidence=Decimal("0.6"),
        )

    return GridRunDecision(
        should_run=True,
        reason="Ranging market, volatility OK, price in middle of range",
        regime=regime,
        confidence=Decimal("0.8"),
    )
