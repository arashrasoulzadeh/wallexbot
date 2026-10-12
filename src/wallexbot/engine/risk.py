"""Risk monitor: turns equity readings into a "stop trading" decision.

Two limits, both as fractions (0.05 = 5%) and both optional:

- max drawdown: how far equity may fall below its highest value since the run started;
- daily loss limit: how far equity may fall below its first value of the current UTC day.

A limit is breached only when strictly exceeded, so an equity exactly at the limit keeps running.
"""

from datetime import UTC, datetime
from decimal import Decimal


class RiskMonitor:
    """Tracks equity and reports the first limit that is broken."""

    def __init__(self, max_drawdown: Decimal | None, daily_loss_limit: Decimal | None) -> None:
        self.max_drawdown = max_drawdown
        self.daily_loss_limit = daily_loss_limit
        self._peak = Decimal(0)
        self._day: str | None = None
        self._day_start = Decimal(0)

    def update(self, equity: Decimal, timestamp_ms: int) -> str | None:
        """Feed the latest equity; returns a human-readable reason if a limit is exceeded."""
        day = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m-%d")
        if day != self._day:
            self._day = day
            self._day_start = equity
        self._peak = max(self._peak, equity)

        if self.max_drawdown is not None and self._peak > 0:
            drawdown = (self._peak - equity) / self._peak
            if drawdown > self.max_drawdown:
                return f"max drawdown {drawdown:.2%} exceeded the limit of {self.max_drawdown:.2%}"

        if self.daily_loss_limit is not None and self._day_start > 0:
            loss = (self._day_start - equity) / self._day_start
            if loss > self.daily_loss_limit:
                return f"daily loss {loss:.2%} exceeded the limit of {self.daily_loss_limit:.2%}"

        return None
