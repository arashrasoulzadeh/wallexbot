"""Fakes of the public Wallex client for CLI tests (real USDTTMN market info, synthetic candles)."""

import json
from decimal import Decimal as D
from pathlib import Path

from wallexbot.domain.market import Symbol
from wallexbot.wallex.models import Candle, Depth, Market, OrderBookLevel, Trade

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wallex"


class FakeClient:
    """Stands in for WallexRestClient with real USDTTMN market info and synthetic candles."""

    def __init__(self, candles: list[Candle] | None = None, markets: list[Market] | None = None):
        raw = json.loads((FIXTURES / "markets.json").read_text(encoding="utf-8"))
        usdttmn = next(m for m in raw["result"]["markets"] if m["symbol"] == "USDTTMN")
        self.markets = (
            markets
            if markets is not None
            else [
                Market(
                    symbol=Symbol("USDTTMN"),
                    base_asset="USDT",
                    quote_asset="TMN",
                    price_precision=usdttmn["price_precision"],
                    amount_precision=usdttmn["amount_precision"],
                    is_spot=True,
                )
            ]
        )
        self.candles = candles if candles is not None else swinging_candles()
        self.requests: list[tuple[str, str, int, int]] = []
        self.trade_requests: list[str] = []
        self.depth_requests: list[str] = []
        self.depth = Depth(
            symbol=Symbol("USDTTMN"),
            timestamp=1_700_000_123_000,
            bids=[
                OrderBookLevel(price=D("262100"), quantity=D("300")),
                OrderBookLevel(price=D("262050"), quantity=D("100")),
            ],
            asks=[
                OrderBookLevel(price=D("262200"), quantity=D("100")),
                OrderBookLevel(price=D("262250"), quantity=D("100")),
            ],
        )
        self.trades: list[Trade] = [
            Trade(
                symbol=Symbol("USDTTMN"),
                price=D("262154"),
                quantity=D("3.5"),
                side="BUY",
                timestamp=1_700_000_123_000,
            )
        ]

    def get_markets(self) -> list[Market]:
        return self.markets

    def get_depth(self, symbol: str) -> Depth:
        self.depth_requests.append(symbol)
        return self.depth

    def get_latest_trades(self, symbol: str, limit: int = 50) -> list[Trade]:
        self.trade_requests.append(symbol)
        return self.trades[:limit]

    def get_candles(self, symbol: str, resolution: str, from_ts: int, to_ts: int) -> list[Candle]:
        self.requests.append((symbol, resolution, from_ts, to_ts))
        return self.candles


def swinging_candles(n: int = 40) -> list[Candle]:
    """Hourly candles swinging between 262,500 and 265,500 (inside the example 261k-267k grid)."""
    out = []
    for i in range(n):
        up = i % 2 == 0
        o, c = (262500, 265500) if up else (265500, 262500)
        out.append(
            Candle(
                symbol=Symbol("USDTTMN"),
                resolution="60",
                open_time=1_700_000_000 + i * 3600,
                open=D(o),
                high=D(max(o, c)),
                low=D(min(o, c)),
                close=D(c),
                volume=D(1000),
            )
        )
    return out


def real_markets() -> list[Market]:
    """All 373 Wallex spot markets exactly as recorded from the live API (tests/fixtures)."""
    import httpx

    class Replay:
        def request(self, method: str, url: str, **kwargs):  # noqa: ANN001, ANN201
            data = json.loads((FIXTURES / "markets_full.json").read_text(encoding="utf-8"))
            return httpx.Response(200, json=data, request=httpx.Request(method, url))

    from wallexbot.wallex.client import WallexRestClient

    return WallexRestClient(transport=Replay()).get_markets()
