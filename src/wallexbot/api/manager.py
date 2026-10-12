"""RunManager: starts, controls and tracks paper runs and backtests for the web API.

A paper run is a real `BotEngine` on a live price feed with simulated orders (no API key); a
backtest replays public candles in a background thread. Both are tracked in memory by id; finished
runs keep their last snapshot so the UI can still show them.
"""

import asyncio
import dataclasses
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from wallexbot.analytics.backtest import Backtester, BacktestResult
from wallexbot.analytics.market_status import build_market_status, jsonable
from wallexbot.analytics.replay import candles_to_ticks
from wallexbot.config.schema import Config
from wallexbot.engine import BotEngine, EngineConfig, EngineState
from wallexbot.engine.recovery import recoverable_runs
from wallexbot.recover import rebuild_engine
from wallexbot.setup import GridSetup, find_market
from wallexbot.storage.repository import Repository
from wallexbot.wallex.client import WallexRestClient
from wallexbot.wallex.live_feed import make_price_feed
from wallexbot.wallex.price_feed import PriceFeedReplay

MAX_CURVE_POINTS = 200


class UnknownRun(KeyError):
    """No run with this id."""


class InvalidRunState(RuntimeError):
    """The run exists but is not in a state that allows the request."""


@dataclass
class _ActiveRun:
    engine: BotEngine
    task: "asyncio.Task[None]"
    feed: Any
    symbol: str
    started_at: int
    final: dict[str, Any] | None = None
    cleanup: "asyncio.Task[None] | None" = field(default=None, repr=False)


