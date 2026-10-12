"""BotEngine: the async paper-trading loop.

Reads prices from a `PriceFeed`, drives a `TradingSession` (strategy + simulated exchange), watches
the risk limits and can be stopped or killed at any time. Paper trading only: nothing here talks to
Wallex with credentials, and orders only ever exist inside the simulator.

States: IDLE -> RUNNING -> STOPPED (feed ended or stop()) | HALTED (kill switch, risk limit) |
FAILED (unexpected error; orders are cancelled and the error is re-raised).
"""

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from wallexbot.engine.config import EngineConfig
from wallexbot.engine.recorder import RunRecorder
from wallexbot.engine.session import TradingSession
from wallexbot.wallex.price_feed import PriceTick

STATUS_EVENTS = 20  # how many recent events a status snapshot carries


class EngineState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
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
                if self.state is not EngineState.RUNNING:
                    break
                self._handle_tick(tick)
                if self.state is not EngineState.RUNNING:
                    break
        except asyncio.CancelledError:
            if self.state is EngineState.HALTED:
                # kill() woke the loop: a halt is a normal outcome, so return instead of raising
                self._close_recorder()
                return
            if self.state is EngineState.RUNNING:
                self._finish(EngineState.STOPPED, "engine stopped")
            raise
        except Exception as exc:
            self._log(f"engine error: {type(exc).__name__}: {exc}")
            self.session.stop()
            self._finish(EngineState.FAILED, "engine failed", cancel_orders=False)
            raise

        if self.state is EngineState.RUNNING:
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

    # --- internals ------------------------------------------------------------------

    def _handle_tick(self, tick: PriceTick) -> None:
        if self._ticks == 0:
            self._initial_equity = self.session.equity(tick.price)
            self.session.start(tick.price, tick.timestamp)  # the grid is built around THIS price
        else:
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
            self._recorder.finish(self.state.value)
            self._recorder = None
