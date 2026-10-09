"""Fee schedule and minimum notional/quantity rules."""

from dataclasses import dataclass
from decimal import Decimal

from wallexbot.domain.market import Side


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    """Maker/taker fee rates."""

    maker_rate: Decimal
    taker_rate: Decimal

    def __post_init__(self) -> None:
        if self.maker_rate < 0:
            raise ValueError("maker_rate cannot be negative")
        if self.taker_rate < 0:
            raise ValueError("taker_rate cannot be negative")

    def calculate_fee(
        self, price: Decimal, quantity: Decimal, side: Side, is_maker: bool
    ) -> Decimal:
        """
        Calculate fee for an order.

        For BUY orders: fee is in quote asset (price * quantity * rate)
        For SELL orders: fee is in base asset (quantity * rate)
        """
        if price < 0 or quantity <= 0:
            raise ValueError("price must be non-negative, quantity must be positive")

        rate = self.maker_rate if is_maker else self.taker_rate

        if side == Side.BUY:
            # Fee in quote asset
            return (price * quantity * rate).quantize(Decimal("0.00000001"))
        else:
            # Fee in base asset
            return (quantity * rate).quantize(Decimal("0.00000001"))

    def calculate_fee_quote(self, quote_value: Decimal, is_maker: bool) -> Decimal:
        """Calculate fee for a quote value (for BUY orders)."""
        rate = self.maker_rate if is_maker else self.taker_rate
        return (quote_value * rate).quantize(Decimal("0.00000001"))

    def calculate_fee_base(self, base_quantity: Decimal, is_maker: bool) -> Decimal:
        """Calculate fee for a base quantity (for SELL orders)."""
        rate = self.maker_rate if is_maker else self.taker_rate
        return (base_quantity * rate).quantize(Decimal("0.00000001"))


@dataclass(frozen=True, slots=True)
class MinNotionalRule:
    """Minimum notional and quantity rules for a market."""

    min_notional: Decimal
    min_quantity: Decimal

    def __post_init__(self) -> None:
        if self.min_notional < 0:
            raise ValueError("min_notional cannot be negative")
        if self.min_quantity < 0:
            raise ValueError("min_quantity cannot be negative")

    def check(self, price: Decimal, quantity: Decimal) -> bool:
        """Check if order meets minimum requirements."""
        notional = price * quantity
        return notional >= self.min_notional and quantity >= self.min_quantity

    def validate(self, price: Decimal, quantity: Decimal) -> tuple[bool, str]:
        """Validate order and return (ok, error_message)."""
        notional = price * quantity
        if notional < self.min_notional:
            return False, f"Notional {notional} below minimum {self.min_notional}"
        if quantity < self.min_quantity:
            return False, f"Quantity {quantity} below minimum {self.min_quantity}"
        return True, ""