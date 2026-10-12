"""Tests for the public Wallex WebSocket client.

Frame shapes come from the Wallex docs (docs/offline/pages/socket-*.md): every message is a JSON
array `[channel, payload]`, e.g. `["USDTTMN@trade", {...}]`.
"""

import json
from decimal import Decimal as D
from typing import Any

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.domain.market import Symbol
from wallexbot.wallex.models import Depth, Trade
from wallexbot.wallex.websocket import WallexWebSocketClient


class FakeConnection:
    """Async-iterable websocket stand-in: yields queued raw messages, then maybe raises."""

    def __init__(self, messages: list[str], then_raise: Exception | None = None) -> None:
        self.messages = list(messages)
        self.then_raise = then_raise
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self) -> "FakeConnection":
        return self

    async def __anext__(self) -> str:
        if self.messages:
            return self.messages.pop(0)
        if self.then_raise is not None:
            raise self.then_raise
        raise StopAsyncIteration


def make_client(*connections: FakeConnection, clock: FakeClock | None = None):
    pending = list(connections)

    async def factory() -> FakeConnection:
        return pending.pop(0)

    return WallexWebSocketClient(connection_factory=factory, clock=clock or FakeClock())


TRADE = [
    "USDTTMN@trade",
    {
        "isBuyOrder": True,
        "quantity": "255.7500000000000000",
        "price": "82131.0000000000000000",
        "timestamp": "2025-06-01T09:33:41Z",
    },
]
BUY_DEPTH = [
    "USDTTMN@buyDepth",
    [
        {"quantity": 255.75, "price": 82131, "sum": 21005003.25},
        {"quantity": 103.07, "price": 82083, "sum": 8460294.81},
    ],
]
SELL_DEPTH = ["USDTTMN@sellDepth", [{"quantity": 8, "price": 82200, "sum": 657600}]]
PRICE = ["all@price", {"symbol": "PEPEUSDT", "price": "0.00001136", "24h_ch": 1.15}]


class TestFrames:
    def test_subscribe_and_unsubscribe_frames(self):
        client = make_client()
        assert client.build_subscribe("USDTTMN@trade") == [
            "subscribe",
            {"channel": "USDTTMN@trade"},
        ]
        assert client.build_unsubscribe("USDTTMN@trade") == [
            "unsubscribe",
            {"channel": "USDTTMN@trade"},
        ]

    def test_trade_frame(self):
        trade = make_client().parse_frame(TRADE)
        assert isinstance(trade, Trade)
        assert trade.symbol == Symbol("USDTTMN")
        assert (trade.price, trade.quantity) == (D("82131"), D("255.75"))
        assert trade.side == "BUY"
        assert trade.timestamp == 1_748_770_421_000  # 2025-06-01T09:33:41Z in ms

    def test_sell_side_trade(self):
        frame = ["USDTTMN@trade", {**TRADE[1], "isBuyOrder": False}]
        assert make_client().parse_frame(frame).side == "SELL"

    def test_buy_depth_frame_fills_bids(self):
        depth = make_client().parse_frame(BUY_DEPTH)
        assert isinstance(depth, Depth)
        assert [b.price for b in depth.bids] == [D("82131"), D("82083")]
        assert depth.bids[0].quantity == D("255.75")
        assert depth.asks == []

    def test_sell_depth_frame_fills_asks(self):
        depth = make_client().parse_frame(SELL_DEPTH)
        assert [a.price for a in depth.asks] == [D("82200")]
        assert depth.bids == []

    def test_all_price_frame(self):
        assert make_client().parse_frame(PRICE) == {Symbol("PEPEUSDT"): D("0.00001136")}

    @pytest.mark.parametrize(
        "garbage",
        [
            {"event": "unknown"},
            [],
            ["x"],
            ["USDTTMN@other", {}],
            "text",
            42,
            None,
            ["USDTTMN@trade", {"unexpected": 1}],
        ],
    )
    def test_unknown_or_malformed_frames_are_skipped_not_raised(self, garbage: Any):
        assert make_client().parse_frame(garbage) is None


class TestRealWebsocketsExceptions:
    async def test_reconnects_after_the_websockets_library_reports_a_closed_connection(self):
        from websockets.exceptions import ConnectionClosedError

        first = FakeConnection([json.dumps(TRADE)], then_raise=ConnectionClosedError(None, None))
        second = FakeConnection([json.dumps(PRICE)])
        client = make_client(first, second)
        seen: list[Any] = []

        def on_message(message: Any) -> None:
            seen.append(message)
            if len(seen) == 2:
                client.stop()

        await client.run_with_reconnect(["all@price"], on_message)

        assert len(seen) == 2


class TestStreaming:
    async def test_messages_yields_parsed_frames_and_skips_bad_json(self):
        conn = FakeConnection([json.dumps(TRADE), "not json {{", json.dumps(PRICE)])
        client = make_client(conn)

        got = [m async for m in client.messages()]

        assert isinstance(got[0], Trade)
        assert got[1] == {Symbol("PEPEUSDT"): D("0.00001136")}
        assert len(got) == 2

    async def test_subscribe_sends_the_documented_frame(self):
        conn = FakeConnection([])
        client = make_client(conn)
        await client.subscribe("USDTTMN@trade")
        assert json.loads(conn.sent[0]) == ["subscribe", {"channel": "USDTTMN@trade"}]

    async def test_reconnects_after_a_drop_and_resubscribes_to_all_channels(self):
        first = FakeConnection([json.dumps(TRADE)], then_raise=ConnectionError("dropped"))
        second = FakeConnection([json.dumps(PRICE)])
        client = make_client(first, second)
        seen: list[Any] = []

        def on_message(message: Any) -> None:
            seen.append(message)
            if len(seen) == 2:
                client.stop()

        await client.run_with_reconnect(["USDTTMN@trade", "all@price"], on_message)

        assert len(seen) == 2
        for conn in (first, second):
            subs = [json.loads(s)[1]["channel"] for s in conn.sent]
            assert subs == ["USDTTMN@trade", "all@price"]

    async def test_connection_is_rotated_before_the_30_minute_server_cutoff(self):
        clock = FakeClock()
        conn1 = FakeConnection([json.dumps(TRADE), json.dumps(TRADE)])
        conn2 = FakeConnection([json.dumps(PRICE)])
        client = make_client(conn1, conn2, clock=clock)
        seen: list[Any] = []

        def on_message(message: Any) -> None:
            seen.append(message)
            if len(seen) == 1:
                clock.advance(26 * 60)  # past the 25-minute rotation point
            if len(seen) == 2:
                client.stop()

        await client.run_with_reconnect(
            ["USDTTMN@trade"], on_message, max_connection_seconds=25 * 60
        )

        assert conn1.closed  # rotated deliberately, one message still unread
        assert len(seen) == 2 and isinstance(seen[1], dict)

    async def test_backoff_grows_while_the_server_is_unreachable(self):
        clock = FakeClock()
        calls = 0

        async def factory() -> FakeConnection:
            nonlocal calls
            calls += 1
            if calls < 4:
                raise OSError("unreachable")
            return FakeConnection([json.dumps(PRICE)])

        client = WallexWebSocketClient(connection_factory=factory, clock=clock)
        start = clock.now()
        seen: list[Any] = []

        def on_message(message: Any) -> None:
            seen.append(message)
            client.stop()

        await client.run_with_reconnect(["all@price"], on_message)

        assert calls == 4 and len(seen) == 1
        assert clock.now() - start == 1 + 2 + 4  # exponential backoff: 1s, 2s, 4s
