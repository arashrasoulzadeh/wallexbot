"""Crash recovery of the paper engine: checkpoints, restore, and replaying the downtime."""

import asyncio
import copy
from decimal import Decimal as D

import pytest

from tests.unit.engine.test_engine import MARKET, ScriptedFeed, make_engine
from wallexbot.engine import BotEngine, EngineState
from wallexbot.engine.recovery import RecoveryError, recoverable_runs, stored_config
from wallexbot.storage.repository import InMemoryRepository
from wallexbot.wallex.price_feed import PriceTick

APP_CONFIG = {"market": {"symbol": "USDTTMN"}, "note": "stand-in for the real config"}
PATH = ["100", "97", "100.5", "95", "99", "102", "98", "101", "96", "100", "94", "103"]


def view(engine: BotEngine) -> dict:
    """What must be identical between an interrupted and an uninterrupted run."""
    snap = engine.snapshot()
    s = snap["status"]
    return {
        "orders": [
            (o["level"], o["side"], o["price"], o["quantity"], o["filled"]) for o in snap["orders"]
        ],
        "balances": snap["balances"],
        "levels": snap["grid"]["levels"],
        "cycles": s["completed_cycles"],
        "realized": s["realized_pnl"],
        "fills": s["fills"],
        "fees": s["fees_paid"],
        "ticks": s["ticks_processed"],
        "equity": s["equity"],
        "initial": s["initial_equity"],
        "price": s["last_price"],
    }


def new_engine(feed, repo, **kw):
    engine, exchange, clock = make_engine(feed, repository=repo, cancel_on_shutdown=False, **kw)
    engine.config.app_config = APP_CONFIG
    return engine, exchange


async def run_until_crash(
    prices: list[str], crash_after: int, snapshot_every_ms: int | None = None
):
    """Run `crash_after` ticks, then 'crash': keep a copy of the database as it is right then."""
    repo = InMemoryRepository()
    wait = asyncio.Event()
    engine, _ = new_engine(ScriptedFeed(prices[:crash_after], then_wait=wait), repo)
    if snapshot_every_ms is not None:
        engine.config.snapshot_every_ms = snapshot_every_ms
    task = engine.start()
    for _ in range(500):
        await asyncio.sleep(0)
        if engine.status().ticks_processed == crash_after:
            break
    assert engine.status().ticks_processed == crash_after
    disk = copy.deepcopy(repo)  # what a crashed process leaves behind
    await engine.stop()
    await asyncio.gather(task, return_exceptions=True)
    return disk, engine.run_id


def unseen_ticks(disk, run_id, prices: list[str], crashed_after: int) -> list[PriceTick]:
    """Prices the last checkpoint had not seen (it is saved when something changes, or every few
    prices); in production the downtime replay supplies them, starting from the checkpoint."""
    seen = disk.get_checkpoint(run_id)["engine"]["ticks"]
    return [
        PriceTick(
            symbol=MARKET.symbol,
            price=D(prices[i]),
            timestamp=1_000_000 + i * 60_000,
            source="replay",
        )
        for i in range(seen, crashed_after)
    ]


async def test_checkpoints_are_written_while_running():
    repo = InMemoryRepository()
    engine, _ = new_engine(ScriptedFeed(PATH[:5]), repo)
    await engine.run()

    cp = repo.get_checkpoint(engine.run_id)
    assert cp["version"] == 1 and cp["app_config"] == APP_CONFIG
    assert cp["engine"]["ticks"] == 5 and cp["engine"]["last_tick_ts"] == 1_000_000 + 4 * 60_000
    assert cp["session"]["strategy"]["started"] is True


@pytest.mark.parametrize("crash_after", [1, 2, 3, 5, 8, 11])
async def test_a_recovered_run_finishes_exactly_like_one_that_never_crashed(crash_after):
    reference, _ = new_engine(ScriptedFeed(PATH), InMemoryRepository())
    await reference.run()

    disk, run_id = await run_until_crash(PATH, crash_after)
    assert disk.get_run(run_id)["status"] == "running"  # a crash never got to say "stopped"

    recovered, _ = new_engine(ScriptedFeed(PATH[crash_after:], offset=crash_after), disk)
    recovered.restore(run_id)
    recovered.set_catchup(unseen_ticks(disk, run_id, PATH, crash_after))
    await recovered.run()

    assert view(recovered) == view(reference)
    assert recovered.run_id == run_id  # the same run continues, it is not a new one


async def test_recovery_continues_the_same_run_record():
    disk, run_id = await run_until_crash(PATH, 4)
    recovered, _ = new_engine(ScriptedFeed(PATH[4:], offset=4), disk)
    recovered.restore(run_id)
    await recovered.run()

    assert len(disk.list_runs()) == 1
    assert disk.get_run(run_id)["status"] == "stopped"
    messages = [e["message"] for e in disk.get_events(run_id)]
    assert any("recovered" in m for m in messages)
    assert len(disk.get_fills(run_id)) >= 1


