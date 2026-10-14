"""Optional auto re-centering: after the price has stayed outside the grid for a while, build the
same-width grid around where it is now (paper only; nothing is sold or bought to do it)."""

from decimal import Decimal as D

from tests.unit.engine.test_engine import ScriptedFeed, make_engine
from wallexbot.storage.repository import InMemoryRepository

# grid is 90..110; ticks are one minute apart
OUT = ["150"] * 8


def levels(engine):
    return [lv.price for lv in engine.config.strategy.state.levels]


async def test_it_is_off_unless_asked_for():
    engine, _, _ = make_engine(ScriptedFeed(["100"] + OUT))
    await engine.run()
    assert levels(engine)[0] == D("90") and levels(engine)[-1] == D("110")


async def test_after_the_wait_the_grid_moves_to_the_price_keeping_its_width():
    got = []
    engine, exchange, _ = make_engine(
        ScriptedFeed(["100"] + OUT),
        recenter_after_minutes=5,
        on_alert=lambda k, t: got.append(k),
        cancel_on_shutdown=False,
    )
    await engine.run()
    lows, highs = levels(engine)[0], levels(engine)[-1]
    assert highs - lows == 20 and lows < D("150") < highs  # same width, now around 150
    assert engine.config.strategy.params.lower_price == lows
    open_prices = [o.price for o in exchange.open_orders()]
    assert open_prices and all(lows <= p <= highs for p in open_prices)
    assert any("re-centered" in e for e in engine.status().events)
    assert "recentered" in got and got.count("recentered") == 1


async def test_it_waits_the_full_time_before_moving():
    engine, _, _ = make_engine(ScriptedFeed(["100", "150", "150", "150"]), recenter_after_minutes=5)
    await engine.run()
    assert levels(engine)[0] == D("90")  # only 2 minutes outside


async def test_coming_back_inside_resets_the_wait():
    prices = ["100", "150", "150", "150", "100", "150", "150", "150"]
    engine, _, _ = make_engine(ScriptedFeed(prices), recenter_after_minutes=3)
    await engine.run()
    assert levels(engine)[0] == D("90")  # never 3 minutes in a row outside


async def test_it_does_not_move_again_right_away():
    prices = ["100"] + ["150"] * 6 + ["250"] * 8  # leaves the new range too, but soon after
    engine, _, _ = make_engine(ScriptedFeed(prices), recenter_after_minutes=3)
    await engine.run()
    assert (
        levels(engine)[0] < D("150") < levels(engine)[-1]
    )  # moved once, cooldown holds the second


async def test_profit_and_order_ids_carry_over_to_the_new_grid():
    engine, exchange, _ = make_engine(
        ScriptedFeed(["100", "96", "100", "96", "100"] + OUT), recenter_after_minutes=3
    )
    await engine.run()
    status = engine.status()
    assert status.completed_cycles >= 1  # earned before the move, still counted
    client_ids = [o.client_id for o in exchange._orders.values()]
    assert len(client_ids) == len(set(client_ids))


async def test_the_inventory_already_held_is_not_bought_twice():
    engine, exchange, _ = make_engine(
        ScriptedFeed(["100"] + OUT), recenter_after_minutes=3, cancel_on_shutdown=False
    )
    await engine.run()
    base = exchange.balances()["USDT"]
    sell_qty = sum(o.quantity for o in exchange.open_orders() if o.side.value == "SELL")
    assert base.total >= sell_qty  # funded for its sells...
    assert base.total < sell_qty * D("1.5")  # ...without piling up a second helping


async def test_the_saved_config_follows_the_move_so_a_crash_recovers_the_new_range():
    repo = InMemoryRepository()
    app_config = {
        "strategy": {"grid": {"lower_price": "90", "upper_price": "110", "grid_count": 9}}
    }
    engine, _, _ = make_engine(
        ScriptedFeed(["100"] + OUT),
        recenter_after_minutes=3,
        repository=repo,
        app_config=app_config,
    )
    await engine.run()
    saved = repo.get_checkpoint(engine.run_id)["app_config"]["strategy"]["grid"]
    assert (
        D(saved["lower_price"]) == levels(engine)[0]
        and D(saved["upper_price"]) == levels(engine)[-1]
    )


async def test_a_crash_after_a_re_centering_recovers_into_the_new_range():
    import asyncio
    import copy

    from tests.helpers.wallex_fakes import FakeClient
    from tests.unit.test_recover import T0, Feed, app_config
    from wallexbot.config.schema import validate_config
    from wallexbot.engine import BotEngine, EngineConfig
    from wallexbot.recover import rebuild_engine
    from wallexbot.setup import GridSetup, find_market

    raw = app_config()
    raw["strategy"]["grid"]["recenter_after_minutes"] = 3
    setup = GridSetup.from_config(validate_config(raw), find_market(FakeClient(), "USDTTMN"))
    assert setup.recenter_after_minutes == 3
    repo = InMemoryRepository()
    prices = [264000] + [290000] * 6  # example grid is 255000-275000
    hold = asyncio.Event()
    engine = BotEngine(
        EngineConfig(
            strategy=setup.new_strategy(),
            exchange=setup.new_exchange(),
            price_feed=Feed(prices, T0, hold),
            risk=setup.risk,
            repository=repo,
            app_config=setup.app_config,
            recenter_after_minutes=3,
            cancel_on_shutdown=False,
        )
    )
    task = engine.start()
    for _ in range(500):
        await asyncio.sleep(0)
        if engine.status().ticks_processed == len(prices):
            break
    disk = copy.deepcopy(repo)  # what a crash leaves on disk
    moved = engine.config.strategy.params
    await engine.stop()
    await asyncio.gather(task, return_exceptions=True)
    assert moved.lower_price > D("260000")  # it did move

    now = T0 + 10 * 60_000
    rebuilt, _, _ = rebuild_engine(
        disk, engine.run_id, FakeClient(candles=[]), lambda k, s, c: Feed([], now), now_ms=now
    )
    params = rebuilt.config.strategy.params
    assert (params.lower_price, params.upper_price) == (moved.lower_price, moved.upper_price)
    assert rebuilt.config.recenter_after_minutes == 3
    assert rebuilt.config.strategy.generation == 1  # next re-centering gets fresh order ids
    assert rebuilt.config.exchange.open_orders()  # and the new grid's orders are still there
