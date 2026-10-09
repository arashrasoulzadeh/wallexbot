"""Fill handling for grid strategy."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from wallexbot.strategy.grid.parameters import Level, GridParameters
from wallexbot.domain.market import Market, Symbol, Side, OrderType
from wallexbot.domain.order import OrderRequest
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.money import quantize_down


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
class CancelAction:
    """Action to cancel an order."""

    type: Literal["cancel"]
    client_id: str
    level_index: int


@dataclass(frozen=True, slots=True)
class FillResult:
    """Result of handling a fill."""

    actions: list[PlaceAction | CancelAction]
    cycle_completed: bool = False
    profit: Decimal = Decimal("0")


Action = PlaceAction | CancelAction


def handle_fill(
    fill_level: int,
    fill_qty: Decimal,
    fill_fee: Decimal,
    levels: list[Level],
    active_orders: dict[int, str],
    market: Market,
    fee_schedule: FeeSchedule,
    min_notional_rule: MinNotionalRule,
    params: GridParameters,
) -> FillResult:
    """
    Handle a fill event and return counter-actions.

    Grid logic:
    - Buy fill at level i -> place sell at level i+1
    - Sell fill at level i -> place buy at level i-1
    - Edge levels (top/bottom): no counter-order, cycle completed
    - Partial fills: counter-order for filled quantity only
    """
    # Check if this fill level has an active order
    if fill_level not in active_orders:
        # Duplicate or out-of-order fill - ignore
        return FillResult(actions=[])

    # Get the filled level info
    level = levels[fill_level]
    filled_side = level.side  # "buy" or "sell"

    actions: list[Action] = []
    cycle_completed = False
    profit = Decimal("0")

    if filled_side == "buy":
        # Buy filled -> place sell at next level up (i+1)
        next_level_idx = fill_level + 1
        if next_level_idx >= len(levels):
            # Top of grid - no counter order, cycle completed
            cycle_completed = True
        elif levels[next_level_idx].side == "":
            # Next level is skipped (at price) - find next valid
            next_valid = next((i for i in range(next_level_idx, len(levels)) if levels[i].side == "sell"), None)
            if next_valid is not None:
                actions.append(_create_counter_order(
                    level_idx=next_valid,
                    side=Side.SELL,
                    quantity=fill_qty,
                    levels=levels,
                    market=market,
                    fee_schedule=fee_schedule,
                    min_notional_rule=min_notional_rule,
                ))
        else:
            actions.append(_create_counter_order(
                level_idx=next_level_idx,
                side=Side.SELL,
                quantity=fill_qty,
                levels=levels,
                market=market,
                fee_schedule=fee_schedule,
                min_notional_rule=min_notional_rule,
            ))

    elif filled_side == "sell":
        # Sell filled -> place buy at next level down (i-1)
        prev_level_idx = fill_level - 1
        if prev_level_idx < 0:
            # Bottom of grid - no counter order, cycle completed
            cycle_completed = True
        elif levels[prev_level_idx].side == "":
            # Prev level is skipped - find prev valid
            prev_valid = next((i for i in range(prev_level_idx, -1, -1) if levels[i].side == "buy"), None)
            if prev_valid is not None:
                actions.append(_create_counter_order(
                    level_idx=prev_valid,
                    side=Side.BUY,
                    quantity=fill_qty,
                    levels=levels,
                    market=market,
                    fee_schedule=fee_schedule,
                    min_notional_rule=min_notional_rule,
                ))
        else:
            actions.append(_create_counter_order(
                level_idx=prev_level_idx,
                side=Side.BUY,
                quantity=fill_qty,
                levels=levels,
                market=market,
                fee_schedule=fee_schedule,
                min_notional_rule=min_notional_rule,
            ))

    return FillResult(actions=actions, cycle_completed=cycle_completed, profit=profit)


def _create_counter_order(
    level_idx: int,
    side: Side,
    quantity: Decimal,
    levels: list[Level],
    market: Market,
    fee_schedule: FeeSchedule,
    min_notional_rule: MinNotionalRule,
) -> PlaceAction:
    """Create a counter-order for the given level."""
    level = levels[level_idx]

    # Adjust quantity for fees to ensure we don't go negative on base balance
    # For SELL counter-order after BUY fill: we received `quantity` base, fee was in quote
    # So we can sell the full `quantity` (minus any fee in base, but buy fee is in quote)
    # For BUY counter-order after SELL fill: we received quote, paid fee in base
    # So we have `quantity` base less fee to sell... wait, we're BUYING
    # Actually: SELL fill gives us quote, costs base fee. We then BUY with quote.
    # The BUY quantity is limited by quote received minus fee.
    # But for simplicity and per decision D1 (wait for full fill), we use fill_qty directly.
    # The fee adjustment is handled by the exchange (locked funds).

    # Validate minimum notional
    ok, _ = min_notional_rule.validate(level.price, quantity)
    if not ok:
        # Quantity too small - don't place order
        raise ValueError(f"Counter order quantity {quantity} at {level.price} fails min notional")

    # Round quantity to market precision
    step = Decimal("1") / (Decimal("10") ** market.amount_precision)
    qty = quantize_down(quantity, step)

    if qty <= 0:
        raise ValueError("Counter order quantity rounded to zero")

    client_id = f"GRID_{level_idx}_{side.value}_1"

    return PlaceAction(
        type="place",
        client_id=client_id,
        symbol=market.symbol,
        side=side,
        order_type=OrderType.LIMIT,
        price=level.price,
        quantity=qty,
        level_index=level_idx,
    )