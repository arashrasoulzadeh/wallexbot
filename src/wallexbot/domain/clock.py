"""Clock protocol for time-dependent operations."""

from __future__ import annotations

import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    """Injectable clock protocol for testing."""

    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
    async def async_sleep(self, seconds: float) -> None: ...


class SystemClock:
    """Real wall clock (the default outside of tests)."""

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    async def async_sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class ManualClock:
    """A clock that only moves when told to: simulated time for backtests and replays."""

    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def now(self) -> float:
        return self._time

    def sleep(self, seconds: float) -> None:
        self._time += seconds

    async def async_sleep(self, seconds: float) -> None:
        self._time += seconds

    def set_time(self, timestamp: float) -> None:
        self._time = timestamp
