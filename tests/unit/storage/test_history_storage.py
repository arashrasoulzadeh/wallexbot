"""What the History page reads: fills with their side, and price/equity snapshots over time."""

import pytest

from tests.unit.engine.test_engine import ScriptedFeed, make_engine
from wallexbot.storage.repository import InMemoryRepository, SQLiteRepository

PATH = ["100", "97", "100.5", "95", "99", "102", "98", "101"]


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        return InMemoryRepository()
    return SQLiteRepository(str(tmp_path / "h.db"))


def snap(ts: int, equity: str = "1000", price: str = "100") -> dict:
    return {
        "ts": ts,
        "price": price,
        "equity": equity,
        "realized": "0",
        "fees": "0",
        "open_orders": 6,
        "fills": 0,
        "cycles": 0,
    }


def test_snapshots_come_back_oldest_first(repo):
    run = repo.create_run("r", {"market": "USDTTMN"})
    for ts in (3000, 1000, 2000):
        repo.save_snapshot(run, snap(ts))
    assert [s["ts"] for s in repo.get_snapshots(run)] == [1000, 2000, 3000]


def test_snapshots_can_be_limited_to_a_time_range(repo):
    run = repo.create_run("r", {"market": "USDTTMN"})
    for ts in range(1000, 6000, 1000):
        repo.save_snapshot(run, snap(ts))
    assert [s["ts"] for s in repo.get_snapshots(run, since=2000, until=4000)] == [2000, 3000, 4000]
    assert [s["ts"] for s in repo.get_snapshots(run, since=4500)] == [5000]
    assert [s["ts"] for s in repo.get_snapshots(run, until=1500)] == [1000]


def test_a_snapshot_at_the_same_time_replaces_the_old_one(repo):
    run = repo.create_run("r", {"market": "USDTTMN"})
    repo.save_snapshot(run, snap(1000, equity="1000"))
    repo.save_snapshot(run, snap(1000, equity="1010"))  # e.g. recomputed during a recovery replay
    [only] = repo.get_snapshots(run)
    assert only["equity"] == "1010"


def test_snapshots_are_kept_per_run(repo):
    a, b = repo.create_run("a", {"market": "X"}), repo.create_run("b", {"market": "Y"})
    repo.save_snapshot(a, snap(1000))
    assert repo.get_snapshots(b) == []


def test_snapshot_values_round_trip_exactly(repo):
    run = repo.create_run("r", {"market": "USDTTMN"})
    repo.save_snapshot(run, {**snap(1000), "equity": "1998356.24140000", "price": "261745"})
    [got] = repo.get_snapshots(run)
    assert got["equity"] == "1998356.24140000" and got["price"] == "261745"
    assert got["open_orders"] == 6 and got["cycles"] == 0


async def test_fills_carry_their_side_and_runs_do_not_overwrite_each_other(repo):
    """Regression: every run numbers its orders ord_0, ord_1...; the orders table's primary key was
    global, so a second run replaced the first run's orders."""
    first, _, _ = make_engine(ScriptedFeed(PATH), repository=repo, cancel_on_shutdown=False)
    await first.run()
    second, _, _ = make_engine(ScriptedFeed(PATH), repository=repo, cancel_on_shutdown=False)
    await second.run()

    for engine in (first, second):
        fills = repo.get_fills(engine.run_id)
        assert len(fills) == engine.status().fills > 0
        assert {f["side"] for f in fills} <= {"BUY", "SELL"}
        assert all(f["side"] for f in fills)
    sides_one = [f["side"] for f in repo.get_fills(first.run_id)]
    sides_two = [f["side"] for f in repo.get_fills(second.run_id)]
    assert sides_one == sides_two  # same prices, same trades: the runs are independent copies
