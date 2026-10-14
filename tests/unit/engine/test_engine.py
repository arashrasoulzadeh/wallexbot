"""BotEngine: the async paper-trading loop (scripted feed, simulated exchange, no network)."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from decimal import Decimal as D

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Symbol
from wallexbot.engine import BotEngine, EngineConfig, EngineState
from wallexbot.engine.risk import RiskMonitor
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.storage.repository import InMemoryRepository
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridMode, GridParameters
from wallexbot.wallex.price_feed import PriceTick

SYMBOL = Symbol("USDTTMN")
MARKET = Market(
    symbol=SYMBOL, base="USDT", quote="TMN", price_precision=2, amount_precision=4, is_spot=True
)


class ScriptedFeed:
    """Yields the given prices as ticks; `before_tick(i)` runs just before tick i is delivered."""

    def __init__(
        self,
        prices: list[str],
        before_tick: Callable[[int], None] | None = None,
        then_raise: Exception | None = None,
        then_wait: asyncio.Event | None = None,
        offset: int = 0,
    ):
        self.offset = offset  # numbering of the first tick, for feeds that continue an earlier one
        self.prices = prices
        self.before_tick = before_tick
        self.then_raise = then_raise
        self.then_wait = then_wait

    async def subscribe(self, symbol: Symbol) -> None: ...
    async def unsubscribe(self, symbol: Symbol) -> None: ...

    async def ticks(self) -> AsyncGenerator[PriceTick, None]:
        for i, p in enumerate(self.prices):
            if self.before_tick:
                self.before_tick(i)
            yield PriceTick(
                symbol=SYMBOL,
                price=D(p),
                timestamp=1_000_000 + (i + self.offset) * 60_000,
                source="test",
            )
        if self.then_raise:
            raise self.then_raise
        if self.then_wait:
            await self.then_wait.wait()


def make_engine(
    feed,
    *,
    grid_count=9,
    investment="90000",
    tmn="2000000",
    risk=None,
    cancel_on_shutdown=True,
    repository=None,
    on_alert=None,
    recenter_after_minutes=None,
    app_config=None,
):
    clock = FakeClock()
    exchange = SimulatedExchange(
        market=MARKET,
        fee_schedule_config=FeeSchedule(maker_rate=D("0.001"), taker_rate=D("0.002")),
        min_notional_rule=MinNotionalRule(min_notional=D("10"), min_quantity=D("0.0001")),
        initial_balances={
            "TMN": Balance(free=D(tmn), locked=D(0)),
            "USDT": Balance(free=D(0), locked=D(0)),
        },
        clock=clock,
    )
    params = GridParameters(
        lower_price=D("90"),
        upper_price=D("110"),
        grid_count=grid_count,
        mode=GridMode.ARITHMETIC,
        total_investment=D(investment),
    )
    engine = BotEngine(
        EngineConfig(
            strategy=GridStrategy(MARKET, params),
            exchange=exchange,
            price_feed=feed,
            risk=risk,
            cancel_on_shutdown=cancel_on_shutdown,
            repository=repository,
            on_alert=on_alert,
            recenter_after_minutes=recenter_after_minutes,
            app_config=app_config,
        )
    )
    return engine, exchange, clock


async def test_the_grid_is_built_around_the_first_real_price_not_a_fixed_one():
    engine, exchange, _ = make_engine(ScriptedFeed(["105"]), cancel_on_shutdown=False)
    await engine.run()

    prices = sorted(o.price for o in exchange.open_orders())
    buys = [o.price for o in exchange.open_orders() if o.side.value == "BUY"]
    assert (
        max(buys)
        < D("105")
        < min(o.price for o in exchange.open_orders() if o.side.value == "SELL")
    )
    assert (
        len(prices) == 8
    )  # 105 is not a level, so every level carries an order... minus none skipped


async def test_fills_are_answered_with_counter_orders_and_profit_is_recorded():
    engine, exchange, _ = make_engine(
        ScriptedFeed(["100"] + ["97", "100.5"] * 3), cancel_on_shutdown=False
    )
    await engine.run()

    status = engine.status()
    assert status.state is EngineState.STOPPED
    assert status.completed_cycles == 3 and status.realized_pnl > 0
    assert status.fills == 6
    assert len(exchange.open_orders()) == 8  # ladder intact after every fill


async def test_feed_end_cancels_orders_by_default():
    engine, exchange, _ = make_engine(ScriptedFeed(["100", "99"]))
    await engine.run()
    assert exchange.open_orders() == []
    assert engine.status().state is EngineState.STOPPED


async def test_orders_can_be_left_resting_on_shutdown():
    engine, exchange, _ = make_engine(ScriptedFeed(["100", "99"]), cancel_on_shutdown=False)
    await engine.run()
    assert len(exchange.open_orders()) == 8


async def test_kill_switch_cancels_everything_and_ignores_later_prices():
    holder = {}

    def before_tick(i: int) -> None:
        if i == 3:
            holder["engine"].kill("manual test")

    engine, exchange, _ = make_engine(
        ScriptedFeed(["100", "97", "100.5", "97", "100.5"], before_tick)
    )
    holder["engine"] = engine
    await engine.run()

    status = engine.status()
    assert status.state is EngineState.HALTED and "manual test" in status.halt_reason
    assert exchange.open_orders() == []
    assert status.ticks_processed == 3  # ticks 0-2 only
    assert status.completed_cycles == 1


async def test_risk_breach_halts_the_engine_and_cancels_orders():
    risk = RiskMonitor(max_drawdown=D("0.0001"), daily_loss_limit=None)
    engine, exchange, _ = make_engine(ScriptedFeed(["100", "90.5", "100", "100"]), risk=risk)
    await engine.run()

    status = engine.status()
    assert status.state is EngineState.HALTED
    assert "drawdown" in status.halt_reason
    assert exchange.open_orders() == []
    assert status.ticks_processed < 4


async def test_a_failing_feed_cancels_orders_marks_failed_and_raises():
    engine, exchange, _ = make_engine(
        ScriptedFeed(["100", "99"], then_raise=ConnectionError("feed died"))
    )

    with pytest.raises(ConnectionError, match="feed died"):
        await engine.run()

    assert engine.status().state is EngineState.FAILED
    assert exchange.open_orders() == []
    assert any("feed died" in e for e in engine.status().events)


async def test_stop_while_waiting_for_prices_shuts_down_cleanly():
    waiting = asyncio.Event()
    engine, exchange, _ = make_engine(ScriptedFeed(["100"], then_wait=waiting))
    engine.start()
    for _ in range(50):  # let it consume the first tick and block on the feed
        await asyncio.sleep(0)
        if engine.status().ticks_processed == 1:
            break

    await engine.stop()

    assert engine.status().state is EngineState.STOPPED
    assert exchange.open_orders() == []


async def test_kill_from_outside_while_waiting_for_prices():
    waiting = asyncio.Event()
    engine, exchange, _ = make_engine(ScriptedFeed(["100"], then_wait=waiting))
    task = engine.start()
    for _ in range(50):
        await asyncio.sleep(0)
        if engine.status().ticks_processed == 1:
            break

    engine.kill("operator pressed the button")
    await asyncio.wait_for(task, 1)  # returns normally: a kill is not a crash

    assert engine.status().state is EngineState.HALTED
    assert exchange.open_orders() == []


async def test_orders_over_the_rate_limit_are_placed_as_time_passes():
    holder = {}

    def before_tick(i: int) -> None:
        holder["clock"].advance(11)  # a minute of simulated time per tick would be plenty

    engine, exchange, clock = make_engine(
        ScriptedFeed(["100"] * 4, before_tick),
        grid_count=31,
        investment="310000",
        cancel_on_shutdown=False,
    )
    holder["clock"] = clock
    await engine.run()

    assert len(exchange.open_orders()) == 30
    assert engine.status().deferred_orders == 0
    assert engine.status().rejected_orders == 0


async def test_status_reports_the_live_picture():
    engine, _, _ = make_engine(ScriptedFeed(["100", "97"]), cancel_on_shutdown=False)
    await engine.run()
    s = engine.status()
    assert s.last_price == D("97")
    assert s.equity is not None and s.initial_equity == D("2000000")
    assert s.open_orders == 8 and s.fills == 1 and s.ticks_processed == 2
    assert s.fees_paid > 0


async def test_leaving_the_range_shows_up_in_events():
    engine, _, _ = make_engine(ScriptedFeed(["100", "120"]), cancel_on_shutdown=False)
    await engine.run()
    assert any("left the grid range" in e for e in engine.status().events)


async def test_a_run_is_recorded_in_the_repository():
    repo = InMemoryRepository()
    engine, _, _ = make_engine(
        ScriptedFeed(["100"] + ["97", "100.5"] * 2), repository=repo, cancel_on_shutdown=False
    )
    await engine.run()

    [run] = repo.list_runs()
    assert run["status"] == "stopped" and run["stopped_at"] is not None
    assert len(repo.get_fills(run["id"])) == 4
    assert repo.get_events(run["id"])  # at least the start/stop events


async def test_an_engine_cannot_be_run_twice():
    engine, _, _ = make_engine(ScriptedFeed(["100"]))
    await engine.run()
    with pytest.raises(RuntimeError, match="already"):
        await engine.run()


async def test_pause_freezes_fills_and_resume_continues():
    holder = {}

    def before_tick(i: int) -> None:
        engine = holder["engine"]
        if i == 1:
            engine.pause()
        if i == 3:
            engine.resume()

    engine, exchange, _ = make_engine(
        ScriptedFeed(["100", "97", "96", "94"], before_tick), cancel_on_shutdown=False
    )
    holder["engine"] = engine
    await engine.run()

    status = engine.status()
    # Prices 97 and 96 arrived while paused: nothing filled. After resume, 94 trades through the
    # buys at 97.5 and 95, and both are filled in that single step.
    assert status.fills == 2
    assert status.ticks_processed == 4
    assert [e for e in status.events if e in ("paused", "resumed")] == ["paused", "resumed"]


async def test_nothing_fills_while_paused():
    holder = {}

    def before_tick(i: int) -> None:
        if i == 1:
            holder["engine"].pause()

    engine, _, _ = make_engine(
        ScriptedFeed(["100", "90.5", "91"], before_tick), cancel_on_shutdown=False
    )
    holder["engine"] = engine
    await engine.run()

    status = engine.status()
    assert status.fills == 0  # 90.5 crosses four buy levels, but the engine was paused
    assert status.last_price == D("91")  # still tracks the market while paused


async def test_pause_only_applies_to_a_running_engine_and_kill_works_while_paused():
    engine, exchange, _ = make_engine(ScriptedFeed(["100"]))
    engine.pause()  # idle: ignored
    assert engine.status().state is EngineState.IDLE

    holder = {}

    def before_tick(i: int) -> None:
        if i == 1:
            holder["engine"].pause()
        if i == 2:
            assert holder["engine"].status().state is EngineState.PAUSED
            holder["engine"].kill("while paused")

    engine, exchange, _ = make_engine(ScriptedFeed(["100", "99", "98"], before_tick))
    holder["engine"] = engine
    await engine.run()
    assert engine.status().state is EngineState.HALTED and exchange.open_orders() == []


async def test_run_id_is_available_when_recording():
    repo = InMemoryRepository()
    engine, _, _ = make_engine(ScriptedFeed(["100"]), repository=repo)
    assert engine.run_id == ""
    await engine.run()
    assert engine.run_id == repo.list_runs()[0]["id"]


async def test_snapshot_is_json_ready_and_has_the_live_picture():
    import json

    engine, _, _ = make_engine(ScriptedFeed(["100", "97"]), cancel_on_shutdown=False)
    await engine.run()

    snap = engine.snapshot()
    json.dumps(snap)  # everything is plain JSON types
    assert snap["market"] == "USDTTMN"  # the UI needs it to look up the public price
    assert snap["status"]["state"] == "stopped" and snap["status"]["last_price"] == "97"
    assert len(snap["orders"]) == 8
    assert {"level", "side", "price", "quantity", "filled"} <= set(snap["orders"][0])
    assert snap["fills"][0]["side"] == "BUY" and D(snap["fills"][0]["price"]) == D("97.5")
    assert {b["asset"] for b in snap["balances"]} == {"TMN", "USDT"}
    assert len(snap["grid"]["levels"]) == 9
    assert D(snap["grid"]["lower"]) == 90 and D(snap["grid"]["upper"]) == 110
    assert [lv["price"] for lv in snap["grid"]["levels"]] == sorted(
        (lv["price"] for lv in snap["grid"]["levels"]), key=D
    )
