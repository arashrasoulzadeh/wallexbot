"""Clock protocol for time-dependent operations."""

from __future__ import annotations
from typing import Protocol


class Clock(Protocol):
    """Injectable clock protocol for testing."""

    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
    async def async_sleep(self, seconds: float) -> None: ...