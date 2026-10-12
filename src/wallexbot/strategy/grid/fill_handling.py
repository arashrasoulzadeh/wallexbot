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

    Grid logic (gap-based):
    - Find the gap level (side == "")
    - Buy fill at level immediately below gap -> place sell at first sell level above gap
    - Sell fill at level immediately above gap -> place buy at first buy level below gap
    - Other fills: no counter-order (cycle completed at boundaries)
    - Partial fills: counter-order for filled quantity only
    """
    # Check if this fill level has an active order
    if fill_level not in active_orders:
        # Duplicate or out-of-order fill - ignore
        return FillResult(actions=[])

    # Get the filled level info
    level = levels[fill_level]
    filled_side = level.side  # "buy" or "sell"

    # Find the gap level (side == "")
    gap_level_idx = None
    for idx, lvl in enumerate(levels):
        if lvl.side == "":
            gap_level_idx = idx
            break

    actions: list[Action] = []
    cycle_completed = False
    profit = Decimal("0")

    if filled_side == "buy":
        # Buy filled -> place sell at first sell level above gap
        # Only if this buy level is immediately below the gap
        if gap_level_idx is not None and fill_level + 1 == gap_level_idx:
            # Find first sell level above gap
            next_level_idx = gap_level_idx + 1
            while next_level_idx < len(levels) and levels[next_level_idx].side != "sell":
                next_level_idx += 1
            if next_level_idx < len(levels):
                # If there's an existing order at the counter level, cancel it first
                if next_level_idx in active_orders:
                    actions.append(CancelAction(
                        type="cancel",
                        client_id=active_orders[next_level_idx],
                        level_index=next_level_idx,
                    ))
                # Place counter order at next valid level
                actions.append(_create_counter_order(
                    level_idx=next_level_idx,
                    side=Side.SELL,
                    quantity=fill_qty,
                    levels=levels,
                    market=market,
                    fee_schedule=fee_schedule,
                    min_notional_rule=min_notional_rule,
                ))
            else:
                cycle_completed = True
        else:
            # Not adjacent to gap - no counter order (boundary)
            cycle_completed = True

    elif filled_side == "sell":
        # Sell filled -> place buy at first buy level below gap
        # Only if this sell level is immediately above the gap
        if gap_level_idx is not None and fill_level - 1 == gap_level_idx:
            # Find first buy level below gap
            prev_level_idx = gap_level_idx - 1
            while prev_level_idx >= 0 and levels[prev_level_idx].side != "buy":
                prev_level_idx -= 1
            if prev_level_idx >= 0:
                # If there's an existing order at the counter level, cancel it first
                if prev_level_idx in active_orders:
                    actions.append(CancelAction(
                        type="cancel",
                        client_id=active_orders[prev_level_idx],
                        level_index=prev_level_idx,
                    ))
                # Place counter order at prev valid level
                actions.append(_create_counter_order(
                    level_idx=prev_level_idx,
                    side=Side.BUY,
                    quantity=fill_qty,
                    levels=levels,
                    market=market,
                    fee_schedule=fee_schedule,
                    min_notional_rule=min_notional_rule,
                ))
            else:
                cycle_completed = True
        else:
            # Not adjacent to gap - no counter order (boundary)
            cycle_completed = True

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