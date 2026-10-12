"""The engine records price and equity over time, so the History page has something to show."""

from decimal import Decimal as D

from tests.unit.engine.test_engine import ScriptedFeed, make_engine
from tests.unit.engine.test_engine_recovery import PATH, new_engine, run_until_crash, unseen_ticks
from wallexbot.storage.repository import InMemoryRepository

T0 = 1_000_000  # ScriptedFeed's first timestamp (ms); ticks are 60 s apart


def make(prices, interval=300_000, **kw):
    repo = InMemoryRepository()
    engine, _, _ = make_engine(
        ScriptedFeed(prices), repository=repo, cancel_on_shutdown=False, **kw
    )
    engine.config.snapshot_every_ms = interval
    return engine, repo


async def test_a_snapshot_is_taken_at_the_first_price_and_then_at_the_interval():
    engine, repo = make(["100"] * 12)  # 12 quiet prices, one per minute, nothing fills
    await engine.run()

    stamps = [s["ts"] for s in repo.get_snapshots(engine.run_id)]
    # first price, then every 5 minutes (ticks 5 and 10), then the final state at the last price
    assert stamps == [T0, T0 + 5 * 60_000, T0 + 10 * 60_000, T0 + 11 * 60_000]


async def test_a_fill_is_recorded_straight_away_even_inside_the_interval():
    engine, repo = make(["100", "97", "100", "100"])  # the buy at 97.5 fills on the second price
    await engine.run()

    stamps = [s["ts"] for s in repo.get_snapshots(engine.run_id)]
    assert T0 + 60_000 in stamps  # not waiting for the 5 minute mark
    row = next(s for s in repo.get_snapshots(engine.run_id) if s["ts"] == T0 + 60_000)
    assert row["fills"] == 1 and row["price"] == "97"


async def test_a_snapshot_describes_the_run_at_that_moment():
    engine, repo = make(["100", "97", "100.5"], interval=1)
    await engine.run()

    first, second, third = repo.get_snapshots(engine.run_id)[:3]
    assert D(first["equity"]) < D("2000000")  # the entry fee has been paid
    assert first["fills"] == 0 and first["open_orders"] == 8 and first["cycles"] == 0
    assert second["fills"] == 1 and D(second["realized"]) == 0
    assert third["cycles"] == 1 and D(third["realized"]) > 0  # the sell closed the cycle
    assert D(third["fees"]) > D(first["fees"])
    status = engine.status()
    assert repo.get_snapshots(engine.run_id)[-1]["equity"] == str(status.equity)


async def test_a_paused_engine_still_records_the_market_moving():
    holder = {}

    def before(i):
        if i == 1:
            holder["e"].pause()

    engine, repo = make(["100", "99", "98"], interval=1)
    engine.config.price_feed.before_tick = before
    holder["e"] = engine
    await engine.run()
    assert [s["price"] for s in repo.get_snapshots(engine.run_id)][:3] == ["100", "99", "98"]


async def test_no_repository_means_no_recording_and_no_error():
    engine, _, _ = make_engine(ScriptedFeed(["100", "97"]))
    await engine.run()
    assert engine.status().ticks_processed == 2


async def test_a_recovered_run_has_the_same_history_as_one_that_never_crashed():
    reference_repo = InMemoryRepository()
    reference, _ = new_engine(ScriptedFeed(PATH), reference_repo)
    reference.config.snapshot_every_ms = 120_000
    await reference.run()

    disk, run_id = await run_until_crash(PATH, 5, snapshot_every_ms=120_000)
    recovered, _ = new_engine(ScriptedFeed(PATH[5:], offset=5), disk)
    recovered.config.snapshot_every_ms = 120_000
    recovered.restore(run_id)
    recovered.set_catchup(unseen_ticks(disk, run_id, PATH, 5))
    await recovered.run()

    def series(repo, rid):
        return [(s["ts"], s["equity"], s["fills"]) for s in repo.get_snapshots(rid)]

    assert series(disk, run_id) == series(reference_repo, reference.run_id)
