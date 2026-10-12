"""Grid strategy parameters and level generation."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from wallexbot.domain.money import quantize_down


class GridMode(str, Enum):
    """Grid spacing mode."""

    ARITHMETIC = "arithmetic"
    GEOMETRIC = "geometric"


@dataclass(frozen=True, slots=True)
class GridParameters:
    """Grid trading parameters."""

    lower_price: Decimal
    upper_price: Decimal
    grid_count: int
    mode: GridMode
    total_investment: Decimal
    per_grid_qty: Decimal | None = None
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None

    def __post_init__(self) -> None:
        # Convert string inputs to Decimal
        object.__setattr__(self, "lower_price", Decimal(str(self.lower_price)))
        object.__setattr__(self, "upper_price", Decimal(str(self.upper_price)))
        object.__setattr__(self, "total_investment", Decimal(str(self.total_investment)))
        if self.per_grid_qty is not None:
            object.__setattr__(self, "per_grid_qty", Decimal(str(self.per_grid_qty)))
        if self.stop_loss_price is not None:
            object.__setattr__(self, "stop_loss_price", Decimal(str(self.stop_loss_price)))
        if self.take_profit_price is not None:
            object.__setattr__(self, "take_profit_price", Decimal(str(self.take_profit_price)))

        # Convert mode string to GridMode enum
        if isinstance(self.mode, str):
            object.__setattr__(self, "mode", GridMode(self.mode))

        if self.lower_price >= self.upper_price:
            raise ValueError("lower_price must be less than upper_price")
        if self.grid_count < 2:
            raise ValueError("grid_count must be at least 2")
        if self.total_investment <= 0:
            raise ValueError("total_investment must be positive")
        if self.per_grid_qty is not None and self.per_grid_qty <= 0:
            raise ValueError("per_grid_qty must be positive")
        if self.stop_loss_price is not None and self.stop_loss_price <= 0:
            raise ValueError("stop_loss_price must be positive")
        if self.take_profit_price is not None and self.take_profit_price <= 0:
            raise ValueError("take_profit_price must be positive")


@dataclass(frozen=True, slots=True)
class Level:
    """A single grid level."""

    index: int
    price: Decimal
    side: str  # "buy", "sell", or "" (skipped)


def generate_levels(
    lower: Decimal,
    upper: Decimal,
    count: int,
    mode: GridMode,
    price_precision: int,
) -> list[Level]:
    """
    Generate grid levels with specified spacing mode.

    Args:
        lower: Lower bound (inclusive)
        upper: Upper bound (inclusive)
        count: Number of levels
        mode: ARITHMETIC or GEOMETRIC spacing
        price_precision: Decimal places for price rounding

    Returns:
        List of Level objects with prices rounded to precision

    Raises:
        ValueError: If rounding causes duplicate levels (collapse)
    """
    if count < 2:
        raise ValueError("count must be at least 2")
    if lower >= upper:
        raise ValueError("lower must be less than upper")
    if price_precision < 0:
        raise ValueError("price_precision must be non-negative")

    step_factor = Decimal("10") ** price_precision
    prices: list[Decimal] = []

    if mode == GridMode.ARITHMETIC:
        # Equal spacing: step = (upper - lower) / (count - 1)
        raw_step = (upper - lower) / (count - 1)
        for i in range(count):
            raw_price = lower + raw_step * i
            # Round down to precision
            price = quantize_down(raw_price, Decimal("1") / step_factor)
            prices.append(price)

    elif mode == GridMode.GEOMETRIC:
        # Equal ratio: ratio = (upper / lower) ** (1 / (count - 1))
        if lower <= 0:
            raise ValueError("lower must be positive for geometric mode")
        ratio = (upper / lower) ** (Decimal("1") / (count - 1))
        for i in range(count):
            raw_price = lower * (ratio**i)
            price = quantize_down(raw_price, Decimal("1") / step_factor)
            prices.append(price)

    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Force endpoints to exact values after rounding
    prices[0] = quantize_down(lower, Decimal("1") / step_factor)
    prices[-1] = quantize_down(upper, Decimal("1") / step_factor)

    # Check for duplicates after rounding
    if len(set(prices)) != len(prices):
        raise ValueError("Level prices collapsed after rounding - increase range or decrease count")

    # Check strictly increasing
    for i in range(1, len(prices)):
        if prices[i] <= prices[i - 1]:
            raise ValueError("Level prices not strictly increasing after rounding")

    # Create Level objects (side will be assigned later)
    return [Level(index=i, price=price, side="") for i, price in enumerate(prices)]


def assign_sides(levels: list[Level], current_price: Decimal) -> list[Level]:
    """
    Assign buy/sell sides to levels based on current price.

    Levels below current price -> buy
    Levels above current price -> sell
    Level at/very close to current price -> skipped (empty side)
    """
    result = []
    for level in levels:
        if level.price < current_price:
            side = "buy"
        elif level.price > current_price:
            side = "sell"
        else:
            side = ""  # Skip level at current price
        result.append(Level(index=level.index, price=level.price, side=side))
    return result
