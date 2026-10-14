"""Initial grid placement logic."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, OrderType, Side, Symbol
from wallexbot.strategy.grid.parameters import GridParameters, Level
from wallexbot.strategy.grid.sizing import (
    calculate_equal_base_qty,
    calculate_equal_quote_qty,
    compute_initial_inventory,
    validate_order_sizes,
)


@dataclass(frozen=True, slots=True)
class PlaceAction:
    """Action to place an order."""

    type: Literal["place"]
    client_id: str
    symbol: Symbol
    side: Side
    order_type: OrderType
    price: Decimal
    quantity: Decimal
    level_index: int


@dataclass(frozen=True, slots=True)
class InitialPlacement:
    """Result of initial grid placement."""

    orders: list[PlaceAction]
    skipped_level_index: int | None
    base_needed_for_sells: Decimal
    quote_needed_for_buys: Decimal


def place_initial_grid(
    levels: list[Level],
    current_price: Decimal,
    market: Market,
    params: GridParameters,
    fee_schedule: FeeSchedule,
    min_notional_rule: MinNotionalRule,
    generation: int = 0,
) -> InitialPlacement:
    """
    Place initial grid orders based on current price.

    Buy orders at levels below current price.
    Sell orders at levels above current price.
    Level at/very close to current price is skipped.
    """
    # Calculate quantities
    if params.per_grid_qty is not None:
        qtys = calculate_equal_base_qty(levels, params.per_grid_qty, market)
    else:
        qtys = calculate_equal_quote_qty(levels, params.total_investment, market)

    # Validate order sizes
    ok, errors = validate_order_sizes(levels, qtys, market, min_notional_rule)
    if not ok:
        raise ValueError(f"Order validation failed: {'; '.join(errors)}")

    # Generate orders
    orders = []
    skipped_index = None
    for level, qty in zip(levels, qtys, strict=True):
        if level.side == "":
            skipped_index = level.index
            continue
        if qty <= 0:
            continue

        client_id = (
            f"GRID_INIT_{level.index}_1"
            if generation == 0
            else f"GRID_G{generation}_INIT_{level.index}_1"
        )
        order = PlaceAction(
            type="place",
            client_id=client_id,
            symbol=market.symbol,
            side=Side.BUY if level.side == "buy" else Side.SELL,
            order_type=OrderType.LIMIT,
            price=level.price,
            quantity=qty,
            level_index=level.index,
        )
        orders.append(order)

    # Compute inventory needs
    base_needed = compute_initial_inventory(levels, qtys, Side.SELL)
    quote_needed = compute_initial_inventory(levels, qtys, Side.BUY)

    return InitialPlacement(
        orders=orders,
        skipped_level_index=skipped_index,
        base_needed_for_sells=base_needed,
        quote_needed_for_buys=quote_needed,
    )
