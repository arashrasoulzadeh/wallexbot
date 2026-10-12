"""RunManager: starts, controls and tracks real paper runs and backtests for the web API."""

import asyncio
import json
from collections.abc import AsyncGenerator
from decimal import Decimal as D
from pathlib import Path

import pytest

from tests.helpers.wallex_fakes import FakeClient
from wallexbot.api.manager import InvalidRunState, RunManager, UnknownRun
from wallexbot.config.schema import Config, load_config
from wallexbot.domain.market import Symbol
from wallexbot.storage.repository import InMemoryRepository
from wallexbot.wallex.price_feed import PriceTick

EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"
SYMBOL = Symbol("USDTTMN")


class HoldingFeed:
    """Delivers the given prices, then idles like a quiet market until closed or failed."""

    def __init__(self, prices: list[int], then_raise: Exception | None = None) -> None:
        self.prices = prices
        self.then_raise = then_raise
        self.closed = asyncio.Event()

    async def subscribe(self, symbol: Symbol) -> None: ...
    async def unsubscribe(self, symbol: Symbol) -> None: ...

    async def ticks(self) -> AsyncGenerator[PriceTick, None]:
        for i, p in enumerate(self.prices):
            yield PriceTick(
                symbol=SYMBOL, price=D(p), timestamp=1_700_000_000_000 + i * 60_000, source="test"
            )
        if self.then_raise:
            raise self.then_raise
        await self.closed.wait()

    async def close(self) -> None:
        self.closed.set()


def config() -> Config:
    return load_config(str(EXAMPLE))


def make_manager(prices=(264000, 262500, 265500), client=None, then_raise=None):
    repo = InMemoryRepository()
    feeds: list[HoldingFeed] = []

    def feed_factory(kind: str, symbol: Symbol, c: object) -> HoldingFeed:
        feed = HoldingFeed(list(prices), then_raise)
        feeds.append(feed)
        return feed

    manager = RunManager(
        repo, client_factory=lambda: client or FakeClient(), feed_factory=feed_factory
    )
    return manager, repo, feeds


async def until(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.01)


async def test_a_paper_run_starts_trades_and_is_recorded():
    manager, repo, _ = make_manager()
    run_id = await manager.start_paper_run(config())

    await until(lambda: manager.snapshot(run_id)["status"]["ticks_processed"] == 3)
    snap = manager.snapshot(run_id)

    assert snap["status"]["state"] == "running"
    assert snap["status"]["fills"] >= 1  # 264000 -> 262500 -> 265500 crosses levels
    assert snap["orders"] and snap["grid"]["levels"] and snap["balances"]
    assert repo.get_run(run_id) is not None  # same id as the recorded run
    await manager.shutdown()


async def test_pause_resume_stop():
    manager, _, _ = make_manager()
    run_id = await manager.start_paper_run(config())
    await until(lambda: manager.snapshot(run_id)["status"]["ticks_processed"] == 3)

    await manager.pause_run(run_id)
    assert manager.snapshot(run_id)["status"]["state"] == "paused"
    await manager.resume_run(run_id)
    assert manager.snapshot(run_id)["status"]["state"] == "running"

    await manager.stop_run(run_id)
    snap = manager.snapshot(run_id)  # still available after the run ended
    assert snap["status"]["state"] == "stopped"
    assert snap["orders"] == []  # resting orders were cancelled


async def test_kill_halts_and_cancels_everything():
    manager, _, _ = make_manager()
    run_id = await manager.start_paper_run(config())
    await until(lambda: manager.snapshot(run_id)["status"]["ticks_processed"] == 3)

    await manager.kill_run(run_id)

    snap = manager.snapshot(run_id)
    assert snap["status"]["state"] == "halted" and snap["orders"] == []
    assert "kill" in snap["status"]["halt_reason"].lower()


async def test_unknown_and_invalid_requests():
    manager, _, _ = make_manager()
    with pytest.raises(UnknownRun):
        await manager.pause_run("nope")
    assert manager.snapshot("nope") is None

    run_id = await manager.start_paper_run(config())
    await until(lambda: manager.snapshot(run_id)["status"]["ticks_processed"] == 3)
    with pytest.raises(InvalidRunState):
        await manager.resume_run(run_id)  # not paused
    await manager.stop_run(run_id)
    with pytest.raises(InvalidRunState):
        await manager.pause_run(run_id)  # already finished
    with pytest.raises(InvalidRunState):
        await manager.kill_run(run_id)


async def test_an_unknown_market_is_refused():
    manager, _, _ = make_manager(client=FakeClient(markets=[]))
    with pytest.raises(ValueError, match="USDTTMN"):
        await manager.start_paper_run(config())


async def test_a_failing_feed_marks_the_run_failed_without_crashing_the_manager():
    manager, _, _ = make_manager(then_raise=ConnectionError("feed died"))
    run_id = await manager.start_paper_run(config())

    await until(lambda: manager.snapshot(run_id)["status"]["state"] == "failed")

    assert any("feed died" in e for e in manager.snapshot(run_id)["status"]["events"])
    assert [r["id"] for r in manager.live_runs()] == [run_id]


async def test_the_feed_is_closed_when_a_run_ends():
    manager, _, feeds = make_manager()
    run_id = await manager.start_paper_run(config())
    await until(lambda: manager.snapshot(run_id)["status"]["ticks_processed"] == 3)
    await manager.stop_run(run_id)
    await until(lambda: feeds[0].closed.is_set())


async def test_shutdown_stops_every_running_engine():
    manager, _, _ = make_manager()
    a = await manager.start_paper_run(config())
    b = await manager.start_paper_run(config())
    await until(lambda: all(manager.snapshot(r)["status"]["ticks_processed"] == 3 for r in (a, b)))

    await manager.shutdown()

    assert all(manager.snapshot(r)["status"]["state"] == "stopped" for r in (a, b))


async def test_live_runs_lists_state_for_the_dashboard():
    manager, _, _ = make_manager()
    run_id = await manager.start_paper_run(config())
    await until(lambda: manager.snapshot(run_id)["status"]["ticks_processed"] == 3)
    [row] = manager.live_runs()
    assert row["id"] == run_id and row["state"] == "running" and row["market"] == "USDTTMN"
    json.dumps(row)
    await manager.shutdown()


async def test_a_backtest_runs_in_the_background_and_reports_metrics():
    manager, _, _ = make_manager()
    bt_id = await manager.start_backtest(config(), 1_700_000_000, 1_700_200_000)

    await until(lambda: manager.backtest(bt_id)["status"] != "running", timeout=5)
    result = manager.backtest(bt_id)

    assert result["status"] == "done", result
    assert result["metrics"]["completed_cycles"] > 0
    assert {"total_return_pct", "max_drawdown", "fees_paid", "buy_and_hold_return"} <= set(
        result["metrics"]
    )
    assert 0 < len(result["equity_curve"]) <= 200
    json.dumps(result)


async def test_a_backtest_failure_is_reported_not_raised():
    manager, _, _ = make_manager(client=FakeClient(candles=[]))
    bt_id = await manager.start_backtest(config(), 1_700_000_000, 1_700_200_000)

    await until(lambda: manager.backtest(bt_id)["status"] != "running", timeout=5)

    result = manager.backtest(bt_id)
    assert result["status"] == "failed" and "no candle data" in result["error"].lower()
    assert manager.backtest("nope") is None
