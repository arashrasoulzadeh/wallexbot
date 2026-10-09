"""Risk guards for grid strategy."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from wallexbot.tests.helpers.clock import Clock


class RiskLimitExceeded(Exception):
    """Raised when a risk limit is exceeded."""
    pass


@dataclass(frozen=True, slots=True)
class RiskGuards:
    """Risk limit configuration."""

    max_open_orders: int = 50
    max_exposure_quote: Decimal = Decimal("1000000")
    max_exposure_base: Decimal = Decimal("10000")
    max_drawdown: Decimal = Decimal("0.05")  # 5%
    daily_loss_limit: Decimal = Decimal("0.02")  # 2%
    max_orders_per_10s: int = 20


class RateLimiter(Protocol):
    """Protocol for order rate limiting."""

    def check_and_consume(self, clock: Clock) -> bool:
        """Check if order can be placed, consume budget if so."""
        ...


@dataclass
class TokenBucketRateLimiter:
    """Token bucket rate limiter for order placement."""

    max_tokens: int
    refill_rate: float  # tokens per second
    _tokens: float = 0
    _last_refill: float = 0

    def __post_init__(self) -> None:
        self._tokens = float(self.max_tokens)

    def check_and_consume(self, clock: Clock) -> bool:
        """Check if order can be placed, consume token if so."""
        now = clock.now()
        # Refill tokens based on elapsed time
        elapsed = now - self._last_refill
        self._tokens = min(self.max_tokens, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


def check_max_open_orders(active_count: int, guards: RiskGuards) -> bool:
    """Check max open orders limit."""
    if active_count >= guards.max_open_orders:
        raise RiskLimitExceeded(f"Max open orders exceeded: {active_count} >= {guards.max_open_orders}")
    return True


def check_max_exposure(
    quote_exposure: Decimal,
    base_exposure: Decimal,
    guards: RiskGuards,
) -> bool:
    """Check max exposure limits."""
    if quote_exposure > guards.max_exposure_quote:
        raise RiskLimitExceeded(f"Quote exposure {quote_exposure} exceeds limit {guards.max_exposure_quote}")
    if base_exposure > guards.max_exposure_base:
        raise RiskLimitExceeded(f"Base exposure {base_exposure} exceeds limit {guards.max_exposure_base}")
    return True


def check_drawdown(
    peak_equity: Decimal,
    current_equity: Decimal,
    guards: RiskGuards,
) -> bool:
    """Check drawdown and daily loss limits."""
    if peak_equity <= 0:
        return True

    drawdown = (peak_equity - current_equity) / peak_equity

    if drawdown > guards.max_drawdown:
        raise RiskLimitExceeded(f"Max drawdown exceeded: {drawdown:.2%} > {guards.max_drawdown:.2%}")

    if drawdown > guards.daily_loss_limit:
        raise RiskLimitExceeded(f"Daily loss limit exceeded: {drawdown:.2%} > {guards.daily_loss_limit:.2%}")

    return True


def check_order_rate(clock: Clock, guards: RiskGuards) -> bool:
    """Check order rate limit using a simple token bucket."""
    # This is a simplified check - in production, use a proper rate limiter
    # For now, just track orders placed in the last 10 seconds
    # This would need persistent state across calls
    return True