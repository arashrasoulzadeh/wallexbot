"""BotEngine: the async paper-trading loop.

Reads prices from a `PriceFeed`, drives a `TradingSession` (strategy + simulated exchange), watches
the risk limits and can be stopped or killed at any time. Paper trading only: nothing here talks to
Wallex with credentials, and orders only ever exist inside the simulator.

States: IDLE -> RUNNING <-> PAUSED -> STOPPED (feed ended or stop()) | HALTED (kill switch, risk limit) |
FAILED (unexpected error; orders are cancelled and the error is re-raised).
"""

import asyncio
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from wallexbot.domain.clock import ManualClock
from wallexbot.engine.config import EngineConfig
from wallexbot.engine.recorder import RunRecorder
from wallexbot.engine.recovery import CHECKPOINT_VERSION, RecoveryError, load_checkpoint
from wallexbot.engine.session import TradingSession
from wallexbot.wallex.price_feed import PriceTick

STATUS_EVENTS = 20  # how many recent events a status snapshot carries


class EngineState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    HALTED = "halted"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class EngineStatus:
    """Snapshot of the engine for UIs, logs and tests."""

    state: EngineState
    halt_reason: str
    last_price: Decimal | None
    initial_equity: Decimal | None
    equity: Decimal | None
    open_orders: int
    deferred_orders: int
    rejected_orders: int
    fills: int
    completed_cycles: int
    realized_pnl: Decimal
    fees_paid: Decimal
    ticks_processed: int
    events: list[str] = field(default_factory=list)


