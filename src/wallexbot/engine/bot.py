"""BotEngine: the async paper-trading loop.

Reads prices from a `PriceFeed`, drives a `TradingSession` (strategy + simulated exchange), watches
the risk limits and can be stopped or killed at any time. Paper trading only: nothing here talks to
Wallex with credentials, and orders only ever exist inside the simulator.

States: IDLE -> RUNNING <-> PAUSED -> STOPPED (feed ended or stop()) | HALTED (kill switch, risk limit) |
FAILED (unexpected error; orders are cancelled and the error is re-raised).
"""

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from wallexbot.engine.config import EngineConfig
from wallexbot.engine.recorder import RunRecorder
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
        self.session = TradingSession(config.strategy, config.exchange)
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

    # --- control --------------------------------------------------------------------

    def start(self) -> "asyncio.Task[None]":
        """Run in the background; returns the task."""
        self._task = asyncio.create_task(self.run())
        return self._task

    async def run(self) -> None:
        """Consume the price feed until it ends, the engine is stopped/killed, or it fails."""
        if self.state is not EngineState.IDLE:
            raise RuntimeError("this engine already ran; create a new one")
        self.state = EngineState.RUNNING
        self._task = self._task or asyncio.current_task()
        self._open_recorder()
        self._log("engine started")

        try:
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

    def pause(self) -> None:
        """Freeze trading: prices are still tracked, but no orders fill or are placed."""
        if self.state is EngineState.RUNNING:
            self.state = EngineState.PAUSED
            self._log("paused")

    def resume(self) -> None:
        """Continue after pause(); the next price is processed normally."""
        if self.state is EngineState.PAUSED:
            self.state = EngineState.RUNNING
            self._log("resumed")

    def kill(self, reason: str = "manual kill switch") -> None:
        """Kill switch: cancel every order and stop trading. Safe to call from anywhere."""
        if self.state in (EngineState.HALTED, EngineState.STOPPED, EngineState.FAILED):
            return
        self.session.stop()
        self.state = EngineState.HALTED
        self.halt_reason = reason
        self._log(f"HALTED: {reason}")
        self._sync_session()
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
            fills=len(self.session.fills),
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
        fills = []
        for fill in reversed(self.session.fills[-50:]):
            order = exchange.get_order(fill.order_id)
            fills.append(
                {
                    "time": fill.timestamp,
                    "side": order.side.value,
                    "price": str(fill.price),
                    "quantity": str(fill.quantity),
                    "fee": str(fill.fee),
                    "fee_asset": fill.fee_asset,
                }
            )
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
        self._last_price = tick.price
        self._equity = self.session.equity(tick.price)
        self._sync_session()

        risk = self.config.risk
        if risk is not None:
            breach = risk.update(self._equity, tick.timestamp)
            if breach is not None:
                self.kill(breach)

    def _sync_session(self) -> None:
        """Copy new session events and fills into the engine log and the repository."""
        new_events = self.session.events[self._synced_events :]
        self._synced_events = len(self.session.events)
        for message in new_events:
            self._events.append(message)
            if self._recorder:
                self._recorder.event("session", message)

        new_fills = self.session.fills[self._synced_fills :]
        self._synced_fills = len(self.session.fills)
        if self._recorder:
            state = self.config.strategy.state
            for fill in new_fills:
                order = self.config.exchange.get_order(fill.order_id)
                level = state.get_level_for_order(order.client_id) if state else None
                self._recorder.fill(order, fill, level)

    def _finish(self, state: EngineState, message: str, cancel_orders: bool = True) -> None:
        self.state = state
        if cancel_orders and self.config.cancel_on_shutdown:
            self.session.stop()
        self._log(message)
        self._sync_session()

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
