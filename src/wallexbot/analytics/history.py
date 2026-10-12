"""History and analytics storage."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class HistoryRepository:
    """Extended repository for full history analytics."""

    db_path: str
    _conn: sqlite3.Connection | None = None

    def __post_init__(self) -> None:
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
        self._create_tables()

    def _create_tables(self) -> None:
        """Create all history tables."""
        cursor = self._db.cursor()

        # Price ticks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                ts INTEGER NOT NULL,
                price TEXT NOT NULL,
                source TEXT NOT NULL,
                UNIQUE(market, ts, source)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_price_ticks_market_ts ON price_ticks(market, ts)"
        )

        # Market trades
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                ts INTEGER NOT NULL,
                price TEXT NOT NULL,
                qty TEXT NOT NULL,
                is_buy BOOLEAN NOT NULL,
                UNIQUE(market, ts, price, qty)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_trades_market_ts ON market_trades(market, ts)"
        )

        # Candles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                resolution TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                open TEXT NOT NULL,
                high TEXT NOT NULL,
                low TEXT NOT NULL,
                close TEXT NOT NULL,
                volume TEXT NOT NULL,
                UNIQUE(market, resolution, open_time)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_candles_market_res_time ON candles(market, resolution, open_time)"
        )

        # Orders and events
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                type TEXT NOT NULL,
                price TEXT,
                quantity TEXT NOT NULL,
                status TEXT NOT NULL,
                filled_quantity TEXT DEFAULT '0',
                fee TEXT DEFAULT '0',
                fee_asset TEXT,
                is_maker BOOLEAN DEFAULT 1,
                level_index INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_run_id ON orders(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL REFERENCES orders(id),
                type TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                filled_qty TEXT,
                fee TEXT,
                timestamp INTEGER NOT NULL
            )
        """)

        # Fills
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                order_id TEXT NOT NULL REFERENCES orders(id),
                level_index INTEGER,
                price TEXT NOT NULL,
                qty TEXT NOT NULL,
                fee TEXT NOT NULL,
                fee_asset TEXT NOT NULL,
                is_maker BOOLEAN NOT NULL,
                ts INTEGER NOT NULL,
                dedupe_key TEXT UNIQUE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fills_run_id ON fills(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fills_order_id ON fills(order_id)")

        # Grid cycles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS grid_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                buy_fill_id INTEGER NOT NULL REFERENCES fills(id),
                sell_fill_id INTEGER NOT NULL REFERENCES fills(id),
                profit TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                completed_at INTEGER NOT NULL
            )
        """)

        # Balance snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS balance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ts INTEGER NOT NULL,
                asset TEXT NOT NULL,
                free TEXT NOT NULL,
                locked TEXT NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_balance_snapshots_run_ts ON balance_snapshots(run_id, ts)"
        )

        # PnL snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pnl_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ts INTEGER NOT NULL,
                realized TEXT NOT NULL,
                unrealized TEXT NOT NULL,
                fees TEXT NOT NULL,
                equity TEXT NOT NULL,
                inventory TEXT NOT NULL,
                price TEXT NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pnl_snapshots_run_ts ON pnl_snapshots(run_id, ts)"
        )

        # Run events
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT,
                level_index INTEGER,
                ts INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_events_run_ts ON run_events(run_id, ts)")

        # Config versions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_versions (
                run_id TEXT PRIMARY KEY,
                config_hash TEXT NOT NULL,
                config_json TEXT NOT NULL
            )
        """)

        # Schema migrations tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history_schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at INTEGER NOT NULL
            )
        """)

        self._db.commit()

    @contextmanager
    def _transaction(self) -> Any:
        cursor = self._db.cursor()
        try:
            yield cursor
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    # Price ticks
    def record_price_tick(self, market: str, ts: int, price: Decimal, source: str) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR IGNORE INTO price_ticks (market, ts, price, source)
                VALUES (?, ?, ?, ?)
            """,
                (market, ts, str(price), source),
            )

    def get_price_ticks(self, market: str, from_ts: int, to_ts: int) -> list[dict[str, Any]]:
        cursor = self._db.cursor()
        cursor.execute(
            """
            SELECT * FROM price_ticks
            WHERE market = ? AND ts BETWEEN ? AND ?
            ORDER BY ts
        """,
            (market, from_ts, to_ts),
        )
        return [dict(row) for row in cursor.fetchall()]

    # Market trades
    def record_market_trade(
        self, market: str, ts: int, price: Decimal, qty: Decimal, is_buy: bool
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR IGNORE INTO market_trades (market, ts, price, qty, is_buy)
                VALUES (?, ?, ?, ?, ?)
            """,
                (market, ts, str(price), str(qty), is_buy),
            )

    # Candles
    def record_candle(self, market: str, resolution: str, candle: dict[str, Any]) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO candles (market, resolution, open_time, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    market,
                    resolution,
                    candle["open_time"],
                    str(candle["open"]),
                    str(candle["high"]),
                    str(candle["low"]),
                    str(candle["close"]),
                    str(candle["volume"]),
                ),
            )

    def get_candles(
        self, market: str, resolution: str, from_ts: int, to_ts: int
    ) -> list[dict[str, Any]]:
        cursor = self._db.cursor()
        cursor.execute(
            """
            SELECT * FROM candles
            WHERE market = ? AND resolution = ? AND open_time BETWEEN ? AND ?
            ORDER BY open_time
        """,
            (market, resolution, from_ts, to_ts),
        )
        return [dict(row) for row in cursor.fetchall()]

    # Orders
    def record_order(self, run_id: str, order: dict[str, Any]) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO orders
                (id, run_id, client_id, symbol, side, type, price, quantity, status,
                 filled_quantity, fee, fee_asset, is_maker, level_index, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    order["id"],
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

    def record_order_event(
        self,
        order_id: str,
        event_type: str,
        old_status: str,
        new_status: str,
        filled_qty: str,
        fee: str,
        ts: int,
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO order_events (order_id, type, old_status, new_status, filled_qty, fee, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (order_id, event_type, old_status, new_status, filled_qty, fee, ts),
            )

    # Fills
    def record_fill(self, run_id: str, fill: dict[str, Any]) -> int:
        dedupe_key = f"{run_id}:{fill['order_id']}:{fill['price']}:{fill['qty']}:{fill['ts']}"
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR IGNORE INTO fills
                (run_id, order_id, level_index, price, qty, fee, fee_asset, is_maker, ts, dedupe_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run_id,
                    fill["order_id"],
                    fill.get("level_index"),
                    fill["price"],
                    fill["qty"],
                    fill["fee"],
                    fill["fee_asset"],
                    fill["is_maker"],
                    fill["ts"],
                    dedupe_key,
                ),
            )
            return cursor.lastrowid or 0

    # Grid cycles
    def record_grid_cycle(
        self,
        run_id: str,
        buy_fill_id: int,
        sell_fill_id: int,
        profit: Decimal,
        duration_ms: int,
        completed_at: int,
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO grid_cycles (run_id, buy_fill_id, sell_fill_id, profit, duration_ms, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (run_id, buy_fill_id, sell_fill_id, str(profit), duration_ms, completed_at),
            )

    # Balance snapshots
    def record_balance_snapshot(
        self, run_id: str, ts: int, balances: dict[str, tuple[Decimal, Decimal]]
    ) -> None:
        with self._transaction() as cursor:
            for asset, (free, locked) in balances.items():
                cursor.execute(
                    """
                    INSERT INTO balance_snapshots (run_id, ts, asset, free, locked)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (run_id, ts, asset, str(free), str(locked)),
                )

    # PnL snapshots
    def record_pnl_snapshot(
        self,
        run_id: str,
        ts: int,
        realized: Decimal,
        unrealized: Decimal,
        fees: Decimal,
        equity: Decimal,
        inventory: Decimal,
        price: Decimal,
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO pnl_snapshots (run_id, ts, realized, unrealized, fees, equity, inventory, price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run_id,
                    ts,
                    str(realized),
                    str(unrealized),
                    str(fees),
                    str(equity),
                    str(inventory),
                    str(price),
                ),
            )

    # Run events
    def record_run_event(
        self, run_id: str, event_type: str, message: str, level_index: int, ts: int
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO run_events (run_id, type, message, level_index, ts)
                VALUES (?, ?, ?, ?, ?)
            """,
                (run_id, event_type, message, level_index, ts),
            )

    # Config versions
    def record_config(self, run_id: str, config_hash: str, config_json: str) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO config_versions (run_id, config_hash, config_json)
                VALUES (?, ?, ?)
            """,
                (run_id, config_hash, config_json),
            )

    # Analytics queries
    def get_pnl_timeseries(self, run_id: str, resolution: str = "1h") -> list[dict[str, Any]]:
        """Get PnL time series at given resolution."""
        cursor = self._db.cursor()
        cursor.execute(
            """
            SELECT ts, realized, unrealized, fees, equity, inventory, price
            FROM pnl_snapshots
            WHERE run_id = ?
            ORDER BY ts
        """,
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_profit_breakdown(self, run_id: str) -> dict[str, Any]:
        """Get profit breakdown by day/week/month/level/cycle."""
        cursor = self._db.cursor()

        # By cycle
        cursor.execute(
            """
            SELECT profit, completed_at FROM grid_cycles WHERE run_id = ?
        """,
            (run_id,),
        )
        cycles = [dict(row) for row in cursor.fetchall()]

        total_profit = sum(Decimal(c["profit"]) for c in cycles)
        winning = [c for c in cycles if Decimal(c["profit"]) > 0]
        losing = [c for c in cycles if Decimal(c["profit"]) < 0]

        return {
            "total_profit": str(total_profit),
            "total_cycles": len(cycles),
            "winning_cycles": len(winning),
            "losing_cycles": len(losing),
            "avg_win": str(sum(Decimal(c["profit"]) for c in winning) / len(winning))
            if winning
            else "0",
            "avg_loss": str(sum(Decimal(c["profit"]) for c in losing) / len(losing))
            if losing
            else "0",
        }

    def get_drawdown_series(self, run_id: str) -> list[dict[str, Any]]:
        """Get drawdown series."""
        cursor = self._db.cursor()
        cursor.execute(
            """
            SELECT ts, equity FROM pnl_snapshots WHERE run_id = ? ORDER BY ts
        """,
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_trade_stats(self, run_id: str) -> dict[str, Any]:
        """Get trade statistics."""
        cursor = self._db.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) as count, AVG(CAST(qty AS REAL)) as avg_size
            FROM fills WHERE run_id = ?
        """,
            (run_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}

    def reconstruct_state_at(self, run_id: str, ts: int) -> dict[str, Any]:
        """Reconstruct grid state at timestamp."""
        # Get orders at that time
        cursor = self._db.cursor()
        cursor.execute(
            """
            SELECT * FROM orders
            WHERE run_id = ? AND created_at <= ?
            ORDER BY created_at
        """,
            (run_id, ts),
        )
        orders = [dict(row) for row in cursor.fetchall()]

        # Get fills up to that time
        cursor.execute(
            """
            SELECT * FROM fills WHERE run_id = ? AND ts <= ?
            ORDER BY ts
        """,
            (run_id, ts),
        )
        fills = [dict(row) for row in cursor.fetchall()]

        # Get balance snapshot at or before that time
        cursor.execute(
            """
            SELECT * FROM balance_snapshots
            WHERE run_id = ? AND ts <= ?
            ORDER BY ts DESC LIMIT 1
        """,
            (run_id, ts),
        )
        balance = cursor.fetchone()

        return {
            "orders": orders,
            "fills": fills,
            "balance": dict(balance) if balance else None,
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
