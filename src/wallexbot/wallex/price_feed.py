"""Price feed abstraction for market data."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, AsyncGenerator, Optional
from datetime import datetime

from wallexbot.domain.market import Symbol
from wallexbot.wallex.models import Trade, Depth


@dataclass(frozen=True, slots=True)
class PriceTick:
    """Single price update."""

    symbol: Symbol
    price: Decimal
    timestamp: int
    source: str  # "live", "replay", "test"


class PriceFeed(Protocol):
    """Price feed interface."""

    async def subscribe(self, symbol: Symbol) -> None: ...
    async def unsubscribe(self, symbol: Symbol) -> None: ...
    async def ticks(self) -> AsyncGenerator[PriceTick, None]: ...


class PriceFeedReplay:
    """Replay price feed from recorded data."""

    def __init__(self, ticks: list[PriceTick]) -> None:
        self._ticks = ticks
        self._index = 0

    async def subscribe(self, symbol: Symbol) -> None:
        pass

    async def unsubscribe(self, symbol: Symbol) -> None:
        pass

    async def ticks(self) -> AsyncGenerator[PriceTick, None]:
        for tick in self._ticks:
            yield tick

    def add_tick(self, tick: PriceTick) -> None:
        self._ticks.append(tick)