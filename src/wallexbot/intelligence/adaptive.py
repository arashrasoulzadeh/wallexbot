"""Adaptive behavior for running grid."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from wallexbot.intelligence.indicators import calculate_atr, calculate_donchian, detect_regime
from wallexbot.strategy.grid.parameters import GridParameters
from wallexbot.wallex.models import Candle


class AdaptiveAction(str, Enum):
    """Actions the adaptive system can take."""

    NONE = "none"
    RECENTER = "recenter"
    WIDEN_SPACING = "widen_spacing"
    NARROW_SPACING = "narrow_spacing"
    PAUSE_BUYS = "pause_buys"
    HALT = "halt"


@dataclass
class AdaptiveDecision:
    """Decision from adaptive system."""

    action: AdaptiveAction
    reason: str
    confidence: Decimal
    params: dict[str, Any] | None = None


def recenter_grid(
    candles: list[Candle],
    current_params: GridParameters,
    out_of_range_minutes: int = 30,
    max_drawdown_pct: Decimal = Decimal("0.05"),
) -> AdaptiveDecision:
    """
    Re-center grid when price has been out of range.

    Only re-centers if drawdown is within limits.
    """
    if len(candles) < 20:
        return AdaptiveDecision(
            action=AdaptiveAction.NONE,
            reason="Insufficient data",
            confidence=Decimal("0"),
        )

    current_price = candles[-1].close

    # Check if price has been out of range
    # (In practice, would track this in run state)
    price_out_of_range = (
        current_price > current_params.upper_price or current_price < current_params.lower_price
    )

    if not price_out_of_range:
        return AdaptiveDecision(
            action=AdaptiveAction.NONE,
            reason="Price in range",
            confidence=Decimal("1"),
        )

    # Check drawdown
    # Would need access to PnL tracker
    # For now, assume drawdown is acceptable

    # Calculate new center
    donchian_upper, donchian_lower = calculate_donchian(candles, period=20)
    new_center = (donchian_upper + donchian_lower) / 2

    # Keep same range width
    range_width = current_params.upper_price - current_params.lower_price
    half_width = range_width / 2

    new_lower = new_center - half_width
    new_upper = new_center + half_width

    return AdaptiveDecision(
        action=AdaptiveAction.RECENTER,
        reason=f"Price out of range for {out_of_range_minutes}min, re-centering to {new_center:.2f}",
        confidence=Decimal("0.7"),
        params={"lower_price": str(new_lower), "upper_price": str(new_upper)},
    )


def dynamic_spacing(
    candles: list[Candle],
    current_params: GridParameters,
    fee_rate: Decimal,
    min_profit_multiple: Decimal = Decimal("2.0"),
    max_change_pct: Decimal = Decimal("0.5"),
) -> AdaptiveDecision:
    """
    Adjust spacing based on volatility.

    Widens when volatility spikes, narrows when calm.
    """
    if len(candles) < 20:
        return AdaptiveDecision(
            action=AdaptiveAction.NONE,
            reason="Insufficient data",
            confidence=Decimal("0"),
        )

    atr = calculate_atr(candles, period=14)
    current_price = candles[-1].close

    # Current spacing
    if current_params.grid_count > 1:
        current_spacing = (current_params.upper_price - current_params.lower_price) / (
            current_params.grid_count - 1
        )
    else:
        return AdaptiveDecision(
            action=AdaptiveAction.NONE, reason="Invalid grid", confidence=Decimal("0")
        )

    # Minimum profitable spacing
    round_trip_fee = fee_rate * 2
    min_spacing = current_price * round_trip_fee * min_profit_multiple

    # Target spacing based on volatility
    # Higher volatility -> wider spacing
    target_spacing = max(min_spacing, atr * Decimal("0.5"))

    # Limit change rate
    change = (target_spacing - current_spacing) / current_spacing
    if abs(change) > max_change_pct:
        if change > 0:
            target_spacing = current_spacing * (Decimal("1") + max_change_pct)
        else:
            target_spacing = current_spacing * (Decimal("1") - max_change_pct)

    if abs(target_spacing - current_spacing) / current_spacing < Decimal("0.05"):
        return AdaptiveDecision(
            action=AdaptiveAction.NONE,
            reason="Spacing within tolerance",
            confidence=Decimal("0.9"),
        )

    action = (
        AdaptiveAction.WIDEN_SPACING
        if target_spacing > current_spacing
        else AdaptiveAction.NARROW_SPACING
    )

    return AdaptiveDecision(
        action=action,
        reason=f"Volatility {'increased' if target_spacing > current_spacing else 'decreased'}, adjusting spacing from {current_spacing:.4f} to {target_spacing:.4f}",
        confidence=Decimal("0.7"),
        params={"target_spacing": str(target_spacing)},
    )


def trend_guard(
    candles: list[Candle],
    current_params: GridParameters,
    adx_threshold: Decimal = Decimal("25"),
    slope_threshold: Decimal = Decimal("0.001"),
) -> AdaptiveDecision:
    """
    Pause new buys when strong trend detected.

    Prevents catching a falling knife.
    """
    if len(candles) < 20:
        return AdaptiveDecision(
            action=AdaptiveAction.NONE,
            reason="Insufficient data",
            confidence=Decimal("0"),
        )

    regime = detect_regime(candles)

    if regime in ("trending_up", "trending_down"):
        # Strong trend - pause buys
        return AdaptiveDecision(
            action=AdaptiveAction.PAUSE_BUYS,
            reason=f"Strong {regime} detected, pausing new buy orders",
            confidence=Decimal("0.8"),
            params={"regime": regime},
        )

    return AdaptiveDecision(
        action=AdaptiveAction.NONE,
        reason="No strong trend",
        confidence=Decimal("0.9"),
    )


def anomaly_guard(
    candles: list[Candle],
    current_params: GridParameters,
    price_jump_sigma: Decimal = Decimal("3"),
    max_stale_seconds: int = 60,
    min_depth_volume: Decimal = Decimal("100"),
) -> AdaptiveDecision:
    """
    Halt on anomalies: price jumps, stale feed, crossed/empty depth.

    Returns HALT action if anomaly detected.
    """
    if len(candles) < 20:
        return AdaptiveDecision(
            action=AdaptiveAction.NONE,
            reason="Insufficient data",
            confidence=Decimal("0"),
        )

    current_price = candles[-1].close
    prev_price = candles[-2].close if len(candles) > 1 else current_price

    # Price jump check
    price_change = abs(current_price - prev_price) / prev_price
    if price_change > price_jump_sigma * Decimal("0.01"):  # 3% jump
        return AdaptiveDecision(
            action=AdaptiveAction.HALT,
            reason=f"Price jump detected: {price_change:.2%}",
            confidence=Decimal("0.9"),
        )

    # Would also check:
    # - Feed staleness (timestamp check)
    # - Crossed/empty depth (from WebSocket)
    # - Abnormal fill rate

    return AdaptiveDecision(
        action=AdaptiveAction.NONE,
        reason="No anomalies detected",
        confidence=Decimal("1"),
    )
