"""rebuild_engine: a crashed run, its stored config, and the downtime's public prices."""

import asyncio
import copy
from decimal import Decimal as D
from pathlib import Path

import pytest

from tests.helpers.wallex_fakes import FakeClient, swinging_candles
from wallexbot.config.schema import load_config, validate_config
from wallexbot.domain.market import Symbol
from wallexbot.engine import BotEngine, EngineConfig, EngineState
from wallexbot.engine.recovery import RecoveryError
from wallexbot.recover import rebuild_engine
from wallexbot.setup import GridSetup, find_market
from wallexbot.storage.repository import InMemoryRepository
from wallexbot.wallex.models import Candle
from wallexbot.wallex.price_feed import PriceTick

EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "grid.example.yaml"
SYMBOL = Symbol("USDTTMN")
T0 = 1_700_000_000_000  # ms


class Feed:
    def __init__(self, prices: list[int], start_ms: int, hold: asyncio.Event | None = None):
        self.prices, self.start_ms, self.hold = prices, start_ms, hold

    async def subscribe(self, symbol: Symbol) -> None: ...
    async def unsubscribe(self, symbol: Symbol) -> None: ...

    async def ticks(self):
        for i, p in enumerate(self.prices):
            yield PriceTick(
                symbol=SYMBOL, price=D(p), timestamp=self.start_ms + i * 60_000, source="test"
            )
        if self.hold:
            await self.hold.wait()

    async def close(self) -> None: ...


def app_config() -> dict:
    return load_config(str(EXAMPLE)).model_dump(mode="json", by_alias=True)


async def crashed_repo(prices=(264000, 262500, 265500, 262000)) -> tuple[InMemoryRepository, str]:
    """A repository as a crash leaves it: run still 'running', checkpoint saved."""
    repo = InMemoryRepository()
    config = validate_config(app_config())
    setup = GridSetup.from_config(config, find_market(FakeClient(), "USDTTMN"))
    hold = asyncio.Event()
    engine = BotEngine(
        EngineConfig(
            strategy=setup.new_strategy(),
            exchange=setup.new_exchange(),
            price_feed=Feed(list(prices), T0, hold),
            risk=setup.risk,
            repository=repo,
            app_config=app_config(),
            cancel_on_shutdown=False,
        )
    )
    task = engine.start()
    for _ in range(500):
        await asyncio.sleep(0)
        if engine.status().ticks_processed == len(prices):
            break
    disk = copy.deepcopy(repo)
    await engine.stop()
    await asyncio.gather(task, return_exceptions=True)
    return disk, engine.run_id


def test_the_config_round_trips_through_its_json_form():
    original = load_config(str(EXAMPLE))
    again = validate_config(app_config())
    assert again.model_dump(mode="json", by_alias=True) == original.model_dump(
        mode="json", by_alias=True
    )
    assert again.logging.json_output is True  # the "json" key survives the round trip


async def test_a_crashed_run_is_rebuilt_from_its_stored_config():
    repo, run_id = await crashed_repo()
    now = T0 + 10 * 60_000
    fake = FakeClient(candles=[])  # nothing happened while it was down

    engine, feed, note = rebuild_engine(
        repo, run_id, fake, lambda kind, sym, c: Feed([], now), now_ms=now
    )

    assert engine.run_id == run_id
    assert engine.status().state is EngineState.RUNNING
    assert engine.status().ticks_processed >= 1 and engine.session.strategy.state is not None
    assert "replaying 0" in note


async def test_the_downtime_is_fetched_from_the_public_candles_and_replayed():
    repo, run_id = await crashed_repo()
    last_ms = repo.get_checkpoint(run_id)["engine"]["last_tick_ts"]
    candles = [
        Candle(
            symbol=SYMBOL,
            resolution="1",
            open_time=(last_ms // 1000) + 60 * (i + 1),
            open=D(264000),
            high=D(264500),
            low=D(261500),
            close=D(264200),
            volume=D(10),
        )
        for i in range(5)
    ]
    now = last_ms + 6 * 60_000
    engine, _, note = rebuild_engine(
        repo, run_id, FakeClient(candles=candles), lambda kind, sym, c: Feed([], now), now_ms=now
    )
    await engine.run()

    assert "replaying 20 public price points" in note  # 5 candles x 4 points
    assert any("replayed 20 price points" in e for e in engine.status().events)


async def test_a_downtime_longer_than_the_limit_is_not_replayed():
    repo, run_id = await crashed_repo()
    last_ms = repo.get_checkpoint(run_id)["engine"]["last_tick_ts"]
    fake = FakeClient(candles=swinging_candles(5))
    now = last_ms + 30 * 3_600_000  # thirty hours later

    engine, _, note = rebuild_engine(
        repo, run_id, fake, lambda k, s, c: Feed([], now), now_ms=now, max_catchup_hours=24
    )

    assert "longer than 24 h" in note
    assert fake.requests == []  # the candles were not even requested


async def test_unrecoverable_cases_raise_recovery_error():
    repo, run_id = await crashed_repo()
    feed_factory = lambda k, s, c: Feed([], T0)  # noqa: E731

    with pytest.raises(RecoveryError, match="not found"):
        rebuild_engine(repo, "nope", FakeClient(), feed_factory)
    with pytest.raises(RecoveryError, match="USDTTMN"):
        rebuild_engine(repo, run_id, FakeClient(markets=[]), feed_factory)

    repo.update_run_status(run_id, "stopped", 1)
    with pytest.raises(RecoveryError, match="stopped"):
        rebuild_engine(repo, run_id, FakeClient(), feed_factory)
