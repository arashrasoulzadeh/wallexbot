"""Grid state model."""

from dataclasses import dataclass, field
from typing import Optional

from wallexbot.strategy.grid.parameters import Level


class GridStateError(Exception):
    """Grid state invariant violation."""
    pass


@dataclass(slots=True)
class GridState:
    """Mutable grid state tracking active orders per level."""

    levels: list[Level]
    active_orders: dict[int, str] = field(default_factory=dict)  # level_index -> order_id
    order_sides: dict[int, str] = field(default_factory=dict)  # level_index -> "buy"/"sell"

    def set_active_order(self, level_index: int, order_id: str, side: str | None = None) -> None:
        """Set active order for a level. `side` defaults to the level's initial side."""
        if level_index in self.active_orders:
            raise GridStateError(f"Level {level_index} already has active order {self.active_orders[level_index]}")
        if level_index < 0 or level_index >= len(self.levels):
            raise GridStateError(f"Invalid level index: {level_index}")
        order_side = side or self.levels[level_index].side
        if order_side not in ("buy", "sell"):
            raise GridStateError(f"Order on level {level_index} needs a buy/sell side")
        self.active_orders[level_index] = order_id
        self.order_sides[level_index] = order_side

    def clear_active_order(self, level_index: int) -> Optional[str]:
        """Clear active order for a level, return the order_id."""
        self.order_sides.pop(level_index, None)
        return self.active_orders.pop(level_index, None)

    def get_level_for_order(self, order_id: str) -> Optional[int]:
        """Find level index for an order_id."""
        for idx, oid in self.active_orders.items():
            if oid == order_id:
                return idx
        return None

    def is_level_active(self, level_index: int) -> bool:
        """Check if a level has an active order."""
        return level_index in self.active_orders

    def get_active_count(self) -> int:
        """Get number of active orders."""
        return len(self.active_orders)

    def validate_invariants(self) -> None:
        """Validate grid state invariants."""
        # At most one active order per level
        assert len(self.active_orders) == len(set(self.active_orders.keys()))

        # Active orders only on valid levels with sides
        for level_idx in self.active_orders:
            assert 0 <= level_idx < len(self.levels)
            assert self.order_sides.get(level_idx) in ("buy", "sell")

        # The ladder keeps exactly one empty slot once the grid is running
        assert len(self.active_orders) <= len(self.levels)
