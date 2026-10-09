"""Range exit handling for grid strategy."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from wallexbot.strategy.grid.parameters import GridParameters
from wallexbot.domain.market import Symbol


class RangeExitPolicy(str, Enum):
    """Policy when price exits grid range."""

    PAUSE_AND_ALERT = "pause_and_alert"
    HOLD = "hold"
    RECENTER = "recenter"


@dataclass(frozen=True, slots=True)
class RangeExitAction:
    """Action to take on range exit."""

    type: Literal["pause"]
    reason: str


def check_range_exit(
    current_price: Decimal,
    params: GridParameters,
    policy: RangeExitPolicy = RangeExitPolicy.PAUSE_AND_ALERT,
) -> RangeExitAction | None:
    """
    Check if price has exited the grid range.

    Returns:
        RangeExitAction if exit detected and policy is PAUSE_AND_ALERT, None otherwise
    """
    if policy == RangeExitPolicy.HOLD:
        return None

    # Check stop loss
    if params.stop_loss_price is not None and current_price <= params.stop_loss_price:
        return RangeExitAction(
            type="pause",
            reason=f"Stop loss triggered: price {current_price} <= {params.stop_loss_price}",
        )

    # Check take profit
    if params.take_profit_price is not None and current_price >= params.take_profit_price:
        return RangeExitAction(
            type="pause",
            reason=f"Take profit triggered: price {current_price} >= {params.take_profit_price}",
        )

    # Check upper bound
    if current_price > params.upper_price:
        return RangeExitAction(
            type="pause",
            reason=f"Price {current_price} above upper bound {params.upper_price}",
        )

    # Check lower bound
    if current_price < params.lower_price:
        return RangeExitAction(
            type="pause",
            reason=f"Price {current_price} below lower bound {params.lower_price}",
        )

    return None