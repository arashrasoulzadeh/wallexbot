"""Crash recovery helpers: find interrupted runs, load their saved state, rebuild the downtime.

A paper run saves a checkpoint (the full state of its simulated exchange, grid and bookkeeping)
every time something changes. If the process dies, the run is left with status "running" and a
checkpoint. Recovering it restores that state and replays the public prices of the downtime, so
orders that would have filled while the bot was off do fill, at their own limit prices, just as
resting orders would on a real exchange.
"""

from typing import Any, Protocol

from wallexbot.analytics.replay import candles_to_ticks
from wallexbot.storage.repository import Repository
from wallexbot.wallex.models import Candle
from wallexbot.wallex.price_feed import PriceTick

CHECKPOINT_VERSION = 1
CATCHUP_RESOLUTION = "1"  # one-minute candles
MAX_CATCHUP_HOURS = 24


class RecoveryError(RuntimeError):
    """A run cannot be recovered; the message says why."""


def load_checkpoint(repo: Repository, run_id: str) -> dict[str, Any]:
    """The run's checkpoint, after checking that the run is one that can be recovered."""
    run = repo.get_run(run_id)
    if not run:
        raise RecoveryError(f"run {run_id} not found")
    status = run.get("status")
    if status != "running":
        raise RecoveryError(
            f"run {run_id} is {status}: only a run that was interrupted (status running) "
            "can be recovered"
        )
    checkpoint = repo.get_checkpoint(run_id)
    if checkpoint is None:
        raise RecoveryError(f"run {run_id} has no checkpoint to recover from")
    if checkpoint.get("version") != CHECKPOINT_VERSION:
        raise RecoveryError(f"unsupported checkpoint version {checkpoint.get('version')!r}")
    return checkpoint


def stored_config(repo: Repository, run_id: str) -> dict[str, Any]:
    """The configuration the run was started with (needed to rebuild it)."""
    checkpoint = repo.get_checkpoint(run_id)
    config = checkpoint.get("app_config") if checkpoint else None
    if not config:
        raise RecoveryError(f"run {run_id} has no stored configuration")
    stored: dict[str, Any] = config
    return stored


def recoverable_runs(repo: Repository, live_ids: set[str]) -> list[dict[str, Any]]:
    """Runs a crash left unfinished: status running, a checkpoint, not live in this process."""
    found = []
    for run in repo.list_runs():
        run_id = run["id"]
        if run.get("status") != "running" or run_id in live_ids:
            continue
        checkpoint = repo.get_checkpoint(run_id)
        if checkpoint is None:
            continue
        found.append(
            {
                "id": run_id,
                "market": run.get("market") or (run.get("config") or {}).get("market", ""),
                "started_at": run.get("started_at", 0),
                "saved_at": checkpoint.get("saved_at", 0),
            }
        )
    return found


class _CandleSource(Protocol):
    def get_candles(
        self, symbol: str, resolution: str, from_ts: int, to_ts: int
    ) -> list[Candle]: ...


def catchup_ticks(
    client: _CandleSource,
    symbol: str,
    since_ms: int,
    until_ms: int,
    max_hours: float = MAX_CATCHUP_HOURS,
) -> tuple[list[PriceTick], str]:
    """Public one-minute prices for the downtime, and a note saying what was (not) replayed.

    Downtime longer than `max_hours` is not replayed (the first live price is used instead): the
    path in between is unknowable at that resolution and the request would be huge.
    """
    gap_hours = (until_ms - since_ms) / 3_600_000
    if gap_hours <= 0:
        return [], "no downtime to replay"
    if gap_hours > max_hours:
        return [], (
            f"downtime of {gap_hours:.1f} h is longer than {max_hours:g} h: "
            "prices in between are not replayed"
        )
    candles = client.get_candles(symbol, CATCHUP_RESOLUTION, since_ms // 1000, until_ms // 1000)
    ticks = [t for t in candles_to_ticks(candles) if since_ms < t.timestamp <= until_ms]
    return ticks, f"replaying {len(ticks)} public price points from {gap_hours:.1f} h of downtime"
