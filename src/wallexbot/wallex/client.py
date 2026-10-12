"""Wallex REST client for public endpoints."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol
import httpx
import time

from wallexbot.wallex.models import Market, Depth, Trade, Candle, OrderBookLevel
from wallexbot.domain.market import Symbol
from wallexbot.domain.money import parse_wire_string
from wallexbot.domain import Clock


class Transport(Protocol):
    """HTTP transport protocol for testing."""

    def request(self, method: str, url: str, **kwargs) -> httpx.Response: ...


@dataclass
class WallexRestClient:
    """Wallex public REST API client."""

    base_url: str = "https://api.wallex.ir"
    transport: Optional[Transport] = None
    clock: Clock = None
    _client: httpx.AsyncClient = None

    def __post_init__(self) -> None:
        if self.clock is None:
            self.clock = _RealClock()

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self.transport is not None:
            # For testing with mock transport
            return self
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make request using mock transport."""
        if self.transport is None:
            raise RuntimeError("No transport available")
        return self.transport.request(method, url, **kwargs)

    def _handle_response(self, response: httpx.Response) -> dict:
        """Handle API response envelope."""
        data = response.json()

        if not data.get("success", True):
            code = data.get("code", "unknown")
            message = data.get("message", "Unknown error")
            raise RuntimeError(f"API error {code}: {message}")

        return data.get("result", {})

    def get_markets(self) -> list[Market]:
        """Get all spot markets."""
        client = self._get_client()
        response = client.request("GET", f"{self.base_url}/hector/web/v1/markets")
        result = self._handle_response(response)

        markets = []
        for item in result:
            if item.get("isSpot", False):
                markets.append(Market(
                    symbol=Symbol(item["symbol"]),
                    base_asset=item["baseAsset"],
                    quote_asset=item["quoteAsset"],
                    price_precision=item["pricePrecision"],
                    amount_precision=item["amountPrecision"],
                    is_spot=item["isSpot"],
                ))
        return markets

    def get_depth(self, symbol: str) -> Depth:
        """Get order book depth for a symbol."""
        client = self._get_client()
        response = client.request("GET", f"{self.base_url}/hector/web/v1/depth", params={"symbol": symbol})
        result = self._handle_response(response)

        bids = [
            OrderBookLevel(price=parse_wire_string(p), quantity=parse_wire_string(q))
            for p, q in result.get("bid", [])
        ]
        asks = [
            OrderBookLevel(price=parse_wire_string(p), quantity=parse_wire_string(q))
            for p, q in result.get("ask", [])
        ]

        return Depth(
            symbol=Symbol(symbol),
            bids=bids,
            asks=asks,
            timestamp=int(self.clock.now() * 1000),
        )

    def get_latest_trades(self, symbol: str, limit: int = 50) -> list[Trade]:
        """Get latest trades for a symbol."""
        client = self._get_client()
        response = client.request(
            "GET",
            f"{self.base_url}/hector/web/v1/trades",
            params={"symbol": symbol, "limit": limit},
        )
        result = self._handle_response(response)

        trades = []
        for item in result:
            trades.append(Trade(
                symbol=Symbol(symbol),
                price=parse_wire_string(item["price"]),
                quantity=parse_wire_string(item["quantity"]),
                side=item["side"].upper(),
                timestamp=item["timestamp"],
            ))
        return trades

    def get_candles(
        self,
        symbol: str,
        resolution: str,
        from_ts: int,
        to_ts: int,
    ) -> list[Candle]:
        """Get candles for a symbol."""
        client = self._get_client()
        response = client.request(
            "GET",
            f"{self.base_url}/hector/web/v1/candles",
            params={
                "symbol": symbol,
                "resolution": resolution,
                "from": from_ts,
                "to": to_ts,
            },
        )
        result = self._handle_response(response)

        # Parse parallel arrays
        timestamps = result.get("t", [])
        opens = result.get("o", [])
        highs = result.get("h", [])
        lows = result.get("l", [])
        closes = result.get("c", [])
        volumes = result.get("v", [])

        candles = []
        for t, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
            candles.append(Candle(
                symbol=Symbol(symbol),
                resolution=resolution,
                open_time=t,
                open=parse_wire_string(o),
                high=parse_wire_string(h),
                low=parse_wire_string(l),
                close=parse_wire_string(c),
                volume=parse_wire_string(v),
            ))

        return candles

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None


class _RealClock:
    """Real system clock implementation."""

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)