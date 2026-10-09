"""Wallex public data models."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from datetime import datetime

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
    trade_id: Optional[str] = None


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