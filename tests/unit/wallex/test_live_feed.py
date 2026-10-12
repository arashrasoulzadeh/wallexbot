"""Live price feeds: public WebSocket trades, with REST polling as the alternative."""

import asyncio
import json
from decimal import Decimal as D
from typing import Any

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.domain.market import Symbol
from wallexbot.wallex.client import WallexApiError
from wallexbot.wallex.live_feed import RestPollingFeed, WebSocketTradeFeed
from wallexbot.wallex.models import Trade
from wallexbot.wallex.websocket import WallexWebSocketClient

SYMBOL = Symbol("USDTTMN")


def trade_frame(price: str, ts: str, symbol: str = "USDTTMN") -> str:
    return json.dumps(
        [
            f"{symbol}@trade",
            {"isBuyOrder": True, "quantity": "1.5", "price": price, "timestamp": ts},
        ]
    )


class HangingConnection:
    """Delivers queued messages, then waits forever (like an idle but healthy socket)."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None: ...

    def __aiter__(self) -> "HangingConnection":
        return self

    async def __anext__(self) -> str:
        if self.messages:
            return self.messages.pop(0)
        await asyncio.Event().wait()
        raise StopAsyncIteration


class TestWebSocketTradeFeed:
    async def test_trades_become_live_ticks_and_the_right_channel_is_subscribed(self):
        conn = HangingConnection(
            [
                trade_frame("264000", "2026-10-12T09:00:00Z"),
                json.dumps(
                    ["all@price", {"symbol": "BTCUSDT", "price": "1", "24h_ch": 0}]
                ),  # ignored
                trade_frame("264010", "2026-10-12T09:00:05Z"),
            ]
        )

        async def factory() -> HangingConnection:
            return conn

        feed = WebSocketTradeFeed(SYMBOL, WallexWebSocketClient(connection_factory=factory))
        got = []
        async for tick in feed.ticks():
            got.append(tick)
            if len(got) == 2:
                break
        await feed.close()

        assert [t.price for t in got] == [D("264000"), D("264010")]
        assert all(t.symbol == SYMBOL and t.source == "live" for t in got)
        assert got[1].timestamp - got[0].timestamp == 5000
        assert json.loads(conn.sent[0]) == ["subscribe", {"channel": "USDTTMN@trade"}]

    async def test_trades_of_other_markets_are_ignored(self):
        conn = HangingConnection(
            [
                trade_frame("1", "2026-10-12T09:00:00Z", symbol="BTCUSDT"),
                trade_frame("264000", "2026-10-12T09:00:01Z"),
            ]
        )

        async def factory() -> HangingConnection:
            return conn

        feed = WebSocketTradeFeed(SYMBOL, WallexWebSocketClient(connection_factory=factory))
        async for tick in feed.ticks():
            assert tick.price == D("264000")
            break
        await feed.close()

    async def test_close_ends_the_stream(self):
        async def factory() -> HangingConnection:
            return HangingConnection([])

        feed = WebSocketTradeFeed(SYMBOL, WallexWebSocketClient(connection_factory=factory))

        async def consume() -> list[Any]:
            return [t async for t in feed.ticks()]

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        await feed.close()
        assert await asyncio.wait_for(task, 1) == []

    async def test_a_crash_in_the_socket_task_reaches_the_consumer(self):
        async def factory() -> HangingConnection:
            raise RuntimeError("bug in the socket layer")  # not a network error: must not be hidden

        feed = WebSocketTradeFeed(SYMBOL, WallexWebSocketClient(connection_factory=factory))
        with pytest.raises(RuntimeError, match="bug in the socket layer"):
            async for _ in feed.ticks():
                pass
        await feed.close()


class FakeRest:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls = 0

    def get_latest_trades(self, symbol: str, limit: int = 50) -> list[Trade]:
        self.calls += 1
        item = self.script.pop(0) if self.script else self.script_last
        if isinstance(item, Exception):
            raise item
        self.script_last = item
        return item


def trade(price: str, ts: int) -> Trade:
    return Trade(symbol=SYMBOL, price=D(price), quantity=D("1"), side="BUY", timestamp=ts)


class TestRestPollingFeed:
    async def test_only_new_trades_become_ticks(self):
        rest = FakeRest(
            [
                [trade("264000", 1000)],
                [trade("264000", 1000)],  # nothing new
                [trade("264020", 2000)],
            ]
        )
        feed = RestPollingFeed(SYMBOL, rest, interval=2.0, clock=FakeClock())
        got = []
        async for tick in feed.ticks():
            got.append(tick)
            if len(got) == 2:
                break
        await feed.close()

        assert [(t.price, t.timestamp) for t in got] == [(D("264000"), 1000), (D("264020"), 2000)]
        assert rest.calls == 3 and all(t.source == "live" for t in got)

    async def test_api_errors_are_retried_not_fatal(self):
        rest = FakeRest(
            [WallexApiError("HTTP 503"), OSError("network down"), [trade("264000", 1000)]]
        )
        feed = RestPollingFeed(SYMBOL, rest, interval=1.0, clock=FakeClock())
        async for tick in feed.ticks():
            assert tick.price == D("264000")
            break
        await feed.close()
        assert rest.calls == 3

    async def test_it_waits_one_interval_between_polls(self):
        clock = FakeClock()
        rest = FakeRest([[trade("1", 1)], [trade("2", 2)], [trade("3", 3)]])
        feed = RestPollingFeed(SYMBOL, rest, interval=2.0, clock=clock)
        start = clock.now()
        n = 0
        async for _ in feed.ticks():
            n += 1
            if n == 3:
                break
        await feed.close()
        assert clock.now() - start == 4.0  # two sleeps between three polls
