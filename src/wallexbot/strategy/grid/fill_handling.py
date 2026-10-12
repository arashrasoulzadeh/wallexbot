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
    warning: str = ""


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
    fill_side: str | None = None,
    fill_fee_asset: str = "",
    run_id: str = "R",
    seq: int = 0,
) -> FillResult:
    """
    Handle a full fill of the order sitting on `fill_level`.

    Ladder rule, local to the filled level (works for any number of fills in a row):
    - BUY filled at level i  -> place a SELL at level i+1
    - SELL filled at level i -> place a BUY at level i-1

    Args:
        fill_side: side of the order that filled ("buy"/"sell"). The static side stored on the
            level only describes the initial placement, so callers should pass the tracked side.
        fill_fee_asset: asset the exchange charged the fee in. A BUY fee charged in the base
            asset is deducted from the quantity we sell back.
        run_id, seq: make the counter order's client_id unique (Wallex rejects repeats).

    Profit is realized on SELL fills: spacing to the level below times quantity, minus
    maker fees on both legs. BUY fills realize nothing.
    """
    if not 0 <= fill_level < len(levels) or fill_level not in active_orders:
        # Unknown level, duplicate or out-of-order fill: nothing to do.
        return FillResult(actions=[])

    side = (fill_side or levels[fill_level].side).lower()
    if side not in ("buy", "sell"):
        return FillResult(actions=[], warning=f"level {fill_level} has no buy/sell order to answer")

    profit = Decimal("0")
    if side == "sell" and fill_level > 0:
        buy_price = levels[fill_level - 1].price
        sell_price = levels[fill_level].price
        gross = (sell_price - buy_price) * fill_qty
        fees = (buy_price + sell_price) * fill_qty * fee_schedule.maker_rate
        profit = gross - fees

    target = fill_level + 1 if side == "buy" else fill_level - 1
    if not 0 <= target < len(levels):
        # Edge of the grid: nothing beyond it to trade against.
        return FillResult(actions=[], cycle_completed=True, profit=profit)
    if target in active_orders:
        return FillResult(
            actions=[],
            profit=profit,
            warning=f"counter level {target} is occupied by {active_orders[target]}",
        )

    quantity = fill_qty
    if side == "buy" and fill_fee_asset and fill_fee_asset == market.base:
        quantity = fill_qty - fill_fee  # fee was taken out of the coins we just bought

    counter_side = Side.SELL if side == "buy" else Side.BUY
    order, warning = _create_counter_order(
        level_idx=target,
        side=counter_side,
        quantity=quantity,
        levels=levels,
        market=market,
        min_notional_rule=min_notional_rule,
        client_id=f"GRID_{run_id}_{seq}_{target}_{counter_side.value}",
    )
    return FillResult(
        actions=[order] if order else [],
        profit=profit,
        warning=warning,
    )


def _create_counter_order(
    level_idx: int,
    side: Side,
    quantity: Decimal,
    levels: list[Level],
    market: Market,
    min_notional_rule: MinNotionalRule,
    client_id: str,
) -> tuple[PlaceAction | None, str]:
    """Build the counter order, or return (None, reason) if it cannot be placed."""
    level = levels[level_idx]

    step = Decimal("1") / (Decimal("10") ** market.amount_precision)
    qty = quantize_down(quantity, step)
    if qty <= 0:
        return None, f"counter quantity {quantity} rounds to zero"

    ok, reason = min_notional_rule.validate(level.price, qty)
    if not ok:
        return None, f"counter order at level {level_idx} below minimum: {reason}"

    return (
        PlaceAction(
            type="place",
            client_id=client_id,
            symbol=market.symbol,
            side=side,
            order_type=OrderType.LIMIT,
            price=level.price,
            quantity=qty,
            level_index=level_idx,
        ),
        "",
    )
