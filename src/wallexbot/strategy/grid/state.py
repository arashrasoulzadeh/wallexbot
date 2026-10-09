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

    def set_active_order(self, level_index: int, order_id: str) -> None:
        """Set active order for a level."""
        if level_index in self.active_orders:
            raise GridStateError(f"Level {level_index} already has active order {self.active_orders[level_index]}")
        if level_index < 0 or level_index >= len(self.levels):
            raise GridStateError(f"Invalid level index: {level_index}")
        if self.levels[level_index].side == "":
            raise GridStateError(f"Cannot place order on skipped level {level_index}")
        self.active_orders[level_index] = order_id

    def clear_active_order(self, level_index: int) -> Optional[str]:
        """Clear active order for a level, return the order_id."""
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
            assert self.levels[level_idx].side in ("buy", "sell")

        # Exactly one gap level (side == "")
        gap_levels = [l for l in self.levels if l.side == ""]
        assert len(gap_levels) == 1, f"Expected exactly one gap level, found {len(gap_levels)}"