class BotEngine:
    """Runs one grid against a live (or scripted) price feed on the simulated exchange."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.session = TradingSession(
            config.strategy,
            config.exchange,
            keep_fills=config.keep_fills,
            keep_events=config.keep_events,
        )
        self.state = EngineState.IDLE
        self.halt_reason = ""
        self._events: list[str] = []
        self._task: asyncio.Task[None] | None = None
        self._ticks = 0
        self._last_price: Decimal | None = None
        self._initial_equity: Decimal | None = None
        self._equity: Decimal | None = None
        self._synced_fills = 0
        self._synced_events = 0
        self._recorder: RunRecorder | None = None
        self._run_id = ""
        self._ran = False
        self._restored = False
        self._last_tick_ts = 0
        self._catchup: list[PriceTick] = []
        self._checkpoint_key: tuple[object, ...] | None = None
        self._ticks_since_checkpoint = 0
        self._last_snapshot_ts: int | None = None
        self._last_snapshot_fills = 0

    # --- control --------------------------------------------------------------------

    def start(self) -> "asyncio.Task[None]":
        """Run in the background; returns the task."""
        self._task = asyncio.create_task(self.run())
        return self._task

    async def run(self) -> None:
        """Consume the price feed until it ends, the engine is stopped/killed, or it fails."""
        if self._ran:
            raise RuntimeError("this engine already ran; create a new one")
        self._ran = True
        if self.state is EngineState.IDLE:
            self.state = EngineState.RUNNING
        self._task = self._task or asyncio.current_task()
        self._open_recorder()
        self._log("recovered from a checkpoint" if self._restored else "engine started")

        try:
            self._replay_catchup()
            async for tick in self.config.price_feed.ticks():
                if self.state not in (EngineState.RUNNING, EngineState.PAUSED):
                    break
                self._handle_tick(tick)
                if self.state not in (EngineState.RUNNING, EngineState.PAUSED):
                    break
        except asyncio.CancelledError:
            if self.state is EngineState.HALTED:
                # kill() woke the loop: a halt is a normal outcome, so return instead of raising
                self._close_recorder()
                return
            if self.state in (EngineState.RUNNING, EngineState.PAUSED):
                self._finish(EngineState.STOPPED, "engine stopped")
            raise
        except Exception as exc:
            self._log(f"engine error: {type(exc).__name__}: {exc}")
            self.session.stop()
            self._finish(EngineState.FAILED, "engine failed", cancel_orders=False)
            raise

        if self.state in (EngineState.RUNNING, EngineState.PAUSED):
            self._finish(EngineState.STOPPED, "price feed ended")
        self._close_recorder()

    async def stop(self) -> None:
        """Stop gracefully (cancels orders unless configured otherwise) and wait for the loop."""
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._close_recorder()

    @property
    def run_id(self) -> str:
        """Id of the recorded run ("" until the run started, or when not recording)."""
        return self._recorder.run_id if self._recorder else self._run_id

    def set_catchup(self, ticks: list[PriceTick]) -> None:
        """Public prices from the downtime, replayed (oldest first) before live prices resume."""
        self._catchup = sorted(ticks, key=lambda t: t.timestamp)

    def restore(self, run_id: str) -> None:
        """Rebuild this (fresh) engine from the checkpoint of an interrupted run.

        The run keeps its id and record; `run()` then continues it. Raises RecoveryError when the
        run cannot be recovered.
        """
        repo = self.config.repository
        if repo is None:
            raise RecoveryError("recovery needs a repository")
        if self.state is not EngineState.IDLE or self._ran:
            raise RecoveryError("this engine already ran; recover into a fresh one")
        saved = load_checkpoint(repo, run_id)

        self.session.import_state(saved["session"])
        if self.config.risk is not None and saved.get("risk") is not None:
            self.config.risk.import_state(saved["risk"])
        mine = saved["engine"]
        self._ticks = mine["ticks"]
        self._last_tick_ts = mine["last_tick_ts"]
        self._last_price = None if mine["last_price"] is None else Decimal(mine["last_price"])
        self._initial_equity = (
            None if mine["initial_equity"] is None else Decimal(mine["initial_equity"])
        )
        self._equity = None if mine["equity"] is None else Decimal(mine["equity"])
        self._events = list(mine["events"])
        self._last_snapshot_ts = mine.get("last_snapshot_ts")
        self._last_snapshot_fills = mine.get("last_snapshot_fills", self.session.fill_count)
        self._synced_fills = self.session.fill_count  # already recorded before the crash
        self._synced_events = self.session.event_count
        self._run_id = run_id
        self._restored = True
        self.state = EngineState.PAUSED if mine["paused"] else EngineState.RUNNING

    def pause(self) -> None:
        """Freeze trading: prices are still tracked, but no orders fill or are placed."""
        if self.state is EngineState.RUNNING:
            self.state = EngineState.PAUSED
            self._log("paused")
            self._save_checkpoint()

    def resume(self) -> None:
        """Continue after pause(); the next price is processed normally."""
        if self.state is EngineState.PAUSED:
            self.state = EngineState.RUNNING
            self._log("resumed")
            self._save_checkpoint()

    def kill(self, reason: str = "manual kill switch") -> None:
        """Kill switch: cancel every order and stop trading. Safe to call from anywhere."""
        if self.state in (EngineState.HALTED, EngineState.STOPPED, EngineState.FAILED):
            return
        self.session.stop()
        self.state = EngineState.HALTED
        self.halt_reason = reason
        self._log(f"HALTED: {reason}")
        self._sync_session()
        self._save_checkpoint()
        task = self._task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()  # wake a loop that is waiting for the next price

    def status(self) -> EngineStatus:
        """Current snapshot."""
        tracker = self.config.strategy.profit_tracker
        return EngineStatus(
            state=self.state,
            halt_reason=self.halt_reason,
            last_price=self._last_price,
            initial_equity=self._initial_equity,
            equity=self._equity,
            open_orders=len(self.config.exchange.open_orders()),
            deferred_orders=self.session.deferred_count,
            rejected_orders=self.session.rejected,
            fills=self.session.fill_count,
            completed_cycles=tracker.total_cycles,
            realized_pnl=tracker.total_profit,
            fees_paid=self.session.fees_quote,
            ticks_processed=self._ticks,
            events=self._events[-STATUS_EVENTS:],
        )

    def snapshot(self) -> dict[str, Any]:
        """Everything a UI needs, as plain JSON types (Decimals as strings)."""
        status = self.status()
        total = (
            status.equity - status.initial_equity
            if status.equity is not None and status.initial_equity is not None
            else Decimal(0)
        )
        exchange = self.config.exchange
        strategy_state = self.config.strategy.state
        params = self.config.strategy.params

        def level_of(client_id: str) -> int | None:
            return strategy_state.get_level_for_order(client_id) if strategy_state else None

        orders = [
            {
                "level": level_of(o.client_id),
                "side": o.side.value,
                "price": str(o.price),
                "quantity": str(o.quantity),
                "filled": str(o.filled_quantity),
                "client_id": o.client_id,
            }
            for o in sorted(
                exchange.open_orders(), key=lambda o: o.price or Decimal(0), reverse=True
            )
        ]
        fills = list(reversed(self.session.fill_rows))  # newest first
        resting = {o["level"]: o["side"] for o in orders if o["level"] is not None}
        levels = [
            {"index": lv.index, "price": str(lv.price), "order": resting.get(lv.index)}
            for lv in (strategy_state.levels if strategy_state else [])
        ]
        return {
            "run_id": self.run_id,
            "status": {
                "state": status.state.value,
                "halt_reason": status.halt_reason,
                "last_price": None if status.last_price is None else str(status.last_price),
                "initial_equity": None
                if status.initial_equity is None
                else str(status.initial_equity),
                "equity": None if status.equity is None else str(status.equity),
                "open_orders": status.open_orders,
                "deferred_orders": status.deferred_orders,
                "rejected_orders": status.rejected_orders,
                "fills": status.fills,
                "completed_cycles": status.completed_cycles,
                "realized_pnl": str(status.realized_pnl),
                "unrealized_pnl": str(total - status.realized_pnl),
                "total_pnl": str(total),
                "fees_paid": str(status.fees_paid),
                "ticks_processed": status.ticks_processed,
                "events": status.events,
            },
            "orders": orders,
            "fills": fills,
            "balances": [
                {
                    "asset": asset,
                    "free": str(b.free),
                    "locked": str(b.locked),
                    "total": str(b.total),
                }
                for asset, b in exchange.balances().items()
            ],
            "grid": {
                "lower": str(params.lower_price),
                "upper": str(params.upper_price),
                "mode": params.mode.value,
                "price": None if status.last_price is None else str(status.last_price),
                "levels": levels,
            },
        }

    # --- internals ------------------------------------------------------------------

    def _handle_tick(self, tick: PriceTick) -> None:
        if self._ticks == 0:
            self._initial_equity = self.session.equity(tick.price)
            self.session.start(tick.price, tick.timestamp)  # the grid is built around THIS price
        elif self.state is EngineState.RUNNING:
            self.session.on_tick(tick.price, tick.timestamp)
        self._ticks += 1
        self._last_tick_ts = tick.timestamp
        self._last_price = tick.price
        self._equity = self.session.equity(tick.price)
        self._sync_session()
        self._maybe_snapshot(tick.timestamp)  # before the checkpoint, which records its cursor
        self._maybe_checkpoint()

        risk = self.config.risk
        if risk is not None:
            breach = risk.update(self._equity, tick.timestamp)
            if breach is not None:
                self.kill(breach)

    def _sync_session(self) -> None:
        """Copy new session events and fills into the engine log and the repository."""
        new_events = self.session.event_count - self._synced_events
        self._synced_events = self.session.event_count
        if new_events > 0:
            for message in self.session.events[-new_events:]:
                self._events.append(message)
                if self._recorder:
                    self._recorder.event("session", message)
            del self._events[: max(0, len(self._events) - self.config.keep_events)]

        new_fills = self.session.fill_count - self._synced_fills
        self._synced_fills = self.session.fill_count
        if new_fills > 0 and self._recorder:
            state = self.config.strategy.state
            for fill in self.session.fills[-new_fills:]:
                order = self.config.exchange.get_order(fill.order_id)
                level = state.get_level_for_order(order.client_id) if state else None
                self._recorder.fill(order, fill, level)

    # --- history ---------------------------------------------------------------------

    def _maybe_snapshot(self, timestamp: int, force: bool = False) -> None:
        """Record price and equity for the History page: at the first price, whenever a fill
        happened, and otherwise at most every `snapshot_every_ms`."""
        recorder = self._recorder
        if recorder is None or not recorder.run_id or self._equity is None:
            return
        fills = self.session.fill_count
        last = self._last_snapshot_ts
        if (
            not force
            and last is not None
            and timestamp - last < self.config.snapshot_every_ms
            and fills == self._last_snapshot_fills
        ):
            return
        tracker = self.config.strategy.profit_tracker
        recorder.snapshot(
            {
                "ts": timestamp,
                "price": None if self._last_price is None else str(self._last_price),
                "equity": str(self._equity),
                "realized": str(tracker.total_profit),
                "fees": str(self.session.fees_quote),
                "open_orders": len(self.config.exchange.open_orders()),
                "fills": fills,
                "cycles": tracker.total_cycles,
            }
        )
        self._last_snapshot_ts = timestamp
        self._last_snapshot_fills = fills

    # --- checkpoints ----------------------------------------------------------------

    def _checkpoint_state(self) -> dict[str, Any]:
        risk = self.config.risk
        return {
            "version": CHECKPOINT_VERSION,
            "saved_at": int(time.time() * 1000),
            "app_config": self.config.app_config,
            "engine": {
                "ticks": self._ticks,
                "last_tick_ts": self._last_tick_ts,
                "last_price": None if self._last_price is None else str(self._last_price),
                "initial_equity": None
                if self._initial_equity is None
                else str(self._initial_equity),
                "equity": None if self._equity is None else str(self._equity),
                "events": self._events[-200:],
                "paused": self.state is EngineState.PAUSED,
                "last_snapshot_ts": self._last_snapshot_ts,
                "last_snapshot_fills": self._last_snapshot_fills,
            },
            "risk": None if risk is None else risk.export_state(),
            "session": self.session.export_state(),
        }

    def _save_checkpoint(self) -> None:
        """Write the full state to the repository (no-op when not recording)."""
        recorder = self._recorder
        if recorder is None or not recorder.run_id:
            return
        recorder.repository.save_checkpoint(recorder.run_id, self._checkpoint_state())
        self._ticks_since_checkpoint = 0
        self._checkpoint_key = self._change_key()

    def _change_key(self) -> tuple[object, ...]:
        return (
            self.session.fill_count,
            len(self.config.exchange.open_orders()),
            self.session.deferred_count,
            self.session.event_count,
            self.state,
        )

    def _maybe_checkpoint(self) -> None:
        """Save after anything changed, and at least every `checkpoint_every_ticks` prices."""
        self._ticks_since_checkpoint += 1
        if (
            self._change_key() != self._checkpoint_key
            or self._ticks_since_checkpoint >= self.config.checkpoint_every_ticks
        ):
            self._save_checkpoint()

    # --- replaying the downtime -----------------------------------------------------

    def _replay_catchup(self) -> None:
        """Feed the public prices of the downtime through the grid before going live."""
        ticks = [t for t in self._catchup if t.timestamp > self._last_tick_ts]
        if not ticks:
            return
        exchange = self.config.exchange
        live_clock = exchange.clock
        replay_clock = ManualClock()
        exchange.use_clock(replay_clock)  # rate limits follow the replayed time, not real time
        try:
            for tick in ticks:
                if self.state not in (EngineState.RUNNING, EngineState.PAUSED):
                    break
                replay_clock.set_time(tick.timestamp / 1000)
                self._handle_tick(tick)
        finally:
            exchange.use_clock(live_clock)
        self._log(f"replayed {len(ticks)} price points from the downtime")
        self._save_checkpoint()

    def _finish(self, state: EngineState, message: str, cancel_orders: bool = True) -> None:
        self.state = state
        if cancel_orders and self.config.cancel_on_shutdown:
            self.session.stop()
        self._log(message)
        self._sync_session()
        if self._ticks > 0:
            self._maybe_snapshot(self._last_tick_ts, force=True)
        self._save_checkpoint()

    def _log(self, message: str) -> None:
        self._events.append(message)
        if self._recorder:
            self._recorder.event("engine", message)

    def _open_recorder(self) -> None:
        if self.config.repository is None:
            return
        params = self.config.strategy.params
        self._recorder = RunRecorder(
            self.config.repository,
            self.config.run_name,
            str(self.config.exchange.market_info().symbol),
        )
        if self._restored:
            self._recorder.attach(self._run_id)  # the same run continues
            return
        self._recorder.start(
            {
                "lower_price": str(params.lower_price),
                "upper_price": str(params.upper_price),
                "grid_count": params.grid_count,
            }
        )

    def _close_recorder(self) -> None:
        if self._recorder and self._recorder.run_id:
            self._run_id = self._recorder.run_id  # keep the id after the recorder is released
            self._recorder.finish(self.state.value)
            self._recorder = None
