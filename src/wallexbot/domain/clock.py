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
