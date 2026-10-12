"""Wallex public data models."""

from dataclasses import dataclass
from decimal import Decimal

from wallexbot.domain.market import Symbol


@dataclass(frozen=True, slots=True)
class Market:
    """Market information from Wallex API."""

    symbol: Symbol
    base_asset: str
    quote_asset: str
    price_precision: int
    amount_precision: int
    is_spot: bool
    # market data shown in the coin list (None when Wallex has none, e.g. an inactive market)
    price: Decimal | None = None
    change_24h_pct: Decimal | None = None
    high_24h: Decimal | None = None
    low_24h: Decimal | None = None
    quote_volume_24h: Decimal | None = None
    min_notional_hint: Decimal | None = None  # Wallex's OTC minimum, the closest public hint
    is_zero_fee: bool = False


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """Single level in order book."""

    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class Depth:
    """Order book depth snapshot."""

    symbol: Symbol
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: int


@dataclass(frozen=True, slots=True)
class Trade:
    """Public trade."""

    symbol: Symbol
    price: Decimal
    quantity: Decimal
    side: str  # "buy" or "sell"
    timestamp: int
    trade_id: str | None = None


@dataclass(frozen=True, slots=True)
class Candle:
    """Candlestick data."""

    symbol: Symbol
    resolution: str
    open_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @property
    def close_time(self) -> int:
        """Calculate close time based on resolution."""
        resolution_seconds = {
            "1": 60,
            "15": 900,
            "60": 3600,
            "240": 14400,
            "480": 28800,
            "720": 43200,
            "1D": 86400,
            "2D": 172800,
            "3D": 259200,
        }
        return self.open_time + resolution_seconds.get(self.resolution, 3600)
