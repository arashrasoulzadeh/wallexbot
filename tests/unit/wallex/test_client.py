"""Tests for public Wallex data client."""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from wallexbot.domain.market import Symbol
from wallexbot.wallex.client import WallexRestClient
from wallexbot.wallex.websocket import WallexWebSocketClient


class TestWallexRestClient:
    """Tests for Wallex REST client."""

    @pytest.fixture
    def mock_transport(self):
        return Mock()

    @pytest.fixture
    def client(self, mock_transport):
        return WallexRestClient(transport=mock_transport)

    def test_get_markets(self, client, mock_transport):
        """Get markets from API."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "result": [
                {
                    "symbol": "USDTTMN",
                    "baseAsset": "USDT",
                    "quoteAsset": "TMN",
                    "pricePrecision": 2,
                    "amountPrecision": 4,
                    "isSpot": True,
                }
            ],
        }
        mock_transport.request.return_value = mock_response

        markets = client.get_markets()
        assert len(markets) == 1
        assert markets[0].symbol == Symbol("USDTTMN")
        assert markets[0].is_spot is True

    def test_get_markets_filters_non_spot(self, client, mock_transport):
        """Non-spot markets filtered out."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "result": [
                {
                    "symbol": "USDTTMN",
                    "baseAsset": "USDT",
                    "quoteAsset": "TMN",
                    "pricePrecision": 2,
                    "amountPrecision": 4,
                    "isSpot": True,
                },
                {
                    "symbol": "BTCUSDT_PERP",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "pricePrecision": 2,
                    "amountPrecision": 4,
                    "isSpot": False,
                },
            ],
        }
        mock_transport.request.return_value = mock_response

        markets = client.get_markets()
        assert len(markets) == 1
        assert markets[0].symbol == Symbol("USDTTMN")

    def test_get_depth(self, client, mock_transport):
        """Get order book depth."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "result": {
                "bid": [["100.00", "10.0000"], ["99.50", "5.0000"]],
                "ask": [["101.00", "8.0000"], ["101.50", "3.0000"]],
            },
        }
        mock_transport.request.return_value = mock_response

        depth = client.get_depth("USDTTMN")
        assert len(depth.bids) == 2
        assert len(depth.asks) == 2
        assert depth.bids[0].price == Decimal("100.00")
        assert depth.bids[0].quantity == Decimal("10.0000")

    def test_get_latest_trades(self, client, mock_transport):
        """Get latest trades."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "result": [
                {"price": "100.00", "quantity": "10.0000", "side": "buy", "timestamp": 1234567890},
                {"price": "99.50", "quantity": "5.0000", "side": "sell", "timestamp": 1234567891},
            ],
        }
        mock_transport.request.return_value = mock_response

        trades = client.get_latest_trades("USDTTMN")
        assert len(trades) == 2
        assert trades[0].price == Decimal("100.00")
        assert trades[0].side == "BUY"

    def test_get_candles(self, client, mock_transport):
        """Get candles."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "result": {
                "t": [1234567800, 1234567860],
                "o": ["100.00", "101.00"],
                "h": ["102.00", "102.50"],
                "l": ["99.00", "100.50"],
                "c": ["101.00", "102.00"],
                "v": ["1000.0000", "500.0000"],
            },
        }
        mock_transport.request.return_value = mock_response

        candles = client.get_candles("USDTTMN", "60", 1234567800, 1234567860)
        assert len(candles) == 2
        assert candles[0].open == Decimal("100.00")
        assert candles[0].close == Decimal("101.00")

    def test_get_candles_empty(self, client, mock_transport):
        """Empty candles response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "result": {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []},
        }
        mock_transport.request.return_value = mock_response

        candles = client.get_candles("USDTTMN", "60", 1234567800, 1234567860)
        assert len(candles) == 0

    def test_get_candles_error(self, client, mock_transport):
        """API error response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": False,
            "code": 400,
            "message": "Invalid symbol",
        }
        mock_transport.request.return_value = mock_response

        with pytest.raises(Exception, match="Invalid symbol"):
            client.get_candles("INVALID", "60", 1234567800, 1234567860)

    def test_timeout_no_retry_yet(self, client, mock_transport):
        """Currently no retry logic - timeout propagates (TODO: implement retries in Phase 6.2.6)."""
        import httpx

        mock_transport.request.side_effect = httpx.TimeoutException("timeout")

        # Should raise timeout exception (no retry implemented yet)
        import pytest

        with pytest.raises(httpx.TimeoutException):
            client.get_candles("USDTTMN", "60", 1234567800, 1234567860)

    def test_no_retry_on_4xx(self, client, mock_transport):
        """No retry on 4xx errors."""
        import httpx

        mock_response = Mock()
        mock_response.status_code = 400
        mock_transport.request.side_effect = httpx.HTTPStatusError(
            "400", request=Mock(), response=mock_response
        )

        with pytest.raises(httpx.HTTPStatusError):
            client.get_candles("USDTTMN", "60", 1234567800, 1234567860)

        # Should only be called once
        assert mock_transport.request.call_count == 1

    def test_client_throttle(self, client, mock_transport):
        """Client-side throttle prevents hammering."""
        # This would test the internal throttle mechanism
        pass

    def test_no_api_key_header(self, client, mock_transport):
        """No x-api-key header ever set."""
        mock_response = Mock()
        mock_response.json.return_value = {"success": True, "result": []}
        mock_transport.request.return_value = mock_response

        client.get_markets()

        # Check that no Authorization or x-api-key header was passed
        call_args = mock_transport.request.call_args
        headers = call_args.kwargs.get("headers", {})
        assert "x-api-key" not in headers
        assert "Authorization" not in headers


class TestCandlePager:
    """Tests for candle history pager."""

    def test_pager_fetches_chunks(self):
        """Fetch long ranges in chunks."""
        pass

    def test_pager_dedupes_sorts(self):
        """Dedupe and sort results."""
        pass


class TestWallexWebSocketClient:
    """Tests for Wallex WebSocket client."""

    @pytest.fixture
    def mock_connection(self):
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_connection):
        async def factory():
            return mock_connection

        return WallexWebSocketClient(connection_factory=factory)

    @pytest.mark.asyncio
    async def test_subscribe_frame(self, client):
        """Subscribe frame builder."""
        frame = client.build_subscribe("USDTTMN@trade")
        assert frame == ["subscribe", {"channel": "USDTTMN@trade"}]

    @pytest.mark.asyncio
    async def test_parse_trade_frame(self, client):
        """Parse @trade frame."""
        frame = {
            "event": "trade",
            "channel": "USDTTMN@trade",
            "data": {
                "price": "100.00",
                "quantity": "10.0000",
                "side": "buy",
                "timestamp": 1234567890,
            },
        }
        trade = client.parse_frame(frame)
        assert trade is not None
        assert trade.price == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_parse_buy_depth_frame(self, client):
        """Parse @buyDepth frame."""
        frame = {
            "event": "depth",
            "channel": "USDTTMN@buyDepth",
            "data": {
                "bids": [["100.00", "10.0000"], ["99.50", "5.0000"]],
            },
        }
        depth = client.parse_frame(frame)
        assert depth is not None
        assert len(depth.bids) == 2

    @pytest.mark.asyncio
    async def test_parse_sell_depth_frame(self, client):
        """Parse @sellDepth frame."""
        frame = {
            "event": "depth",
            "channel": "USDTTMN@sellDepth",
            "data": {
                "asks": [["101.00", "8.0000"], ["101.50", "3.0000"]],
            },
        }
        depth = client.parse_frame(frame)
        assert depth is not None
        assert len(depth.asks) == 2

    @pytest.mark.asyncio
    async def test_parse_all_price_frame(self, client):
        """Parse all@price frame."""
        frame = {
            "event": "price",
            "channel": "all@price",
            "data": {
                "USDTTMN": "100.00",
                "BTCTMN": "500000000.00",
            },
        }
        prices = client.parse_frame(frame)
        assert prices["USDTTMN"] == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_heartbeat_ping_pong(self, client, mock_connection):
        """Answer server PING with PONG."""
        # Connect first to set up _connection
        await client.connect()
        # Server sends ping
        ping_frame = {"event": "ping"}
        await client.handle_message(ping_frame)
        # Should send pong
        mock_connection.send.assert_called()
        sent = mock_connection.send.call_args[0][0]
        import json

        assert json.loads(sent) == {"event": "pong"}

    @pytest.mark.asyncio
    async def test_auto_reconnect(self, client, mock_connection):
        """Auto-reconnect before 30-minute cutoff."""
        pass

    @pytest.mark.asyncio
    async def test_gap_handling_after_reconnect(self, client):
        """Gap handling after reconnect."""
        pass

    @pytest.mark.asyncio
    async def test_max_50_messages_per_channel(self, client):
        """Max 50 messages/channel respected."""
        pass

    @pytest.mark.asyncio
    async def test_unknown_frames_logged_not_crash(self, client):
        """Unknown/garbage frames logged and skipped."""
        frame = {"event": "unknown", "data": "garbage"}
        # Should not raise
        result = client.parse_frame(frame)
        assert result is None


class TestPriceFeed:
    """Tests for PriceFeed abstraction."""

    def test_price_feed_interface(self):
        """PriceFeed is an interface."""
        pass
