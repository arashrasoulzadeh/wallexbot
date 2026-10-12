"""Bot engine configuration."""

from dataclasses import dataclass

from wallexbot.engine.risk import RiskMonitor
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.storage.repository import Repository
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.wallex.price_feed import PriceFeed


@dataclass
class EngineConfig:
    """Everything a paper-trading run needs."""

    strategy: GridStrategy
    exchange: SimulatedExchange
    price_feed: PriceFeed
    risk: RiskMonitor | None = None  # None = no automatic kill switch
    cancel_on_shutdown: bool = True  # cancel resting orders when the run ends or is stopped
    repository: Repository | None = None  # record the run, its fills and events when given
    run_name: str = "paper"
