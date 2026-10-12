"""Wallex WebSocket client for public channels.

Wire format (docs/offline/pages/socket-*.md): every message is a JSON array `[channel, payload]`,
and subscriptions are `["subscribe", {"channel": "USDTTMN@trade"}]`. The server closes each
connection after 30 minutes, so `run_with_reconnect` rotates the connection before that.
The server's 20-second PING is a protocol-level ping, answered automatically by `websockets`.
"""

import json
import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from websockets.exceptions import WebSocketException

from wallexbot.domain import Clock, SystemClock
from wallexbot.domain.market import Symbol
from wallexbot.domain.money import parse_wire_string
from wallexbot.wallex.models import Depth, OrderBookLevel, Trade

logger = logging.getLogger(__name__)

Message = Depth | Trade | dict[Symbol, Decimal]

# Server drops connections after 30 min; rotate a little earlier.
DEFAULT_MAX_CONNECTION_SECONDS = 25 * 60
MAX_BACKOFF_SECONDS = 60


def _decimal(value: Any) -> Decimal:
    return parse_wire_string(str(value))


def _iso_to_ms(value: str) -> int:
    return int(
        datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).timestamp() * 1000
    )


@dataclass
class WallexWebSocketClient:
    """Wallex public WebSocket client (no authentication)."""

    url: str = "wss://api.wallex.ir/ws"
    connection_factory: Callable[..., Any] | None = None
    clock: Clock = field(default_factory=SystemClock)
    _connection: Any = field(default=None, repr=False)
    _stopped: bool = field(default=False, repr=False)

    # --- frames ---------------------------------------------------------------------

    def build_subscribe(self, channel: str) -> list[Any]:
        """Build subscribe frame."""
        return ["subscribe", {"channel": channel}]

    def build_unsubscribe(self, channel: str) -> list[Any]:
        """Build unsubscribe frame."""
        return ["unsubscribe", {"channel": channel}]

    def parse_frame(self, frame: Any) -> Message | None:
        """Parse one decoded message; unknown or malformed frames return None."""
        if not isinstance(frame, list) or len(frame) != 2 or not isinstance(frame[0], str):
            return None
        channel, payload = frame
        try:
            if channel == "all@price" and isinstance(payload, dict):
                return {Symbol(payload["symbol"]): _decimal(payload["price"])}
            symbol, _, kind = channel.partition("@")
            if kind == "trade" and isinstance(payload, dict):
                return Trade(
                    symbol=Symbol(symbol),
                    price=_decimal(payload["price"]),
                    quantity=_decimal(payload["quantity"]),
                    side="BUY" if payload["isBuyOrder"] else "SELL",
                    timestamp=_iso_to_ms(payload["timestamp"]),
                )
            if kind in ("buyDepth", "sellDepth") and isinstance(payload, list):
                levels = [
                    OrderBookLevel(price=_decimal(r["price"]), quantity=_decimal(r["quantity"]))
                    for r in payload
                ]
                return Depth(
                    symbol=Symbol(symbol),
                    bids=levels if kind == "buyDepth" else [],
                    asks=levels if kind == "sellDepth" else [],
                    timestamp=int(self.clock.now() * 1000),
                )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            logger.warning("skipping malformed frame on %s", channel)
        return None

    # --- connection -----------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to the WebSocket."""
        if self.connection_factory:
            self._connection = await self.connection_factory()
        else:
            import websockets

            self._connection = await websockets.connect(self.url)

    async def disconnect(self) -> None:
        """Close the connection if open."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def subscribe(self, channel: str) -> None:
        """Subscribe to a channel (connects first if needed)."""
        if self._connection is None:
            await self.connect()
        await self._connection.send(json.dumps(self.build_subscribe(channel)))

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        if self._connection is not None:
            await self._connection.send(json.dumps(self.build_unsubscribe(channel)))

    def stop(self) -> None:
        """Ask `run_with_reconnect` / `messages` to finish."""
        self._stopped = True

    async def messages(self) -> AsyncGenerator[Message, None]:
        """Yield parsed messages from the current connection until it closes or stop() is called."""
        if self._connection is None:
            await self.connect()
        async for raw in self._connection:
            if self._stopped:
                break
            try:
                parsed = self.parse_frame(json.loads(raw))
            except json.JSONDecodeError:
                continue  # skip malformed frames
            if parsed is not None:
                yield parsed

    async def run_with_reconnect(
        self,
        channels: list[str],
        on_message: Callable[[Message], None],
        max_connection_seconds: float = DEFAULT_MAX_CONNECTION_SECONDS,
    ) -> None:
        """Stream `channels` forever: resubscribe after drops, rotate before the 30-min cutoff.

        Network errors back off exponentially (1s, 2s, 4s ... capped); anything else is a bug and
        propagates.
        """
        self._stopped = False
        delay = 1.0
        while not self._stopped:
            try:
                await self.connect()
                for channel in channels:
                    await self.subscribe(channel)
                delay = 1.0
                deadline = self.clock.now() + max_connection_seconds
                async for message in self.messages():
                    on_message(message)
                    if self._stopped or self.clock.now() >= deadline:
                        break  # stop requested, or rotate the connection
            except (OSError, TimeoutError, ConnectionError, WebSocketException) as exc:
                logger.warning("websocket error (%s); reconnecting in %.0fs", exc, delay)
                await self._safe_disconnect()
                if self._stopped:
                    break
                await self.clock.async_sleep(delay)
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)
            else:
                await self._safe_disconnect()

    async def _safe_disconnect(self) -> None:
        try:
            await self.disconnect()
        except (OSError, ConnectionError, WebSocketException):
            self._connection = None
