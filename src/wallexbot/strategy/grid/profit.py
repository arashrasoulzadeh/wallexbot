"""Profit accounting for grid strategy."""

from dataclasses import dataclass, field
from decimal import Decimal

from wallexbot.domain.fees import FeeSchedule
from wallexbot.domain.market import Side


def calculate_cycle_profit(
    buy_price: Decimal,
    sell_price: Decimal,
    quantity: Decimal,
    fee_schedule: FeeSchedule,
    buy_is_maker: bool = True,
    sell_is_maker: bool = True,
) -> Decimal:
    """
    Calculate net profit for a completed grid cycle (buy -> sell).

    Args:
        buy_price: Price at which base was bought
        sell_price: Price at which base was sold
        quantity: Base quantity traded
        fee_schedule: Fee rates
        buy_is_maker: Whether buy order was maker
        sell_is_maker: Whether sell order was maker

    Returns:
        Net profit in quote asset
    """
    # Buy side: pay quote, receive base, fee in quote
    buy_cost = buy_price * quantity
    buy_fee = fee_schedule.calculate_fee(buy_price, quantity, Side.BUY, buy_is_maker)
    total_buy_cost = buy_cost + buy_fee

    # Sell side: receive quote, pay base, fee in base
    sell_revenue = sell_price * quantity
    sell_fee_base = fee_schedule.calculate_fee(sell_price, quantity, Side.SELL, sell_is_maker)
    # Convert sell fee to quote equivalent
    sell_fee_quote = sell_fee_base * sell_price
    net_sell_revenue = sell_revenue - sell_fee_quote

    return net_sell_revenue - total_buy_cost


@dataclass
class ProfitTracker:
    """Track realized profit across grid cycles."""

    total_cycles: int = 0
    total_profit: Decimal = field(default_factory=lambda: Decimal("0"))
    total_fees_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    cycle_profits: list[Decimal] = field(default_factory=list)

    def record_cycle(
        self,
        buy_price: Decimal,
        sell_price: Decimal,
        quantity: Decimal,
        buy_fee: Decimal,
        sell_fee: Decimal,
        buy_fee_asset: str,
        sell_fee_asset: str,
    ) -> Decimal:
        """Record a completed cycle and return its profit."""
        # Convert fees to quote equivalent for profit calculation
        buy_fee_quote = buy_fee if buy_fee_asset != "USDT" else buy_fee * buy_price
        sell_fee_quote = sell_fee if sell_fee_asset != "USDT" else sell_fee * sell_price

        buy_cost = buy_price * quantity + buy_fee_quote
        sell_revenue = sell_price * quantity - sell_fee_quote
        profit = sell_revenue - buy_cost

        self.total_cycles += 1
        self.total_profit += profit
        self.total_fees_paid += buy_fee_quote + sell_fee_quote
        self.cycle_profits.append(profit)

        return profit

    def average_profit_per_cycle(self) -> Decimal:
        """Calculate average profit per cycle."""
        if self.total_cycles == 0:
            return Decimal("0")
        return self.total_profit / self.total_cycles