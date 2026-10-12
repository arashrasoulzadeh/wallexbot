"""Live price feeds built on the public Wallex endpoints (no API key).

- `WebSocketTradeFeed`: subscribes to `<SYMBOL>@trade` and turns each trade into a tick. Reconnects
  (and rotates the connection before the server's 30-minute cutoff) via `WallexWebSocketClient`.
- `RestPollingFeed`: polls the latest public trade; slower, but needs nothing but HTTPS.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Protocol

import httpx

from wallexbot.domain import Clock, SystemClock
from wallexbot.domain.market import Symbol
from wallexbot.wallex.client import WallexApiError
from wallexbot.wallex.models import Trade
from wallexbot.wallex.price_feed import PriceTick
from wallexbot.wallex.websocket import Message, WallexWebSocketClient

logger = logging.getLogger(__name__)


class WebSocketTradeFeed:
    """Ticks from the public trade channel of one market."""

    def __init__(self, symbol: Symbol, client: WallexWebSocketClient | None = None) -> None:
        self.symbol = symbol
        self.client = client or WallexWebSocketClient()
        self._queue: asyncio.Queue[PriceTick] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    async def subscribe(self, symbol: Symbol) -> None:  # PriceFeed protocol; fixed to one market
        pass

    async def unsubscribe(self, symbol: Symbol) -> None:
        pass

    def _on_message(self, message: Message) -> None:
        if isinstance(message, Trade) and message.symbol == self.symbol:
            self._queue.put_nowait(
                PriceTick(
                    symbol=self.symbol,
                    price=message.price,
                    timestamp=message.timestamp,
                    source="live",
                )
            )

    async def ticks(self) -> AsyncGenerator[PriceTick, None]:
        if self._task is None:
            self._task = asyncio.create_task(
                self.client.run_with_reconnect([f"{self.symbol}@trade"], self._on_message)
            )
        while not self._closed:
            getter = asyncio.ensure_future(self._queue.get())
            await asyncio.wait({getter, self._task}, return_when=asyncio.FIRST_COMPLETED)
            if getter.done():
                yield getter.result()
                continue
            getter.cancel()
            if self._task.done() and not self._task.cancelled():
                self._task.result()  # re-raise a crash instead of ending quietly
            return

    async def close(self) -> None:
        """Stop streaming and release the socket."""
        self._closed = True
        self.client.stop()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.client.disconnect()


class _TradeSource(Protocol):
    def get_latest_trades(self, symbol: str, limit: int = 50) -> list[Trade]: ...


class RestPollingFeed:
    """Ticks from polling the latest public trade every `interval` seconds."""

    def __init__(
        self,
        symbol: Symbol,
        client: _TradeSource,
        interval: float = 2.0,
        clock: Clock | None = None,
    ) -> None:
        self.symbol = symbol
        self.client = client
        self.interval = interval
        self.clock = clock or SystemClock()
        self._closed = False

    async def subscribe(self, symbol: Symbol) -> None:
        pass

    async def unsubscribe(self, symbol: Symbol) -> None:
        pass

    async def ticks(self) -> AsyncGenerator[PriceTick, None]:
        last: tuple[int, object, object] | None = None
        first_poll = True
        while not self._closed:
            if not first_poll:
                await self.clock.async_sleep(self.interval)
            first_poll = False
            try:
                trades = await asyncio.to_thread(self.client.get_latest_trades, str(self.symbol), 1)
            except (WallexApiError, httpx.HTTPError, OSError) as exc:
                logger.warning("price poll failed (%s); retrying", exc)
                continue
            if not trades:
                continue
            latest = trades[0]
            key = (latest.timestamp, latest.price, latest.quantity)
            if key == last:
                continue
            last = key
            yield PriceTick(
                symbol=self.symbol, price=latest.price, timestamp=latest.timestamp, source="live"
            )

    async def close(self) -> None:
        self._closed = True


def make_price_feed(
    kind: str, symbol: Symbol, client: _TradeSource
) -> WebSocketTradeFeed | RestPollingFeed:
    """Live price feed for paper trading: public WebSocket trades ("ws") or REST polling ("poll")."""
    if kind == "poll":
        return RestPollingFeed(symbol, client)
    return WebSocketTradeFeed(symbol)
