"""Strategy interface for grid trading."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, OrderType, Side, Symbol
from wallexbot.strategy.grid.parameters import GridParameters, Level
from wallexbot.strategy.grid.profit import ProfitTracker
from wallexbot.strategy.grid.state import GridState


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
class PauseAction:
    """Action to pause the strategy."""

    type: Literal["pause"]
    reason: str


@dataclass(frozen=True, slots=True)
class AlertAction:
    """Action to send an alert."""

    type: Literal["alert"]
    message: str
    severity: Literal["info", "warning", "critical"] = "info"


Action = PlaceAction | CancelAction | PauseAction | AlertAction


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """Context passed to strategy methods."""

    market: "Market"
    params: GridParameters
    state: GridState
    profit_tracker: ProfitTracker
    current_price: Decimal
    timestamp: int


class GridStrategy:
    """Grid trading strategy implementation."""

    def __init__(
        self,
        market: "Market",
        params: GridParameters,
        fee_schedule: "FeeSchedule | None" = None,
        min_notional_rule: "MinNotionalRule | None" = None,
        run_id: str = "R",
    ) -> None:
        from wallexbot.domain.fees import FeeSchedule, MinNotionalRule

        self.market = market
        self.params = params
        # Placeholders until the real Wallex fee / minimum order size are known (TODO D16/D17).
        self.fee_schedule = fee_schedule or FeeSchedule(
            maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")
        )
        self.min_notional_rule = min_notional_rule or MinNotionalRule(
            min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")
        )
        self.run_id = run_id
        self.state: GridState | None = None
        self.profit_tracker = ProfitTracker()
        self._clock = None
        self._seq = 0

    def on_start(self, current_price: Decimal, timestamp: int = 0) -> list[Action]:
        """Initialize grid on start."""
        from wallexbot.strategy.grid.parameters import assign_sides, generate_levels
        from wallexbot.strategy.grid.placement import place_initial_grid

        # Generate levels
        levels = generate_levels(
            lower=self.params.lower_price,
            upper=self.params.upper_price,
            count=self.params.grid_count,
            mode=self.params.mode,
            price_precision=self.market.price_precision,
        )
        levels = assign_sides(levels, current_price)

        # Place initial grid
        fee_schedule = self.fee_schedule
        min_notional = self.min_notional_rule

        placement = place_initial_grid(
            levels=levels,
            current_price=current_price,
            market=self.market,
            params=self.params,
            fee_schedule=fee_schedule,
            min_notional_rule=min_notional,
        )

        # Initialize state
        self.state = GridState(levels=levels)

        # Populate active orders from initial placement
        for order in placement.orders:
            self.state.set_active_order(
                order.level_index, order.client_id, order.side.value.lower(), order.quantity
            )

        # Convert placement orders to actions
        actions: list[Action] = []
        for order in placement.orders:
            actions.append(
                PlaceAction(
                    type="place",
                    client_id=order.client_id,
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    price=order.price,
                    quantity=order.quantity,
                    level_index=order.level_index,
                )
            )

        return actions

    def on_price(self, current_price: Decimal, timestamp: int = 0) -> list[Action]:
        """Handle price update."""
        from wallexbot.strategy.grid.range_exit import RangeExitPolicy, check_range_exit

        actions: list[Action] = []

        if self.state is None:
            return actions

        # Check range exit
        exit_action = check_range_exit(current_price, self.params, RangeExitPolicy.PAUSE_AND_ALERT)
        if exit_action:
            actions.append(PauseAction(type="pause", reason=exit_action.reason))
            actions.append(
                AlertAction(
                    type="alert",
                    message=exit_action.reason,
                    severity="warning",
                )
            )

        return actions

    def on_fill(
        self,
        level_index: int,
        fill_qty: Decimal,
        fill_fee: Decimal,
        fill_fee_asset: str,
        timestamp: int = 0,
    ) -> list[Action]:
        """Handle a fill of the order on `level_index` (decision D1: wait for the full fill).

        Partial fills are recorded and produce no actions. When the running total reaches the
        ordered quantity (within one amount-precision step), a single counter-order is placed
        for the total filled quantity.
        """
        if self.state is None or level_index not in self.state.active_orders:
            return []  # unknown level, or duplicate/late event for an order we already answered

        total_qty, total_fee = self.state.record_partial_fill(level_index, fill_qty, fill_fee)
        ordered = self.state.order_qty.get(level_index)
        if ordered is not None:
            step = Decimal(1) / (Decimal(10) ** self.market.amount_precision)
            if total_qty < ordered - step:
                return []  # still partially filled: keep the order and wait
        return self._complete_fill(level_index, total_qty, total_fee, fill_fee_asset)

    def _complete_fill(
        self, level_index: int, qty: Decimal, fee: Decimal, fee_asset: str
    ) -> list[Action]:
        """Answer a finished (or cancelled-after-partial) order with its counter-order."""
        from wallexbot.strategy.grid.fill_handling import handle_fill

        assert self.state is not None
        actions: list[Action] = []
        self._seq += 1

        result = handle_fill(
            fill_level=level_index,
            fill_qty=qty,
            fill_fee=fee,
            levels=self.state.levels,
            active_orders=self.state.active_orders,
            market=self.market,
            fee_schedule=self.fee_schedule,
            min_notional_rule=self.min_notional_rule,
            params=self.params,
            fill_side=self.state.order_sides.get(level_index),
            fill_fee_asset=fee_asset,
            run_id=self.run_id,
            seq=self._seq,
        )

        self.state.clear_active_order(level_index)

        for action in result.actions:
            if action.type == "place":
                actions.append(
                    PlaceAction(
                        type="place",
                        client_id=action.client_id,
                        symbol=action.symbol,
                        side=action.side,
                        order_type=action.order_type,
                        price=action.price,
                        quantity=action.quantity,
                        level_index=action.level_index,
                    )
                )
                self.state.set_active_order(
                    action.level_index, action.client_id, action.side.value.lower(), action.quantity
                )
            elif action.type == "cancel":
                actions.append(
                    CancelAction(
                        type="cancel",
                        client_id=action.client_id,
                        level_index=action.level_index,
                    )
                )
                self.state.clear_active_order(action.level_index)

        if result.profit != 0:
            self.profit_tracker.total_cycles += 1
            self.profit_tracker.total_profit += result.profit
            self.profit_tracker.cycle_profits.append(result.profit)

        if result.warning:
            actions.append(AlertAction(type="alert", message=result.warning, severity="warning"))
        elif result.cycle_completed:
            actions.append(
                AlertAction(
                    type="alert",
                    message=f"Grid cycle completed at level {level_index}",
                    severity="info",
                )
            )

        return actions

    def on_cancel(self, level_index: int, timestamp: int = 0) -> list[Action]:
        """Handle order cancellation; a partly filled order still gets a counter-order."""
        if self.state is None:
            return []

        filled = self.state.filled_qty.get(level_index, Decimal("0"))
        if filled > 0 and level_index in self.state.active_orders:
            fee = self.state.filled_fee.get(level_index, Decimal("0"))
            return self._complete_fill(level_index, filled, fee, "")

        self.state.clear_active_order(level_index)
        return []

    def on_stop(self, timestamp: int = 0) -> list[Action]:
        """Stop the strategy - cancel all active orders."""
        if self.state is None:
            return []

        actions: list[Action] = []
        for level_index, order_id in list(self.state.active_orders.items()):
            actions.append(CancelAction(type="cancel", client_id=order_id, level_index=level_index))
            self.state.clear_active_order(level_index)

        return actions

    # --- saving and restoring (crash recovery) ---------------------------------------

    STATE_VERSION = 1
    KEEP_CYCLES = 100  # recent cycle profits kept in a saved state

    def export_state(self) -> dict[str, Any]:
        """The strategy's full state as plain JSON types."""
        state = self.state
        tracker = self.profit_tracker
        return {
            "version": self.STATE_VERSION,
            "grid_count": self.params.grid_count,
            "seq": self._seq,
            "started": state is not None,
            "levels": []
            if state is None
            else [
                {"index": lv.index, "price": str(lv.price), "side": lv.side} for lv in state.levels
            ],
            "active_orders": {}
            if state is None
            else {str(k): v for k, v in state.active_orders.items()},
            "order_sides": {}
            if state is None
            else {str(k): v for k, v in state.order_sides.items()},
            "order_qty": {}
            if state is None
            else {str(k): str(v) for k, v in state.order_qty.items()},
            "filled_qty": {}
            if state is None
            else {str(k): str(v) for k, v in state.filled_qty.items()},
            "filled_fee": {}
            if state is None
            else {str(k): str(v) for k, v in state.filled_fee.items()},
            "profit": {
                "cycles": tracker.total_cycles,
                "total": str(tracker.total_profit),
                "fees": str(tracker.total_fees_paid),
                "recent": [str(p) for p in tracker.cycle_profits[-self.KEEP_CYCLES :]],
            },
        }

    def import_state(self, saved: dict[str, Any]) -> None:
        """Restore a saved state; refuses one that belongs to a different grid."""
        if saved.get("version") != self.STATE_VERSION:
            raise ValueError(f"unsupported strategy state version {saved.get('version')!r}")
        if saved["grid_count"] != self.params.grid_count:
            raise ValueError(
                f"saved state is for a grid of {saved['grid_count']} levels, "
                f"this strategy has {self.params.grid_count}"
            )
        self._seq = saved["seq"]
        profit = saved["profit"]
        self.profit_tracker.total_cycles = profit["cycles"]
        self.profit_tracker.total_profit = Decimal(profit["total"])
        self.profit_tracker.total_fees_paid = Decimal(profit["fees"])
        self.profit_tracker.cycle_profits = [Decimal(p) for p in profit["recent"]]
        if not saved["started"]:
            self.state = None
            return
        levels = [
            Level(index=lv["index"], price=Decimal(lv["price"]), side=lv["side"])
            for lv in saved["levels"]
        ]
        state = GridState(levels=levels)
        state.active_orders = {int(k): v for k, v in saved["active_orders"].items()}
        state.order_sides = {int(k): v for k, v in saved["order_sides"].items()}
        state.order_qty = {int(k): Decimal(v) for k, v in saved["order_qty"].items()}
        state.filled_qty = {int(k): Decimal(v) for k, v in saved["filled_qty"].items()}
        state.filled_fee = {int(k): Decimal(v) for k, v in saved["filled_fee"].items()}
        self.state = state
