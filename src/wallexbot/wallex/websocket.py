"""Wallex WebSocket client for public channels."""

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from wallexbot.domain import Clock
from wallexbot.domain.market import Symbol
from wallexbot.domain.money import parse_wire_string
from wallexbot.wallex.models import Depth, OrderBookLevel, Trade


@dataclass
class WallexWebSocketClient:
    """Wallex public WebSocket client."""

    url: str = "wss://api.wallex.ir/ws"
    connection_factory: Callable[..., Any] | None = None
    clock: Clock = None

    def __post_init__(self) -> None:
        if self.clock is None:
            self.clock = _RealClock()
        self._connection = None
        self._running = False

    def build_subscribe(self, channel: str) -> list[Any]:
        """Build subscribe frame."""
        return ["subscribe", {"channel": channel}]

    def build_unsubscribe(self, channel: str) -> list[Any]:
        """Build unsubscribe frame."""
        return ["unsubscribe", {"channel": channel}]

    async def connect(self) -> None:
        """Connect to WebSocket."""
        if self.connection_factory:
            self._connection = await self.connection_factory()
        else:
            import websockets

            self._connection = await websockets.connect(self.url)

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def subscribe(self, channel: str) -> None:
        """Subscribe to a channel."""
        if not self._connection:
            await self.connect()
        frame = self.build_subscribe(channel)
        await self._connection.send(json.dumps(frame))

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        if self._connection:
            frame = self.build_unsubscribe(channel)
            await self._connection.send(json.dumps(frame))

    def parse_frame(self, frame: dict[str, Any]) -> Depth | Trade | dict | None:
        """Parse incoming WebSocket frame."""
        event = frame.get("event")
        channel = frame.get("channel", "")
        data = frame.get("data", {})

        if event == "ping":
            return {"type": "pong"}

        if event == "pong":
            return None

        if event == "trade" or channel.endswith("@trade"):
            return self._parse_trade(channel, data)

        if event == "depth" or channel.endswith("@buyDepth") or channel.endswith("@sellDepth"):
            return self._parse_depth(channel, data)

        if event == "price" or channel == "all@price":
            return self._parse_price(data)

        # Unknown frame - log and skip
        return None

    def _parse_trade(self, channel: str, data: dict[str, Any]) -> Trade:
        """Parse trade frame."""
        symbol = channel.split("@")[0]
        return Trade(
            symbol=Symbol(symbol),
            price=parse_wire_string(data["price"]),
            quantity=parse_wire_string(data["quantity"]),
            side=data["side"].upper(),
            timestamp=data["timestamp"],
        )

    def _parse_depth(self, channel: str, data: dict[str, Any]) -> Depth:
        """Parse depth frame."""
        symbol = channel.split("@")[0]
        bids = []
        asks = []

        if "bids" in data:
            bids = [
                OrderBookLevel(price=parse_wire_string(p), quantity=parse_wire_string(q))
                for p, q in data["bids"]
            ]
        if "asks" in data:
            asks = [
                OrderBookLevel(price=parse_wire_string(p), quantity=parse_wire_string(q))
                for p, q in data["asks"]
            ]

        return Depth(
            symbol=Symbol(symbol),
            bids=bids,
            asks=asks,
            timestamp=int(self.clock.now() * 1000),
        )

    def _parse_price(self, data: dict[str, Any]) -> dict[Symbol, Decimal]:
        """Parse all@price frame."""
        prices = {}
        for symbol, price_str in data.items():
            prices[Symbol(symbol)] = parse_wire_string(price_str)
        return prices

    async def handle_message(self, frame: dict[str, Any]) -> dict | None:
        """Handle incoming message, respond to pings."""
        if frame.get("event") == "ping":
            if self._connection:
                await self._connection.send(json.dumps({"event": "pong"}))
            return {"type": "pong"}

        return self.parse_frame(frame)

    async def messages(self) -> AsyncGenerator[dict, None]:
        """Async generator yielding parsed messages."""
        if not self._connection:
            await self.connect()

        self._running = True
        try:
            async for raw_message in self._connection:
                if not self._running:
                    break

                try:
                    frame = json.loads(raw_message)
                    parsed = await self.handle_message(frame)
                    if parsed is not None:
                        yield parsed
                except json.JSONDecodeError:
                    continue  # Skip malformed frames
        finally:
            self._running = False

    async def run_with_reconnect(
        self,
        channels: list[str],
        on_message: Callable[[dict], None],
    ) -> None:
        """Run with auto-reconnect."""
        while self._running:
            try:
                await self.connect()
                for channel in channels:
                    await self.subscribe(channel)

                async for message in self.messages():
                    if message:
                        on_message(message)

            except Exception:
                # Log error and reconnect with backoff
                await asyncio.sleep(5)  # Simple backoff
                continue


class _RealClock:
    """Real system clock implementation."""

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
