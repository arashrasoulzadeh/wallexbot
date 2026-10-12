"""Rate limiter for simulating exchange API limits."""

from typing import Protocol

from wallexbot.domain import Clock


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Clock,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clock = clock
        self._requests: list[float] = []

    def acquire(self) -> bool:
        """Try to acquire a request slot. Returns True if allowed."""
        now = self.clock.now()

        # Remove expired requests
        cutoff = now - self.window_seconds
        self._requests = [t for t in self._requests if t > cutoff]

        if len(self._requests) < self.max_requests:
            self._requests.append(now)
            return True

        return False

    def wait_for_slot(self) -> None:
        """Wait until a slot is available."""
        while not self.acquire():
            self.clock.sleep(0.1)