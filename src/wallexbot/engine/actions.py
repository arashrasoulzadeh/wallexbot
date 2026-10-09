"""Action executor for translating strategy actions to exchange calls."""

from dataclasses import dataclass
from decimal import Decimal
from typing: Optional
import uuid

from wallexbot.strategy.grid.interface import (
    Action,
    PlaceAction,
    CancelAction,
    PauseAction,
    AlertAction,
)
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.domain.order import OrderRequest
from wallexbot.domain.market import Symbol, Side, OrderType, OrderStatus
from wallexbot.tests.helpers.clock import Clock


@dataclass
class ActionExecutor:
    """Executes strategy actions on the exchange."""

    exchange: SimulatedExchange
    clock: Clock
    _client_id_counter: int = 0
    _run_id: str = ""

    def __post_init__(self) -> None:
        self._run_id = uuid.uuid4().hex[:8]

    def _generate_client_id(self, level_index: int, seq: int) -> str:
        """Generate idempotent client_id."""
        self._client_id_counter += 1
        return f"GRID_{self._run_id}_{level_index}_{seq}"

    def execute(self, action: Action) -> list:
        """Execute a strategy action."""
        if isinstance(action, PlaceAction):
            return [self.execute_place(action)]
        elif isinstance(action, CancelAction):
            self.execute_cancel(action)
            return []
        elif isinstance(action, PauseAction):
            return [{"type": "pause", "reason": action.reason}]
        elif isinstance(action, AlertAction):
            return [{"type": "alert", "message": action.message, "severity": action.severity}]
        return []

    def execute_place(self, action: PlaceAction) -> object:
        """Execute place order action."""
        # Generate client_id if not provided
        client_id = action.client_id or self._generate_client_id(action.level_index, self._client_id_counter)

        request = OrderRequest(
            client_id=client_id,
            symbol=action.symbol,
            side=action.side,
            type=action.order_type,
            price=action.price,
            quantity=action.quantity,
        )

        order = self.exchange.place_order(request)
        return order

    def execute_cancel(self, action: CancelAction) -> None:
        """Execute cancel order action."""
        self.exchange.cancel_order(action.client_id)

    def handle_timeout(self, client_id: str) -> object:
        """Handle place call timeout - look up by client_id before retry."""
        # Check if order was actually placed
        try:
            order = self.exchange.get_order(client_id)
            if order:
                return order
        except Exception:
            pass

        # Order not found - safe to retry
        return None