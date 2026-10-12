"""Bot engine configuration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
    app_config: dict[str, Any] | None = (
        None  # saved with checkpoints so a crashed run can be rebuilt
    )
    checkpoint_every_ticks: int = 20  # also saved whenever anything changes (fills, orders...)
    keep_fills: int = 200  # in-memory history caps for runs that never end
    keep_events: int = 500
    on_alert: Callable[[str, str], None] | None = (
        None  # (kind, text): halted / failed / out_of_range
    )
    snapshot_every_ms: int = 30_000  # price/equity history is recorded at most this often
