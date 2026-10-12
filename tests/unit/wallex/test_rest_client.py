"""REST client against REAL recorded Wallex responses (tests/fixtures/wallex/*.json).

The fixtures were captured from the public endpoints (no API key). If Wallex changes a shape,
refresh them and these tests will show what moved.
"""

import json
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import httpx
import pytest

from wallexbot.domain.market import Symbol
from wallexbot.wallex.client import WallexApiError, WallexRestClient

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "wallex"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeTransport:
    """Returns canned httpx responses and records every request."""

    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.status = status
        self.body = body
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append((method, url, kwargs))
        return httpx.Response(self.status, json=self.body, request=httpx.Request(method, url))


def client_for(body: Any, status: int = 200) -> tuple[WallexRestClient, FakeTransport]:
    transport = FakeTransport(status, body)
    return WallexRestClient(transport=transport), transport


def test_get_markets_parses_real_response_and_keeps_only_spot():
    client, transport = client_for(load("markets.json"))

    markets = client.get_markets()

    assert transport.calls[0][1] == "https://api.wallex.ir/hector/web/v1/markets"
    assert [m.symbol for m in markets] == [
        Symbol("USDTTMN"),
        Symbol("BTCUSDT"),
    ]  # ORAITMN is not spot
    usdttmn = markets[0]
    assert (usdttmn.base_asset, usdttmn.quote_asset) == ("USDT", "TMN")
    assert (usdttmn.price_precision, usdttmn.amount_precision) == (0, 2)
    assert usdttmn.is_spot is True


def test_get_depth_parses_numeric_prices_best_first():
    client, transport = client_for(load("depth_usdttmn.json"))

    depth = client.get_depth("USDTTMN")

    method, url, kwargs = transport.calls[0]
    assert url == "https://api.wallex.ir/v1/depth"
    assert kwargs["params"] == {"symbol": "USDTTMN"}
    raw = load("depth_usdttmn.json")["result"]
    assert depth.asks[0].price == D(str(raw["ask"][0]["price"]))
    assert depth.asks[0].quantity == D(str(raw["ask"][0]["quantity"]))
    assert depth.bids[0].price == D(str(raw["bid"][0]["price"]))
    assert len(depth.asks) == len(raw["ask"]) and len(depth.bids) == len(raw["bid"])
    assert depth.bids[0].price < depth.asks[0].price  # not crossed


def test_get_latest_trades_parses_strings_side_and_iso_timestamp():
    client, transport = client_for(load("trades_usdttmn.json"))

    trades = client.get_latest_trades("USDTTMN")

    assert transport.calls[0][1] == "https://api.wallex.ir/v1/trades"
    raw = load("trades_usdttmn.json")["result"]["latestTrades"]
    assert len(trades) == len(raw)
    first = trades[0]
    assert first.price == D(raw[0]["price"])
    assert first.quantity == D(raw[0]["quantity"])
    assert first.side == ("BUY" if raw[0]["isBuyOrder"] else "SELL")
    assert first.timestamp == 1_791_797_311_000 or first.timestamp > 1_700_000_000_000  # ms epoch


def test_get_latest_trades_limit_is_applied():
    client, _ = client_for(load("trades_usdttmn.json"))
    assert len(client.get_latest_trades("USDTTMN", limit=2)) == 2


def test_get_candles_parses_parallel_arrays():
    client, transport = client_for(load("candles_usdttmn_15.json"))

    candles = client.get_candles("USDTTMN", "15", 1, 2)

    method, url, kwargs = transport.calls[0]
    assert url == "https://api.wallex.ir/v1/udf/history"
    assert kwargs["params"] == {"symbol": "USDTTMN", "resolution": "15", "from": 1, "to": 2}
    raw = load("candles_usdttmn_15.json")
    assert len(candles) == len(raw["t"])
    assert candles[0].open_time == raw["t"][0]
    assert candles[0].close == D(raw["c"][0])
    assert candles[0].volume == D(raw["v"][0])
    assert all(c.symbol == Symbol("USDTTMN") for c in candles)


def test_get_candles_no_data_returns_empty_list():
    client, _ = client_for({"s": "no_data"})
    assert client.get_candles("USDTTMN", "60", 1, 2) == []


def test_get_candles_mismatched_arrays_raise_a_clear_error():
    client, _ = client_for(
        {"s": "ok", "t": [1, 2], "o": ["1"], "h": ["1"], "l": ["1"], "c": ["1"], "v": ["1"]}
    )
    with pytest.raises(WallexApiError, match="mismatched"):
        client.get_candles("USDTTMN", "60", 1, 2)


def test_envelope_error_raises_with_code_and_message():
    client, _ = client_for({"success": False, "code": 400, "message": "Invalid symbol"})
    with pytest.raises(WallexApiError, match="Invalid symbol"):
        client.get_depth("NOPE")


def test_http_error_status_raises_and_is_not_retried():
    client, transport = client_for({"message": "unauthorized"}, status=401)
    with pytest.raises(WallexApiError, match="401"):
        client.get_markets()
    assert len(transport.calls) == 1


def test_timeout_propagates():
    class Timeout:
        def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            raise httpx.TimeoutException("timeout")

    with pytest.raises(httpx.TimeoutException):
        WallexRestClient(transport=Timeout()).get_markets()


def test_no_auth_headers_are_ever_sent():
    client, transport = client_for(load("markets.json"))
    client.get_markets()
    headers = {k.lower() for k in transport.calls[0][2].get("headers", {})}
    assert not headers & {"x-api-key", "authorization"}


def test_markets_carry_price_volume_and_the_minimum_order_hint():
    client, _ = client_for(load("markets_full.json"))
    markets = {m.symbol: m for m in client.get_markets()}

    usdt = markets[Symbol("USDTTMN")]
    assert usdt.price is not None and usdt.price > 0
    assert (
        usdt.high_24h >= usdt.low_24h > 0
    )  # (the live price can sit a hair outside a lagging 24 h range)
    assert usdt.quote_volume_24h > 0 and usdt.min_notional_hint == D("90000")
    assert markets[Symbol("BTCUSDT")].min_notional_hint == D("2")


def test_every_spot_market_is_returned_including_ones_without_a_price():
    client, _ = client_for(load("markets_full.json"))
    markets = client.get_markets()
    assert len(markets) == 373
    assert {m.quote_asset for m in markets} == {"TMN", "USDT"}
    assert any(
        m.price is None for m in markets
    )  # inactive markets have no price: kept, not crashed on