class RunManager:
    """Owns every paper run and backtest started through the API."""

    def __init__(
        self,
        repo: Repository,
        client_factory: Callable[[], WallexRestClient] = WallexRestClient,
        feed_factory: Callable[[str, Any, Any], Any] = make_price_feed,
    ) -> None:
        self.repo = repo
        self._client_factory = client_factory
        self._feed_factory = feed_factory
        self._runs: dict[str, _ActiveRun] = {}
        self._backtests: dict[str, dict[str, Any]] = {}
        self._backtest_tasks: set[asyncio.Task[None]] = set()

    # --- paper runs -----------------------------------------------------------------

    async def start_paper_run(self, config: Config, feed: str = "ws") -> str:
        """Start a paper run on live prices; returns its run id."""
        client = self._client_factory()
        symbol = str(config.market.symbol)
        info = await asyncio.to_thread(find_market, client, symbol)
        if info is None:
            raise ValueError(f"market {symbol} not found (is it a spot market?)")
        setup = GridSetup.from_config(config, info)

        price_feed = self._feed_factory(feed, setup.market.symbol, client)
        engine = BotEngine(
            EngineConfig(
                strategy=setup.new_strategy(),
                exchange=setup.new_exchange(),
                price_feed=price_feed,
                risk=setup.risk,
                repository=self.repo,
                run_name=f"paper-{symbol}",
                app_config=config.model_dump(mode="json", by_alias=True),
            )
        )
        return await self._launch(engine, price_feed, symbol)

    async def _launch(self, engine: BotEngine, price_feed: Any, symbol: str) -> str:
        """Start an engine in the background and track it under its run id."""
        task = engine.start()
        while not engine.run_id and not task.done():
            await asyncio.sleep(0)
        if not engine.run_id:  # the task ended before it could even register
            await asyncio.gather(task, return_exceptions=False)
            raise RuntimeError("the engine stopped before it started")

        run = _ActiveRun(engine, task, price_feed, symbol, int(time.time() * 1000))
        run_id = engine.run_id
        self._runs[run_id] = run
        task.add_done_callback(lambda t: self._on_done(run_id, t))
        return run_id

    async def recover_run(self, run_id: str, feed: str = "ws") -> str:
        """Continue a run that a crash left unfinished; it keeps its id. Raises RecoveryError."""
        live = self._runs.get(run_id)
        if live is not None and live.engine.state in (EngineState.RUNNING, EngineState.PAUSED):
            raise InvalidRunState("run is already live in this process")
        client = self._client_factory()
        engine, price_feed, _note = await asyncio.to_thread(
            rebuild_engine, self.repo, run_id, client, self._feed_factory, feed
        )
        symbol = str(engine.config.exchange.market_info().symbol)
        return await self._launch(engine, price_feed, symbol)

    async def latest_price(self, symbol: str) -> dict[str, Any] | None:
        """The most recent public trade of a market (no run needed), or None if there is none."""
        client = self._client_factory()
        trades = await asyncio.to_thread(client.get_latest_trades, symbol, 1)
        if not trades:
            return None
        return {"symbol": symbol, "price": str(trades[0].price), "timestamp": trades[0].timestamp}

    async def market_status(self, config: Config) -> dict[str, Any]:
        """Neutral market facts for the configured grid (public data only)."""
        return await asyncio.to_thread(self._market_status_sync, config)

    def _market_status_sync(self, config: Config) -> dict[str, Any]:
        client = self._client_factory()
        symbol = str(config.market.symbol)
        info = find_market(client, symbol)
        if info is None:
            raise ValueError(f"market {symbol} not found (is it a spot market?)")
        setup = GridSetup.from_config(config, info)
        trades = client.get_latest_trades(symbol, 1)
        if not trades:
            raise ValueError("no recent trades on this market")
        now_ms = int(time.time() * 1000)
        candles = client.get_candles(symbol, "1", now_ms // 1000 - 86400, now_ms // 1000)
        depth = client.get_depth(symbol)
        result: dict[str, Any] = jsonable(
            build_market_status(
                symbol=symbol,
                price=trades[0].price,
                trade_ts=trades[0].timestamp,
                candles=candles,
                depth=depth,
                params=setup.params,
                price_precision=setup.market.price_precision,
                maker_fee=setup.maker,
                now_ms=now_ms,
            )
        )
        return result

    def recoverable(self) -> list[dict[str, Any]]:
        """Interrupted runs found in the repository that can be recovered."""
        live = {
            rid
            for rid, run in self._runs.items()
            if run.engine.state in (EngineState.RUNNING, EngineState.PAUSED)
        }
        return recoverable_runs(self.repo, live)

    def _on_done(self, run_id: str, task: "asyncio.Task[None]") -> None:
        """Remember the final picture and release the feed, whatever way the run ended."""
        run = self._runs[run_id]
        if not task.cancelled():
            task.exception()  # mark retrieved; the engine already logged the error as an event
        run.final = run.engine.snapshot()
        closer = getattr(run.feed, "close", None)
        if closer is not None:
            run.cleanup = asyncio.ensure_future(closer())

    def _get(self, run_id: str) -> _ActiveRun:
        run = self._runs.get(run_id)
        if run is None:
            raise UnknownRun(run_id)
        return run

    @staticmethod
    def _require(run: _ActiveRun, *states: EngineState) -> None:
        if run.engine.state not in states:
            wanted = " or ".join(s.value for s in states)
            raise InvalidRunState(f"run is {run.engine.state.value}, needs to be {wanted}")

    async def pause_run(self, run_id: str) -> None:
        run = self._get(run_id)
        self._require(run, EngineState.RUNNING)
        run.engine.pause()

    async def resume_run(self, run_id: str) -> None:
        run = self._get(run_id)
        self._require(run, EngineState.PAUSED)
        run.engine.resume()

    async def stop_run(self, run_id: str) -> None:
        run = self._get(run_id)
        self._require(run, EngineState.RUNNING, EngineState.PAUSED)
        await run.engine.stop()
        await self._settle(run)

    async def kill_run(self, run_id: str) -> None:
        run = self._get(run_id)
        self._require(run, EngineState.RUNNING, EngineState.PAUSED)
        run.engine.kill("kill switch pressed (API)")
        await self._settle(run)

    @staticmethod
    async def _settle(run: _ActiveRun) -> None:
        """Wait until the engine task and its cleanup have finished."""
        await asyncio.wait({run.task}, timeout=2)
        if run.cleanup is not None:
            await asyncio.wait({run.cleanup}, timeout=2)

    def snapshot(self, run_id: str) -> dict[str, Any] | None:
        """Live picture of a run, or its last picture once finished; None if unknown."""
        run = self._runs.get(run_id)
        if run is None:
            return None
        return run.final if run.final is not None else run.engine.snapshot()

    def live_runs(self) -> list[dict[str, Any]]:
        """One summary row per run started in this process."""
        rows = []
        for run_id, run in self._runs.items():
            snap = self.snapshot(run_id)
            assert snap is not None
            status = snap["status"]
            change = None
            if status["equity"] is not None and status["initial_equity"] not in (None, "0"):
                initial = Decimal(status["initial_equity"])
                change = str((Decimal(status["equity"]) - initial) / initial * 100)
            rows.append(
                {
                    "id": run_id,
                    "state": status["state"],
                    "market": run.symbol,
                    "mode": "paper",
                    "started_at": run.started_at,
                    "last_price": status["last_price"],
                    "return_pct": change,
                    "open_orders": status["open_orders"],
                    "fills": status["fills"],
                    "completed_cycles": status["completed_cycles"],
                    "halt_reason": status["halt_reason"],
                }
            )
        return rows

    # --- backtests ------------------------------------------------------------------

    async def start_backtest(
        self, config: Config, from_ts: int, to_ts: int, resolution: str = "60"
    ) -> str:
        """Start a backtest in the background; returns its id (poll `backtest(id)`)."""
        bt_id = f"bt_{uuid.uuid4().hex[:8]}"
        self._backtests[bt_id] = {
            "id": bt_id,
            "status": "running",
            "market": str(config.market.symbol),
        }
        task = asyncio.create_task(self._run_backtest(bt_id, config, from_ts, to_ts, resolution))
        self._backtest_tasks.add(task)
        task.add_done_callback(self._backtest_tasks.discard)
        return bt_id

    def backtest(self, bt_id: str) -> dict[str, Any] | None:
        return self._backtests.get(bt_id)

    async def _run_backtest(
        self, bt_id: str, config: Config, from_ts: int, to_ts: int, resolution: str
    ) -> None:
        record = self._backtests[bt_id]
        try:
            result = await asyncio.to_thread(
                self._backtest_sync, config, from_ts, to_ts, resolution
            )
        except Exception as exc:  # reported to the caller through the record, not raised
            record.update(status="failed", error=str(exc))
            return
        metrics = {
            key: (value if isinstance(value, int) else str(value))
            for key, value in dataclasses.asdict(result.metrics).items()
            if key != "equity_curve"
        }
        curve = result.metrics.equity_curve
        step = max(1, -(-len(curve) // MAX_CURVE_POINTS))
        sampled = curve[::step]
        if curve and sampled[-1] != curve[-1]:
            sampled.append(curve[-1])
        record.update(
            status="done",
            metrics=metrics,
            equity_curve=[str(v) for v in sampled],
            events=result.events[:50],
            fills=len(result.fills),
        )

    def _backtest_sync(
        self, config: Config, from_ts: int, to_ts: int, resolution: str
    ) -> BacktestResult:
        client = self._client_factory()
        symbol = str(config.market.symbol)
        info = find_market(client, symbol)
        if info is None:
            raise ValueError(f"market {symbol} not found (is it a spot market?)")
        candles = client.get_candles(symbol, resolution, from_ts, to_ts)
        if not candles:
            raise ValueError("no candle data for that period")
        setup = GridSetup.from_config(config, info)
        return Backtester(
            strategy=setup.new_strategy(),
            exchange=setup.new_exchange(),
            price_feed=PriceFeedReplay(candles_to_ticks(candles)),
        ).run()

    # --- shutdown -------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Stop every running engine and cancel pending backtests (called at app shutdown)."""
        for run in list(self._runs.values()):
            if run.engine.state in (EngineState.RUNNING, EngineState.PAUSED):
                await run.engine.stop()
            await self._settle(run)
        for task in list(self._backtest_tasks):
            task.cancel()
