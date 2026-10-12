"""Wallex REST client for public endpoints (no API key is ever sent).

Response shapes were verified against the live public API; recorded samples live in
tests/fixtures/wallex/. See docs/wallex-api.md for the endpoint reference.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

import httpx

from wallexbot.domain import Clock, SystemClock
from wallexbot.domain.market import Symbol
from wallexbot.domain.money import parse_wire_string
from wallexbot.wallex.models import Candle, Depth, Market, OrderBookLevel, Trade


class WallexApiError(RuntimeError):
    """The API answered with an error (HTTP status >= 400 or `success: false`)."""


class Transport(Protocol):
    """HTTP transport protocol, so tests can inject canned responses."""

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response: ...


def _decimal(value: Any) -> Decimal:
    """Parse a JSON number or numeric string into a Decimal without float artefacts."""
    return parse_wire_string(str(value))


def _optional_decimal(value: Any) -> Decimal | None:
    """A decimal from a JSON value, or None for a missing / zero / non-numeric one."""
    if value in (None, "", 0, "0", "0.0"):
        return None
    try:
        parsed = _decimal(value)
    except Exception:  # an unparsable number is "no data", not a crash
        return None
    return parsed if parsed > 0 else None


def _iso_to_ms(value: str) -> int:
    """'2026-10-12T09:28:31Z' -> epoch milliseconds."""
    return int(
        datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).timestamp() * 1000
    )


@dataclass
class WallexRestClient:
    """Wallex public REST API client."""

    base_url: str = "https://api.wallex.ir"
    transport: Transport | None = None
    clock: Clock = field(default_factory=SystemClock)
    _http: httpx.Client | None = field(default=None, repr=False)

    # --- plumbing -----------------------------------------------------------------

    def _request(self, path: str, params: dict[str, Any]) -> Any:
        """GET `path` and return the decoded JSON body, raising WallexApiError on failure."""
        url = f"{self.base_url}{path}"
        if self.transport is not None:
            response = self.transport.request("GET", url, params=params)
        else:
            if self._http is None:
                self._http = httpx.Client(timeout=30.0)
            response = self._http.request("GET", url, params=params)

        if response.status_code >= 400:
            raise WallexApiError(f"HTTP {response.status_code} for {path}: {response.text[:200]}")
        return response.json()

    @staticmethod
    def _unwrap(body: Any) -> Any:
        """Strip the {success, message, result} envelope, raising on `success: false`."""
        if isinstance(body, dict) and body.get("success") is False:
            raise WallexApiError(
                f"API error {body.get('code', 'unknown')}: {body.get('message', 'Unknown error')}"
            )
        if isinstance(body, dict) and "result" in body:
            return body["result"]
        return body

    # --- endpoints ------------------------------------------------------------------

    def get_markets(self) -> list[Market]:
        """All spot markets (`GET /hector/web/v1/markets`, `result.markets[]`)."""
        result = self._unwrap(self._request("/hector/web/v1/markets", {}))
        return [
            Market(
                symbol=Symbol(item["symbol"]),
                base_asset=item["base_asset"],
                quote_asset=item["quote_asset"],
                price_precision=int(item["price_precision"]),
                amount_precision=int(item["amount_precision"]),
                is_spot=bool(item["is_spot"]),
                price=_optional_decimal(item.get("price")),
                change_24h_pct=None
                if item.get("change_24h") is None
                else _decimal(item["change_24h"]),
                high_24h=_optional_decimal(item.get("highest_24h_price")),
                low_24h=_optional_decimal(item.get("lowest_24h_price")),
                quote_volume_24h=_optional_decimal(item.get("quote_volume_24h")),
                min_notional_hint=_optional_decimal(item.get("otc_min_notional")),
                is_zero_fee=bool(item.get("is_zero_fee")),
            )
            for item in result["markets"]
            if item.get("is_spot")
        ]

    def get_depth(self, symbol: str) -> Depth:
        """Order book (`GET /v1/depth`): `result.bid` / `result.ask`, best price first."""
        result = self._unwrap(self._request("/v1/depth", {"symbol": symbol}))

        def levels(rows: list[dict[str, Any]]) -> list[OrderBookLevel]:
            return [
                OrderBookLevel(price=_decimal(r["price"]), quantity=_decimal(r["quantity"]))
                for r in rows
            ]

        return Depth(
            symbol=Symbol(symbol),
            bids=levels(result.get("bid", [])),
            asks=levels(result.get("ask", [])),
            timestamp=int(self.clock.now() * 1000),
        )

    def get_latest_trades(self, symbol: str, limit: int = 50) -> list[Trade]:
        """Latest public trades (`GET /v1/trades`, `result.latestTrades[]`), newest first."""
        result = self._unwrap(self._request("/v1/trades", {"symbol": symbol}))
        return [
            Trade(
                symbol=Symbol(symbol),
                price=_decimal(item["price"]),
                quantity=_decimal(item["quantity"]),
                side="BUY" if item["isBuyOrder"] else "SELL",
                timestamp=_iso_to_ms(item["timestamp"]),
            )
            for item in result["latestTrades"][:limit]
        ]

    def get_candles(self, symbol: str, resolution: str, from_ts: int, to_ts: int) -> list[Candle]:
        """OHLC candles (`GET /v1/udf/history`): parallel arrays t/o/h/l/c/v, UTC seconds."""
        body = self._request(
            "/v1/udf/history",
            {"symbol": symbol, "resolution": resolution, "from": from_ts, "to": to_ts},
        )
        if isinstance(body, dict) and body.get("success") is False:
            self._unwrap(body)  # raises
        status = body.get("s")
        if status == "no_data":
            return []
        if status != "ok":
            raise WallexApiError(f"unexpected candle status {status!r}")

        columns = [body.get(k, []) for k in ("t", "o", "h", "l", "c", "v")]
        if len({len(col) for col in columns}) != 1:
            raise WallexApiError("candle response has mismatched array lengths")

        return [
            Candle(
                symbol=Symbol(symbol),
                resolution=resolution,
                open_time=int(t),
                open=_decimal(o),
                high=_decimal(h),
                low=_decimal(low),
                close=_decimal(c),
                volume=_decimal(v),
            )
            for t, o, h, low, c, v in zip(*columns, strict=True)
        ]

    def close(self) -> None:
        """Close the HTTP client."""
        if self._http is not None:
            self._http.close()
            self._http = None
