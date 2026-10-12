"""Database migrations for SQLite schema."""

import sqlite3

MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        config_hash TEXT NOT NULL,
        config_json TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at INTEGER NOT NULL,
        stopped_at INTEGER,
        market TEXT NOT NULL,
        mode TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
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
        updated_at INTEGER NOT NULL,
        UNIQUE(run_id, client_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL REFERENCES runs(id),
        order_id TEXT NOT NULL REFERENCES orders(id),
        trade_id TEXT,
        price TEXT NOT NULL,
        quantity TEXT NOT NULL,
        fee TEXT NOT NULL,
        fee_asset TEXT NOT NULL,
        is_maker BOOLEAN NOT NULL,
        timestamp INTEGER NOT NULL,
        level_index INTEGER,
        dedupe_key TEXT UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS grid_state (
        run_id TEXT PRIMARY KEY REFERENCES runs(id),
        levels_json TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL REFERENCES runs(id),
        type TEXT NOT NULL,
        message TEXT,
        level_index INTEGER,
        timestamp INTEGER NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_orders_run_id ON orders(run_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fills_run_id ON fills(run_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fills_order_id ON fills(order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS checkpoints (
        run_id TEXT PRIMARY KEY REFERENCES runs(id),
        data_json TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS snapshots (
        run_id TEXT NOT NULL REFERENCES runs(id),
        ts INTEGER NOT NULL,
        price TEXT,
        equity TEXT NOT NULL,
        realized TEXT NOT NULL,
        fees TEXT NOT NULL,
        open_orders INTEGER NOT NULL,
        fills INTEGER NOT NULL,
        cycles INTEGER NOT NULL,
        PRIMARY KEY (run_id, ts)
    )
    """,
]


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run all pending migrations."""
    cursor = conn.cursor()

    # Create migrations tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at INTEGER NOT NULL
        )
    """)

    # Get applied migrations
    cursor.execute("SELECT version FROM schema_migrations")
    applied = {row[0] for row in cursor.fetchall()}

    # Apply pending migrations
    for i, migration in enumerate(MIGRATIONS, 1):
        if i not in applied:
            cursor.executescript(migration)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (i, int(__import__("time").time() * 1000)),
            )

    conn.commit()
