"""Balance model for asset balances."""

from dataclasses import dataclass, replace
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Balance:
    """Asset balance with free and locked amounts."""

    free: Decimal
    locked: Decimal

    def __post_init__(self) -> None:
        if self.free < 0:
            raise ValueError("free balance cannot be negative")
        if self.locked < 0:
            raise ValueError("locked balance cannot be negative")

    @property
    def total(self) -> Decimal:
        """Total balance (free + locked)."""
        return self.free + self.locked

    def lock(self, amount: Decimal) -> "Balance":
        """Lock amount from free balance."""
        if amount < 0:
            raise ValueError("lock amount cannot be negative")
        if amount > self.free:
            raise ValueError(f"Insufficient free balance: {self.free} < {amount}")
        return replace(self, free=self.free - amount, locked=self.locked + amount)

    def unlock(self, amount: Decimal) -> "Balance":
        """Unlock amount to free balance."""
        if amount < 0:
            raise ValueError("unlock amount cannot be negative")
        if amount > self.locked:
            raise ValueError(f"Insufficient locked balance: {self.locked} < {amount}")
        return replace(self, free=self.free + amount, locked=self.locked - amount)

    def add(self, amount: Decimal) -> "Balance":
        """Add to free balance (e.g., from deposit or fill)."""
        if amount < 0:
            raise ValueError("add amount cannot be negative")
        return replace(self, free=self.free + amount)

    def subtract(self, amount: Decimal) -> "Balance":
        """Subtract from free balance (e.g., for withdrawal or fee)."""
        if amount < 0:
            raise ValueError("subtract amount cannot be negative")
        if amount > self.free:
            raise ValueError(f"Insufficient free balance: {self.free} < {amount}")
        return replace(self, free=self.free - amount)
