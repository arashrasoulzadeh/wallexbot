"""A neutral look back over the recent paper runs: the data for 'is this worth continuing?'."""

import time
from decimal import Decimal as D

from tests.unit.engine.test_engine import ScriptedFeed, make_engine
from wallexbot.analytics.review import review
from wallexbot.storage.repository import InMemoryRepository

PATH = ["100", "97", "100.5", "95", "99", "102", "98", "101"]
NOW = int(time.time() * 1000)


async def two_runs():
    repo = InMemoryRepository()
    for _ in range(2):
        engine, _, _ = make_engine(ScriptedFeed(PATH), repository=repo, cancel_on_shutdown=False)
        await engine.run()
    return repo


async def test_it_lists_each_recent_run_and_adds_up_the_totals():
    repo = await two_runs()
    out = review(repo, now_ms=NOW, days=7)
    assert len(out["runs"]) == 2 and out["totals"]["runs"] == 2
    t = out["totals"]
    assert t["fills"] == sum(r["fills"] for r in out["runs"]) > 0
    assert t["cycles"] == sum(r["cycles"] for r in out["runs"])
    assert t["realized"] == sum((r["realized"] for r in out["runs"]), D(0))
    assert t["fees"] == sum((r["fees"] for r in out["runs"]), D(0))
    assert t["worst_drawdown_pct"] == max(r["max_drawdown_pct"] for r in out["runs"])


async def test_runs_older_than_the_period_are_left_out():
    repo = await two_runs()
    out = review(repo, now_ms=NOW + 30 * 86_400_000, days=7)
    assert out["runs"] == [] and out["totals"]["runs"] == 0
    assert "no_runs" in {n["code"] for n in out["notes"]}


async def test_it_says_when_the_evidence_is_too_thin_to_judge():
    out = review(await two_runs(), now_ms=NOW, days=7)
    codes = {n["code"] for n in out["notes"]}
    assert "short_coverage" in codes  # the runs together cover seconds of price history, not 7 days
    assert "few_cycles" in codes


async def test_how_many_runs_beat_simply_holding_is_counted_not_judged():
    out = review(await two_runs(), now_ms=NOW, days=7)
    t = out["totals"]
    assert 0 <= t["beat_holding"] <= t["runs"]
    assert t["beat_holding"] == sum(
        1 for r in out["runs"] if r["return_pct"] > r["price_change_pct"]
    )


async def test_a_run_that_recorded_nothing_is_listed_but_does_not_break_the_totals():
    repo = await two_runs()
    repo.create_run("empty", {"market": "USDTTMN"})
    out = review(repo, now_ms=NOW, days=7)
    assert len(out["runs"]) == 3 and out["totals"]["runs"] == 3
    assert any(r["fills"] == 0 for r in out["runs"])
