"""Strategy interface for grid trading."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from wallexbot.domain.market import Market, Symbol, Side, OrderType
from wallexbot.strategy.grid.parameters import GridParameters
from wallexbot.strategy.grid.state import GridState
from wallexbot.strategy.grid.profit import ProfitTracker
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule


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
        from wallexbot.strategy.grid.parameters import generate_levels, assign_sides
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
            self.state.set_active_order(order.level_index, order.client_id, order.side.value.lower())

        # Convert placement orders to actions
        actions: list[Action] = []
        for order in placement.orders:
            actions.append(PlaceAction(
                type="place",
                client_id=order.client_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                price=order.price,
                quantity=order.quantity,
                level_index=order.level_index,
            ))

        return actions

    def on_price(self, current_price: Decimal, timestamp: int = 0) -> list[Action]:
        """Handle price update."""
        from wallexbot.strategy.grid.range_exit import check_range_exit, RangeExitPolicy

        actions: list[Action] = []

        if self.state is None:
            return actions

        # Check range exit
        exit_action = check_range_exit(current_price, self.params, RangeExitPolicy.PAUSE_AND_ALERT)
        if exit_action:
            actions.append(PauseAction(type="pause", reason=exit_action.reason))
            actions.append(AlertAction(
                type="alert",
                message=exit_action.reason,
                severity="warning",
            ))

        return actions

    def on_fill(
        self,
        level_index: int,
        fill_qty: Decimal,
        fill_fee: Decimal,
        fill_fee_asset: str,
        timestamp: int = 0,
    ) -> list[Action]:
        """Handle a full fill of the order on `level_index`."""
        from wallexbot.strategy.grid.fill_handling import handle_fill

        if self.state is None:
            return []

        actions: list[Action] = []
        self._seq += 1

        result = handle_fill(
            fill_level=level_index,
            fill_qty=fill_qty,
            fill_fee=fill_fee,
            levels=self.state.levels,
            active_orders=self.state.active_orders,
            market=self.market,
            fee_schedule=self.fee_schedule,
            min_notional_rule=self.min_notional_rule,
            params=self.params,
            fill_side=self.state.order_sides.get(level_index),
            fill_fee_asset=fill_fee_asset,
            run_id=self.run_id,
            seq=self._seq,
        )

        if level_index in self.state.active_orders:
            self.state.clear_active_order(level_index)

        for action in result.actions:
            if action.type == "place":
                actions.append(PlaceAction(
                    type="place",
                    client_id=action.client_id,
                    symbol=action.symbol,
                    side=action.side,
                    order_type=action.order_type,
                    price=action.price,
                    quantity=action.quantity,
                    level_index=action.level_index,
                ))
                self.state.set_active_order(
                    action.level_index, action.client_id, action.side.value.lower()
                )
            elif action.type == "cancel":
                actions.append(CancelAction(
                    type="cancel",
                    client_id=action.client_id,
                    level_index=action.level_index,
                ))
                self.state.clear_active_order(action.level_index)

        if result.profit != 0:
            self.profit_tracker.total_cycles += 1
            self.profit_tracker.total_profit += result.profit
            self.profit_tracker.cycle_profits.append(result.profit)

        if result.warning:
            actions.append(AlertAction(type="alert", message=result.warning, severity="warning"))
        elif result.cycle_completed:
            actions.append(AlertAction(
                type="alert",
                message=f"Grid cycle completed at level {level_index}",
                severity="info",
            ))

        return actions

    def on_cancel(self, level_index: int, timestamp: int = 0) -> list[Action]:
        """Handle order cancellation."""
        if self.state is None:
            return []

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