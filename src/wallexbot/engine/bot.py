"""Bot engine - wires strategy, exchange, and data feed."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
import asyncio
import signal

from wallexbot.engine.config import EngineConfig
from wallexbot.engine.actions import ActionExecutor
from wallexbot.strategy.grid.interface import GridStrategy, Action
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.wallex.price_feed import PriceFeed, PriceTick
from wallexbot.domain import Clock


@dataclass
class BotEngine:
    """Main bot engine."""

    config: EngineConfig
    _running: bool = field(default=False, init=False)
    _halted: bool = field(default=False, init=False)
    _executor: ActionExecutor = field(init=False)
    _price_task: Optional[asyncio.Task] = field(default=None, init=False)
    _poll_task: Optional[asyncio.Task] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._executor = ActionExecutor(
            exchange=self.config.exchange,
            clock=self.config.clock,
        )

    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._running and not self._halted

    def is_halted(self) -> bool:
        """Check if engine is halted."""
        return self._halted

    async def start(self) -> None:
        """Start the bot engine."""
        if self._running:
            return

        # 1. Load and validate config (already done)

        # 2. Fetch market info and fee schedule
        market = self.config.exchange.market_info()
        fee_schedule = self.config.exchange.fee_schedule()

        # 3. Check balances sufficient for grid
        balances = self.config.exchange.balances()
        # Strategy will validate in on_start

        # 4. Reconcile with existing open orders (Phase 9)

        # 5. Place initial grid
        initial_actions = self.config.strategy.on_start(
            current_price=Decimal("100.00"),  # Will be updated from feed
            timestamp=int(self.config.clock.now() * 1000),
        )

        for action in initial_actions:
            self._executor.execute(action)

        # Start price feed processing
        self._running = True
        self._price_task = asyncio.create_task(self._process_price_feed())

        # Start polling fallback
        self._poll_task = asyncio.create_task(self._polling_fallback())

    async def _process_price_feed(self) -> None:
        """Process price feed events."""
        try:
            async for tick in self.config.price_feed.ticks():
                if not self._running or self._halted:
                    break

                await self._handle_price_tick(tick)
        except Exception as e:
            # Log error
            pass

    async def _handle_price_tick(self, tick: PriceTick) -> None:
        """Handle a single price tick."""
        # Update strategy with new price
        actions = self.config.strategy.on_price(
            current_price=tick.price,
            timestamp=tick.timestamp,
        )

        # Execute actions
        for action in actions:
            self._executor.execute(action)

    async def _polling_fallback(self) -> None:
        """Polling fallback when event stream is down."""
        while self._running and not self._halted:
            await asyncio.sleep(self.config.poll_interval)

            if self._halted:
                break

            # Poll open orders and diff to infer fills
            open_orders = self.config.exchange.open_orders()
            # Compare with strategy state to infer fills
            # This is a simplified implementation

    async def process_next_tick(self) -> Optional[PriceTick]:
        """Process next tick from feed (for testing)."""
        # This would pull from the feed
        pass

    def kill(self) -> None:
        """Kill switch - stop placing, cancel all orders."""
        self._halted = True

        # Cancel all open orders
        for order in self.config.exchange.open_orders():
            self.config.exchange.cancel_order(order.id)

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self._running = False

        if self._price_task:
            self._price_task.cancel()
            try:
                await self._price_task
            except asyncio.CancelledError:
                pass

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        # Per config: cancel orders or leave them
        # For now, cancel all
        self.kill()

    def handle_fill(self, level_index: int, fill_qty: Decimal, fill_fee: Decimal, fill_fee_asset: str) -> None:
        """Handle fill event from exchange."""
        actions = self.config.strategy.on_fill(
            level_index=level_index,
            fill_qty=fill_qty,
            fill_fee=fill_fee,
            fill_fee_asset=fill_fee_asset,
            timestamp=int(self.config.clock.now() * 1000),
        )

        for action in actions:
            self._executor.execute(action)