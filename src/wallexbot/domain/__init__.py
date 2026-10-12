"""Domain package for Wallex Grid Bot."""

from wallexbot.domain.balance import Balance
from wallexbot.domain.clock import Clock, SystemClock
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import (
    Market,
    OrderStatus,
    OrderType,
    Side,
    Symbol,
)
from wallexbot.domain.money import (
    parse_wire_string,
    quantize_down,
    quantize_to_precision,
)
from wallexbot.domain.order import (
    Fill,
    Order,
    OrderRequest,
    Trade,
)

__all__ = [
    "quantize_down",
    "quantize_to_precision",
    "parse_wire_string",
    "Symbol",
    "Market",
    "Side",
    "OrderType",
    "OrderStatus",
    "Order",
    "OrderRequest",
    "Fill",
    "Trade",
    "Balance",
    "FeeSchedule",
    "MinNotionalRule",
    "Clock",
    "SystemClock",
]
