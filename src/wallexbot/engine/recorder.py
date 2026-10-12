"""Writes a run, its orders, fills and events to a Repository."""

import time
from typing import Any

from wallexbot.domain.order import Fill, Order
from wallexbot.storage.repository import Repository


class RunRecorder:
    """Persists one engine run through the generic Repository interface."""

    def __init__(self, repository: Repository, name: str, market: str) -> None:
        self.repository = repository
        self.name = name
        self.market = market
        self.run_id = ""
        self._saved_orders: set[str] = set()

    def start(self, details: dict[str, Any]) -> str:
        # SQLiteRepository reads market and mode from config["strategy"]["grid"].
        config = {
            "market": self.market,
            "mode": "paper",
            "strategy": {"grid": {"market": self.market, "mode": "paper"}},
            **details,
        }
        self.run_id = self.repository.create_run(self.name, config)
        return self.run_id

    def event(self, kind: str, message: str, level_index: int | None = None) -> None:
        self.repository.save_event(
            self.run_id,
            {
                "type": kind,
                "message": message,
                "level_index": level_index,
                "timestamp": int(time.time() * 1000),
            },
        )

    def fill(self, order: Order, fill: Fill, level_index: int | None) -> None:
        if order.id not in self._saved_orders:  # fills reference their order
            self.repository.save_order(self.run_id, self._order_dict(order, level_index))
            self._saved_orders.add(order.id)
        self.repository.save_fill(
            self.run_id,
            {
                "order_id": order.id,
                "trade_id": fill.trade_id,
                "price": str(fill.price),
                "quantity": str(fill.quantity),
                "fee": str(fill.fee),
                "fee_asset": fill.fee_asset,
                "is_maker": fill.is_maker,
                "timestamp": fill.timestamp,
                "level_index": level_index,
            },
        )

    def finish(self, status: str) -> None:
        self.repository.update_run_status(self.run_id, status, int(time.time() * 1000))

    @staticmethod
    def _order_dict(order: Order, level_index: int | None) -> dict[str, Any]:
        return {
            "id": order.id,
            "client_id": order.client_id,
            "symbol": str(order.symbol),
            "side": order.side.value,
            "type": order.type.value,
            "price": None if order.price is None else str(order.price),
            "quantity": str(order.quantity),
            "status": order.status.value,
            "filled_quantity": str(order.filled_quantity),
            "fee": str(order.fee),
            "fee_asset": order.fee_asset,
            "is_maker": order.is_maker,
            "level_index": level_index,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }
