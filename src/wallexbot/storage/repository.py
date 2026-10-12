"""Repository interface and implementations."""

import json
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from wallexbot.storage.migrations import run_migrations


class Repository(ABC):
    """Repository interface for persistence."""

    @abstractmethod
    def create_run(self, name: str, config: dict[str, Any]) -> str: ...

    @abstractmethod
    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_runs(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def update_run_status(
        self, run_id: str, status: str, stopped_at: int | None = None
    ) -> None: ...

    @abstractmethod
    def save_order(self, run_id: str, order: dict[str, Any]) -> str: ...

    @abstractmethod
    def get_order(self, run_id: str, order_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def get_order_by_client_id(self, run_id: str, client_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def update_order(self, order_id: str, updates: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_open_orders(self, run_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save_fill(self, run_id: str, fill: dict[str, Any]) -> int: ...

    @abstractmethod
    def get_fills(self, run_id: str, order_id: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save_grid_state(self, run_id: str, state: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_grid_state(self, run_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_event(self, run_id: str, event: dict[str, Any]) -> int: ...

    @abstractmethod
    def get_events(self, run_id: str) -> list[dict[str, Any]]: ...


class InMemoryRepository(Repository):
    """In-memory repository for testing."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._orders: dict[tuple[str, str], dict[str, Any]] = {}
        self._fills: dict[tuple[str, int], dict[str, Any]] = {}
        self._grid_states: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._run_counter = 0
        self._fill_counter = 0
        self._event_counter = 0

    def create_run(self, name: str, config: dict[str, Any]) -> str:
        self._run_counter += 1
        run_id = f"run_{self._run_counter}"
        import time

        self._runs[run_id] = {
            "id": run_id,
            "name": name,
            "config": config,
            "status": "running",
            "started_at": int(time.time() * 1000),
            "stopped_at": None,
        }
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        return list(self._runs.values())

    def update_run_status(self, run_id: str, status: str, stopped_at: int | None = None) -> None:
        if run_id in self._runs:
            self._runs[run_id]["status"] = status
            if stopped_at:
                self._runs[run_id]["stopped_at"] = stopped_at

    def save_order(self, run_id: str, order: dict[str, Any]) -> str:
        order_id: str = order.get("id", f"ord_{len(self._orders) + 1}")
        key = (run_id, order_id)
        self._orders[key] = {**order, "id": order_id, "run_id": run_id}
        return order_id

    def get_order(self, run_id: str, order_id: str) -> dict[str, Any] | None:
        return self._orders.get((run_id, order_id))

    def get_order_by_client_id(self, run_id: str, client_id: str) -> dict[str, Any] | None:
        for order in self._orders.values():
            if order["run_id"] == run_id and order["client_id"] == client_id:
                return order
        return None

    def update_order(self, order_id: str, updates: dict[str, Any]) -> None:
        for key, order in self._orders.items():
            if order["id"] == order_id:
                self._orders[key].update(updates)
                break

    def get_open_orders(self, run_id: str) -> list[dict[str, Any]]:
        return [
            o
            for o in self._orders.values()
            if o["run_id"] == run_id and o["status"] in ("NEW", "PARTIALLY_FILLED")
        ]

    def save_fill(self, run_id: str, fill: dict[str, Any]) -> int:
        self._fill_counter += 1
        fill_id = self._fill_counter
        key = (run_id, fill_id)
        self._fills[key] = {**fill, "id": fill_id, "run_id": run_id}
        return fill_id

    def get_fills(self, run_id: str, order_id: str | None = None) -> list[dict[str, Any]]:
        fills = [f for f in self._fills.values() if f["run_id"] == run_id]
        if order_id:
            fills = [f for f in fills if f["order_id"] == order_id]
        return fills

    def save_grid_state(self, run_id: str, state: dict[str, Any]) -> None:
        import time

        self._grid_states[run_id] = {**state, "updated_at": int(time.time() * 1000)}

    def get_grid_state(self, run_id: str) -> dict[str, Any] | None:
        return self._grid_states.get(run_id)

    def save_event(self, run_id: str, event: dict[str, Any]) -> int:
        self._event_counter += 1
        event_id = self._event_counter
        import time

        self._events.setdefault(run_id, []).append(
            {**event, "id": event_id, "run_id": run_id, "timestamp": int(time.time() * 1000)}
        )
        return event_id

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._events.get(run_id, [])


class SQLiteRepository(Repository):
    """SQLite repository for production."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def _db(self) -> sqlite3.Connection:
        """The open connection; raises a clear error instead of an AttributeError on None."""
        if self._conn is None:
            raise RuntimeError("database connection is closed")
        return self._conn

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        run_migrations(self._conn)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """Transaction context manager."""
        cursor = self._db.cursor()
        try:
            yield cursor
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    def create_run(self, name: str, config: dict[str, Any]) -> str:
        import hashlib
        import time

        config_json = json.dumps(config, sort_keys=True)
        config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:16]
        run_id = f"run_{int(time.time() * 1000)}_{config_hash}"

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO runs (id, config_hash, config_json, status, started_at, market, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run_id,
                    config_hash,
                    config_json,
                    "running",
                    int(time.time() * 1000),
                    config.get("strategy", {}).get("grid", {}).get("market", ""),
                    config.get("strategy", {}).get("grid", {}).get("mode", ""),
                ),
            )
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        cursor = self._db.cursor()
        cursor.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def list_runs(self) -> list[dict[str, Any]]:
        cursor = self._db.cursor()
        cursor.execute("SELECT * FROM runs ORDER BY started_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def update_run_status(self, run_id: str, status: str, stopped_at: int | None = None) -> None:
        with self._transaction() as cursor:
            if stopped_at:
                cursor.execute(
                    "UPDATE runs SET status = ?, stopped_at = ? WHERE id = ?",
                    (status, stopped_at, run_id),
                )
            else:
                cursor.execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))

    def save_order(self, run_id: str, order: dict[str, Any]) -> str:
        order_id: str = order.get("id", f"ord_{order.get('client_id', 'unknown')}")

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO orders
                (id, run_id, client_id, symbol, side, type, price, quantity, status,
                 filled_quantity, fee, fee_asset, is_maker, level_index, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    order_id,
                    run_id,
                    order["client_id"],
                    order["symbol"],
                    order["side"],
                    order["type"],
                    order.get("price"),
                    order["quantity"],
                    order["status"],
                    order.get("filled_quantity", "0"),
                    order.get("fee", "0"),
                    order.get("fee_asset", ""),
                    order.get("is_maker", True),
                    order.get("level_index"),
                    order["created_at"],
                    order["updated_at"],
                ),
            )
        return order_id

    def get_order(self, run_id: str, order_id: str) -> dict[str, Any] | None:
        cursor = self._db.cursor()
        cursor.execute("SELECT * FROM orders WHERE run_id = ? AND id = ?", (run_id, order_id))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_order_by_client_id(self, run_id: str, client_id: str) -> dict[str, Any] | None:
        cursor = self._db.cursor()
        cursor.execute(
            "SELECT * FROM orders WHERE run_id = ? AND client_id = ?", (run_id, client_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_order(self, order_id: str, updates: dict[str, Any]) -> None:
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [order_id]

        with self._transaction() as cursor:
            cursor.execute(f"UPDATE orders SET {set_clause} WHERE id = ?", values)

    def get_open_orders(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self._db.cursor()
        cursor.execute(
            """
            SELECT * FROM orders
            WHERE run_id = ? AND status IN ('NEW', 'PARTIALLY_FILLED')
        """,
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def save_fill(self, run_id: str, fill: dict[str, Any]) -> int:
        # Generate dedupe key
        dedupe_key = (
            f"{run_id}:{fill['order_id']}:{fill['price']}:{fill['quantity']}:{fill['timestamp']}"
        )

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR IGNORE INTO fills
                (run_id, order_id, trade_id, price, quantity, fee, fee_asset, is_maker, timestamp, level_index, dedupe_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run_id,
                    fill["order_id"],
                    fill.get("trade_id"),
                    fill["price"],
                    fill["quantity"],
                    fill["fee"],
                    fill["fee_asset"],
                    fill["is_maker"],
                    fill["timestamp"],
                    fill.get("level_index"),
                    dedupe_key,
                ),
            )
            return cursor.lastrowid or 0

    def get_fills(self, run_id: str, order_id: str | None = None) -> list[dict[str, Any]]:
        cursor = self._db.cursor()
        if order_id:
            cursor.execute(
                "SELECT * FROM fills WHERE run_id = ? AND order_id = ?", (run_id, order_id)
            )
        else:
            cursor.execute("SELECT * FROM fills WHERE run_id = ?", (run_id,))
        return [dict(row) for row in cursor.fetchall()]

    def save_grid_state(self, run_id: str, state: dict[str, Any]) -> None:
        import json
        import time

        levels_json = json.dumps(state.get("levels", []))

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO grid_state (run_id, levels_json, updated_at)
                VALUES (?, ?, ?)
            """,
                (run_id, levels_json, int(time.time() * 1000)),
            )

    def get_grid_state(self, run_id: str) -> dict[str, Any] | None:
        cursor = self._db.cursor()
        cursor.execute("SELECT * FROM grid_state WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        if row:
            import json

            return {"levels": json.loads(row["levels_json"]), "updated_at": row["updated_at"]}
        return None

    def save_event(self, run_id: str, event: dict[str, Any]) -> int:
        import time

        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO events (run_id, type, message, level_index, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    run_id,
                    event["type"],
                    event.get("message"),
                    event.get("level_index"),
                    event.get("timestamp", int(time.time() * 1000)),
                ),
            )
            return cursor.lastrowid or 0

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self._db.cursor()
        cursor.execute("SELECT * FROM events WHERE run_id = ? ORDER BY timestamp", (run_id,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
