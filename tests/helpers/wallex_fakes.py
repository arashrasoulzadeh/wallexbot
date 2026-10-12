"""Fakes of the public Wallex client for CLI tests (real USDTTMN market info, synthetic candles)."""

import json
from decimal import Decimal as D
from pathlib import Path

from wallexbot.domain.market import Symbol
from wallexbot.wallex.models import Candle, Market

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

    def get_markets(self) -> list[Market]:
        return self.markets

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
