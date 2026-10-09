"""Order, OrderRequest, Fill, and Trade models."""

from dataclasses import dataclass, replace
from decimal import Decimal
import re

from wallexbot.domain.market import Symbol, Side, OrderType, OrderStatus
from wallexbot.domain.money import quantize_down


_CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def _validate_client_id(client_id: str) -> None:
    """Validate client_id format."""
    if not client_id:
        raise ValueError("client_id cannot be empty")
    if not _CLIENT_ID_PATTERN.match(client_id):
        raise ValueError(f"client_id must match ^[A-Za-z0-9_]+$, got {client_id!r}")


@dataclass(frozen=True, slots=True)
class Order:
    """Exchange order with full state."""

    id: str
    client_id: str
    symbol: Symbol
    side: Side
    type: OrderType
    price: Decimal
    quantity: Decimal
    status: OrderStatus
    filled_quantity: Decimal
    fee: Decimal
    fee_asset: str
    is_maker: bool
    created_at: int
    updated_at: int

    def __post_init__(self) -> None:
        _validate_client_id(self.client_id)
        if self.filled_quantity < 0:
            raise ValueError("filled_quantity cannot be negative")
        if self.filled_quantity > self.quantity:
            raise ValueError("filled_quantity cannot exceed quantity")
        if self.fee < 0:
            raise ValueError("fee cannot be negative")

    @property
    def remaining_quantity(self) -> Decimal:
        """Quantity remaining to be filled."""
        return self.quantity - self.filled_quantity

    @property
    def filled_percent(self) -> Decimal:
        """Fill ratio (0.0 to 1.0)."""
        if self.quantity == 0:
            return Decimal("0")
        return quantize_down(self.filled_quantity / self.quantity, Decimal("0.00000001"))

    @property
    def is_active(self) -> bool:
        """Whether order can still be filled or canceled."""
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    def with_filled(self, fill_qty: Decimal, fill_fee: Decimal, timestamp: int) -> "Order":
        """Return new order with additional fill applied."""
        if fill_qty <= 0:
            raise ValueError("fill_qty must be positive")
        if fill_qty > self.remaining_quantity:
            raise ValueError("fill_qty exceeds remaining quantity")

        new_filled = self.filled_quantity + fill_qty
        new_fee = self.fee + fill_fee

        if new_filled >= self.quantity:
            new_status = OrderStatus.FILLED
        else:
            new_status = OrderStatus.PARTIALLY_FILLED

        return replace(
            self,
            filled_quantity=new_filled,
            fee=new_fee,
            status=new_status,
            updated_at=timestamp,
        )

    def with_canceled(self, timestamp: int) -> "Order":
        """Return new order marked as canceled."""
        if not self.is_active:
            raise ValueError("Cannot cancel inactive order")
        return replace(self, status=OrderStatus.CANCELED, updated_at=timestamp)

    def with_rejected(self, timestamp: int) -> "Order":
        """Return new order marked as rejected."""
        return replace(self, status=OrderStatus.REJECTED, updated_at=timestamp)


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Order request from strategy to exchange."""

    client_id: str
    symbol: Symbol
    side: Side
    type: OrderType
    price: Decimal | None  # None for MARKET orders
    quantity: Decimal
    stop_price: Decimal | None = None  # For STOP_* orders

    def __post_init__(self) -> None:
        _validate_client_id(self.client_id)
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and self.price is None:
            raise ValueError(f"{self.type} order requires price")
        if self.type in (OrderType.STOP_LIMIT, OrderType.STOP_MARKET) and self.stop_price is None:
            raise ValueError(f"{self.type} order requires stop_price")
        if self.type == OrderType.MARKET and self.price is not None:
            raise ValueError("MARKET order must not have price")


@dataclass(frozen=True, slots=True)
class Fill:
    """Execution fill from exchange."""

    order_id: str
    trade_id: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    fee_asset: str
    is_maker: bool
    timestamp: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.price < 0:
            raise ValueError("price cannot be negative")
        if self.fee < 0:
            raise ValueError("fee cannot be negative")

    @property
    def quote_value(self) -> Decimal:
        """Total quote value of this fill (price * quantity)."""
        return self.price * self.quantity


@dataclass(frozen=True, slots=True)
class Trade:
    """Public trade tick from market data."""

    symbol: Symbol
    price: Decimal
    quantity: Decimal
    side: Side  # Aggressor side
    timestamp: int
    trade_id: str

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.price < 0:
            raise ValueError("price cannot be negative")