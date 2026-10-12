"""The engine tells the outside world when something needs a human (halt, failure, price left the grid)."""

import asyncio

from tests.unit.engine.test_engine import ScriptedFeed, make_engine


def collect():
    got: list[tuple[str, str]] = []
    return got, lambda kind, text: got.append((kind, text))


async def test_a_kill_switch_halt_raises_an_alert_with_the_reason():
    got, hook = collect()
    holder = {}

    def kill_at_third(i):
        if i == 2:
            holder["engine"].kill("manual test")

    engine, _, _ = make_engine(
        ScriptedFeed(["100", "100", "100", "100"], before_tick=kill_at_third), on_alert=hook
    )
    holder["engine"] = engine
    await engine.run()
    assert [k for k, _ in got] == ["halted"] and "manual test" in got[0][1]


async def test_leaving_the_grid_range_alerts_once_not_on_every_price():
    got, hook = collect()
    engine, _, _ = make_engine(ScriptedFeed(["100", "150", "151", "152"]), on_alert=hook)
    await engine.run()
    assert [k for k, _ in got] == ["out_of_range"]


async def test_an_engine_failure_raises_an_alert():
    got, hook = collect()
    engine, _, _ = make_engine(
        ScriptedFeed(["100"], then_raise=RuntimeError("boom")), on_alert=hook
    )
    try:
        await engine.run()
    except RuntimeError:
        pass
    assert "failed" in [k for k, _ in got]


async def test_a_broken_alert_hook_never_stops_the_bot():
    def bad(kind, text):
        raise OSError("telegram is down")

    engine, _, _ = make_engine(ScriptedFeed(["100", "150", "100"]), on_alert=bad)
    await asyncio.wait_for(engine.run(), 5)
    assert engine.status().ticks_processed == 3
