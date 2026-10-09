"""Fake clock utility for deterministic testing."""

from __future__ import annotations
import time
from typing import Protocol
from dataclasses import dataclass, field


class Clock(Protocol):
    """Injectable clock protocol for testing."""

    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


@dataclass
class FakeClock:
    """Deterministic fake clock for testing."""
    _time: float = field(default_factory=time.time)

    def now(self) -> float:
        return self._time

    def sleep(self, seconds: float) -> None:
        self._time += seconds

    def advance(self, seconds: float) -> None:
        """Advance the clock by the given seconds."""
        self._time += seconds

    def set_time(self, timestamp: float) -> None:
        """Set the clock to a specific timestamp."""
        self._time = timestamp


@dataclass
class RealClock:
    """Real system clock."""

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)