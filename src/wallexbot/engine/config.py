"""Bot engine configuration."""

from dataclasses import dataclass
from typing import Optional

from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.wallex.price_feed import PriceFeed
from wallexbot.domain import Clock


@dataclass
class EngineConfig:
    """Bot engine configuration."""

    strategy: GridStrategy
    exchange: SimulatedExchange
    price_feed: PriceFeed
    clock: Clock
    poll_interval: float = 1.0  # seconds
    max_poll_retries: int = 3