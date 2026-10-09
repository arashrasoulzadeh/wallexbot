"""Market and Symbol models for Wallex exchange."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Self

from wallexbot.domain.money import quantize_down


class Symbol(str):
    """Trading pair symbol (e.g., USDTTMN)."""

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise TypeError(f"Symbol must be string, got {type(value).__name__}")
        if not value:
            raise ValueError("Symbol cannot be empty")
        return super().__new__(cls, value.upper())


class Side(str, Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type as per Wallex API."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    STOP_MARKET = "STOP_MARKET"


class OrderStatus(str, Enum):
    """Order status as per Wallex API."""

    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_wire(cls, value: str | None) -> Self:
        """Convert wire value to OrderStatus, mapping unknown to UNKNOWN."""
        if value is None:
            return cls.UNKNOWN
        try:
            return cls(value.upper())
        except ValueError:
            return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class Market:
    """Market information from Wallex /hector/web/v1/markets."""

    symbol: Symbol
    base: str
    quote: str
    price_precision: int
    amount_precision: int
    is_spot: bool

    @classmethod
    def from_api_response(cls, data: dict) -> Self:
        """Create Market from Wallex API response."""
        symbol = Symbol(data["symbol"])
        base = data["baseAsset"]
        quote = data["quoteAsset"]
        is_spot = data.get("isSpot", False)

        price_precision = data.get("pricePrecision")
        amount_precision = data.get("amountPrecision")

        if price_precision is None or amount_precision is None:
            raise ValueError(f"Market {symbol}: missing precision fields")

        if not isinstance(price_precision, int) or not isinstance(amount_precision, int):
            raise ValueError(f"Market {symbol}: precision must be integers")

        if price_precision < 0 or amount_precision < 0:
            raise ValueError(f"Market {symbol}: precision must be non-negative")

        return cls(
            symbol=symbol,
            base=base,
            quote=quote,
            price_precision=price_precision,
            amount_precision=amount_precision,
            is_spot=is_spot,
        )

    @property
    def price_step(self) -> Decimal:
        """Minimum price increment (10^-price_precision)."""
        return Decimal("1") / (Decimal("10") ** self.price_precision)

    @property
    def amount_step(self) -> Decimal:
        """Minimum amount increment (10^-amount_precision)."""
        return Decimal("1") / (Decimal("10") ** self.amount_precision)

    def quantize_price(self, price: Decimal) -> Decimal:
        """Quantize price to market precision (round down)."""
        return quantize_down(price, self.price_step)

    def quantize_amount(self, amount: Decimal) -> Decimal:
        """Quantize amount to market precision (round down)."""
        return quantize_down(amount, self.amount_step)