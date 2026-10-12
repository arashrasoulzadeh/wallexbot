"""Technical indicators for market analysis."""

from decimal import Decimal
from typing import Any

from wallexbot.wallex.models import Candle


def calculate_atr(candles: list[Candle], period: int = 14) -> Decimal:
    """
    Calculate Average True Range (ATR).

    ATR measures volatility by calculating the average of true ranges
    over the specified period.
    """
    if len(candles) < period + 1:
        return Decimal("0")

    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(tr)

    # Calculate SMA of true ranges
    recent_tr = true_ranges[-period:]
    atr = sum(recent_tr) / Decimal(str(period))
    return atr


def calculate_std_returns(candles: list[Candle], period: int = 20) -> Decimal:
    """
    Calculate standard deviation of returns.

    Returns the standard deviation of log returns over the period.
    """
    if len(candles) < period + 1:
        return Decimal("0")

    returns = []
    for i in range(1, len(candles)):
        if candles[i - 1].close > 0:
            ret = (candles[i].close / candles[i - 1].close).ln()
            returns.append(ret)

    recent_returns = returns[-period:]
    if not recent_returns:
        return Decimal("0")

    mean = sum(recent_returns) / Decimal(str(len(recent_returns)))
    variance = sum((r - mean) ** 2 for r in recent_returns) / Decimal(str(len(recent_returns)))
    return variance.sqrt()


def calculate_adx(candles: list[Candle], period: int = 14) -> Decimal:
    """
    Calculate Average Directional Index (ADX).

    ADX measures trend strength regardless of direction.
    """
    if len(candles) < period + 1:
        return Decimal("0")

    plus_dm = []
    minus_dm = []
    tr_list = []

    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev_high = candles[i - 1].high
        prev_low = candles[i - 1].low
        prev_close = candles[i - 1].close

        # True Range
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        tr_list.append(tr)

        # Directional Movement
        up_move = high - prev_high
        down_move = prev_low - low

        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(Decimal("0"))

        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(Decimal("0"))

    # Smooth with Wilder's smoothing (similar to EMA)
    def wilders_smooth(values: list[Decimal], period: int) -> list[Decimal]:
        if len(values) < period:
            return []
        smoothed = []
        # First value is SMA
        first = sum(values[:period]) / Decimal(str(period))
        smoothed.append(first)
        # Rest use Wilder's smoothing: (prev * (period-1) + current) / period
        for i in range(period, len(values)):
            smoothed.append((smoothed[-1] * (period - 1) + values[i]) / Decimal(str(period)))
        return smoothed

    tr_smooth = wilders_smooth(tr_list, period)
    plus_dm_smooth = wilders_smooth(plus_dm, period)
    minus_dm_smooth = wilders_smooth(minus_dm, period)

    if not tr_smooth:
        return Decimal("0")

    # Calculate DI+ and DI-
    di_plus = [
        (plus_dm_smooth[i] / tr_smooth[i] * 100) if tr_smooth[i] > 0 else Decimal("0")
        for i in range(len(tr_smooth))
    ]
    di_minus = [
        (minus_dm_smooth[i] / tr_smooth[i] * 100) if tr_smooth[i] > 0 else Decimal("0")
        for i in range(len(tr_smooth))
    ]

    # Calculate DX
    dx_values = []
    for i in range(len(di_plus)):
        di_sum = di_plus[i] + di_minus[i]
        if di_sum > 0:
            dx = abs(di_plus[i] - di_minus[i]) / di_sum * 100
        else:
            dx = Decimal("0")
        dx_values.append(dx)

    # ADX is smoothed DX
    if len(dx_values) < period:
        return Decimal("0")

    adx = sum(dx_values[-period:]) / Decimal(str(period))
    return adx


def detect_regime(candles: list[Candle], period: int = 20) -> str:
    """
    Detect market regime.

    Returns: "ranging", "trending_up", "trending_down", or "volatile"
    """
    if len(candles) < period + 1:
        return "ranging"

    adx = calculate_adx(candles, period)
    returns = [(candles[i].close / candles[i - 1].close - 1) for i in range(1, len(candles))]
    recent_returns = returns[-period:]

    # Calculate trend slope
    x_sum = sum(Decimal(str(i)) for i in range(len(recent_returns)))
    y_sum = sum(recent_returns)
    xy_sum = sum(Decimal(str(i)) * r for i, r in enumerate(recent_returns))
    x2_sum = sum(Decimal(str(i)) ** 2 for i in range(len(recent_returns)))
    n = Decimal(str(len(recent_returns)))

    slope = (
        (n * xy_sum - x_sum * y_sum) / (n * x2_sum - x_sum * x_sum)
        if (n * x2_sum - x_sum * x_sum) != 0
        else Decimal("0")
    )

    # Classify regime
    if adx > 25:
        if slope > 0:
            return "trending_up"
        else:
            return "trending_down"
    elif adx < 20:
        # Check volatility
        std = calculate_std_returns(candles, period)
        if std > Decimal("0.02"):  # 2% daily vol threshold
            return "volatile"
        return "ranging"
    else:
        return "ranging"


def calculate_donchian(candles: list[Candle], period: int = 20) -> tuple[Decimal, Decimal]:
    """
    Calculate Donchian channels.

    Returns (upper, lower) channel values.
    """
    if len(candles) < period:
        return Decimal("0"), Decimal("0")

    recent = candles[-period:]
    upper = max(c.high for c in recent)
    lower = min(c.low for c in recent)
    return upper, lower


def calculate_percentile_in_range(candles: list[Candle], period: int = 20) -> Decimal:
    """
    Calculate percentile of current price within recent range.

    Returns 0-100 percentile.
    """
    if len(candles) < period:
        return Decimal("50")

    recent = candles[-period:]
    upper = max(c.high for c in recent)
    lower = min(c.low for c in recent)
    current = candles[-1].close

    if upper == lower:
        return Decimal("50")

    percentile = (current - lower) / (upper - lower) * 100
    return max(Decimal("0"), min(Decimal("100"), percentile))


def check_liquidity(depth: dict[str, Any], min_spread_bps: int = 5) -> tuple[bool, str]:
    """
    Check if market has sufficient liquidity.

    Returns (is_liquid, message).
    """
    bids = depth.get("bids", [])
    asks = depth.get("asks", [])

    if not bids or not asks:
        return False, "Empty order book"

    best_bid = Decimal(bids[0][0])
    best_ask = Decimal(asks[0][0])

    if best_bid <= 0 or best_ask <= 0:
        return False, "Invalid prices"

    spread_bps = (best_ask - best_bid) / best_bid * 10000

    if spread_bps > min_spread_bps:
        return False, f"Spread too wide: {spread_bps:.1f} bps"

    # Check depth
    bid_volume = sum(Decimal(b[1]) for b in bids[:5])
    ask_volume = sum(Decimal(a[1]) for a in asks[:5])

    if bid_volume < Decimal("100") or ask_volume < Decimal("100"):
        return False, f"Insufficient depth: bid={bid_volume}, ask={ask_volume}"

    return True, "OK"
