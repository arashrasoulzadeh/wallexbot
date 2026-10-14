"""Rebuild a crashed paper run so it can continue where it stopped."""

import time
from collections.abc import Callable
from typing import Any

from wallexbot.config.schema import validate_config
from wallexbot.engine import BotEngine, EngineConfig
from wallexbot.engine.recovery import (
    MAX_CATCHUP_HOURS,
    RecoveryError,
    catchup_ticks,
    load_checkpoint,
    stored_config,
)
from wallexbot.setup import GridSetup, find_market
from wallexbot.storage.repository import Repository
from wallexbot.wallex.client import WallexRestClient


def rebuild_engine(
    repo: Repository,
    run_id: str,
    client: WallexRestClient,
    feed_factory: Callable[[str, Any, Any], Any],
    feed_kind: str = "ws",
    max_catchup_hours: float = MAX_CATCHUP_HOURS,
    now_ms: int | None = None,
) -> tuple[BotEngine, Any, str]:
    """An engine restored from `run_id`'s checkpoint, with the downtime queued for replay.

    Returns (engine, price feed, note describing the replay). Raises RecoveryError if the run
    cannot be recovered. Nothing runs until the caller starts the engine.
    """
    checkpoint = load_checkpoint(repo, run_id)  # fails early with a clear reason
    raw = stored_config(repo, run_id)
    config = validate_config(raw)
    symbol = str(config.market.symbol)
    info = find_market(client, symbol)
    if info is None:
        raise RecoveryError(f"market {symbol} not found (is it a spot market?)")
    setup = GridSetup.from_config(config, info)

    price_feed = feed_factory(feed_kind, setup.market.symbol, client)
    engine = BotEngine(
        EngineConfig(
            strategy=setup.new_strategy(),
            exchange=setup.new_exchange(),
            price_feed=price_feed,
            risk=setup.risk,
            repository=repo,
            run_name=f"paper-{symbol}",
            app_config=raw,
            recenter_after_minutes=setup.recenter_after_minutes,
        )
    )
    engine.restore(run_id)

    last_ms = checkpoint["engine"]["last_tick_ts"]
    ticks, note = catchup_ticks(
        client, symbol, last_ms, now_ms or int(time.time() * 1000), max_catchup_hours
    )
    engine.set_catchup(ticks)
    return engine, price_feed, note