async def test_a_paused_run_comes_back_paused():
    repo = InMemoryRepository()
    wait = asyncio.Event()
    engine, _ = new_engine(ScriptedFeed(PATH[:3], then_wait=wait), repo)
    task = engine.start()
    for _ in range(500):
        await asyncio.sleep(0)
        if engine.status().ticks_processed == 3:
            break
    engine.pause()
    disk = copy.deepcopy(repo)
    await engine.stop()
    await asyncio.gather(task, return_exceptions=True)

    recovered, _ = new_engine(ScriptedFeed(PATH[3:6], offset=3), disk)
    recovered.restore(engine.run_id)
    assert recovered.status().state is EngineState.PAUSED


async def test_the_downtime_is_replayed_so_orders_that_would_have_filled_do_fill():
    disk, run_id = await run_until_crash(["100", "100.2"], 2)
    # while the bot was down, price fell through two buy levels and came back
    downtime = [
        PriceTick(
            symbol=MARKET.symbol,
            price=D(p),
            timestamp=1_000_000 + (2 + i) * 60_000,
            source="replay",
        )
        for i, p in enumerate(["96.5", "94", "99"])
    ]
    seen = disk.get_checkpoint(run_id)["engine"]["ticks"]  # prices the checkpoint had counted
    recovered, exchange = new_engine(ScriptedFeed(["99.5"], offset=5), disk)
    recovered.restore(run_id)
    recovered.set_catchup(downtime)
    await recovered.run()

    status = recovered.status()
    assert status.fills >= 3  # the buys at 97.5, 95 (and what followed) happened during the gap
    assert status.ticks_processed == seen + 3 + 1
    assert any("replayed 3 price points" in e for e in status.events)


async def test_downtime_prices_older_than_the_checkpoint_are_ignored():
    disk, run_id = await run_until_crash(["100", "97"], 2)
    stale = [PriceTick(symbol=MARKET.symbol, price=D("50"), timestamp=1_000_000, source="replay")]
    recovered, _ = new_engine(ScriptedFeed([], offset=2), disk)
    recovered.restore(run_id)
    recovered.set_catchup(stale)
    await recovered.run()
    assert recovered.status().ticks_processed == 2  # the stale tick was not applied


async def test_the_exchange_clock_is_restored_after_replaying_the_downtime():
    disk, run_id = await run_until_crash(["100", "99"], 2)
    recovered, exchange = new_engine(ScriptedFeed([], offset=5), disk)
    original_clock = exchange.clock
    recovered.restore(run_id)
    recovered.set_catchup(
        [
            PriceTick(
                symbol=MARKET.symbol,
                price=D("98"),
                timestamp=1_000_000 + 3 * 60_000,
                source="replay",
            )
        ]
    )
    await recovered.run()
    assert exchange.clock is original_clock


async def test_restore_refuses_runs_that_cannot_be_recovered():
    repo = InMemoryRepository()
    engine, _ = new_engine(ScriptedFeed(PATH[:3]), repo)
    await engine.run()  # finished cleanly: status "stopped"
    fresh, _ = new_engine(ScriptedFeed([]), repo)
    with pytest.raises(RecoveryError, match="stopped"):
        fresh.restore(engine.run_id)

    with pytest.raises(RecoveryError, match="not found"):
        fresh.restore("run_does_not_exist")

    other = InMemoryRepository()
    run_id = other.create_run("paper", {"market": "USDTTMN"})  # a run with no checkpoint
    nocp, _ = new_engine(ScriptedFeed([]), other)
    with pytest.raises(RecoveryError, match="checkpoint"):
        nocp.restore(run_id)

    disk, crashed = await run_until_crash(PATH, 3)
    cp = disk.get_checkpoint(crashed)
    cp["version"] = 99
    disk.save_checkpoint(crashed, cp)
    bad, _ = new_engine(ScriptedFeed([]), disk)
    with pytest.raises(RecoveryError, match="version"):
        bad.restore(crashed)


async def test_restore_needs_a_repository_and_an_idle_engine():
    engine, _, _ = make_engine(ScriptedFeed([]))  # no repository
    with pytest.raises(RecoveryError, match="repository"):
        engine.restore("anything")

    disk, run_id = await run_until_crash(PATH, 3)
    busy, _ = new_engine(ScriptedFeed(PATH[3:], offset=3), disk)
    busy.restore(run_id)
    await busy.run()
    with pytest.raises(RecoveryError, match="already"):
        busy.restore(run_id)


async def test_recoverable_runs_are_the_ones_a_crash_left_unfinished():
    disk, crashed = await run_until_crash(PATH, 3)
    done, _ = new_engine(ScriptedFeed(PATH[:2]), disk)
    await done.run()  # a second, cleanly finished run in the same database

    found = recoverable_runs(disk, live_ids=set())
    assert [r["id"] for r in found] == [crashed]
    assert recoverable_runs(disk, live_ids={crashed}) == []  # still running in this process
    assert stored_config(disk, crashed) == APP_CONFIG
