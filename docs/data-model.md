# Data Model

## SQLite Schema

### runs
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Run identifier |
| config_hash | TEXT | SHA256 of config |
| config_json | TEXT | Full config JSON |
| status | TEXT | running/paused/halted/completed |
| started_at | INTEGER | Start timestamp (ms) |
| stopped_at | INTEGER | Stop timestamp (ms) |
| market | TEXT | Market symbol |
| mode | TEXT | Grid mode |

### orders
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Order ID |
| run_id | TEXT FK | Run ID |
| client_id | TEXT | Idempotent client ID |
| symbol | TEXT | Market symbol |
| side | TEXT | BUY/SELL |
| type | TEXT | LIMIT/MARKET/STOP_* |
| price | TEXT | Limit price |
| quantity | TEXT | Order quantity |
| status | TEXT | NEW/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED |
| filled_quantity | TEXT | Filled amount |
| fee | TEXT | Accrued fees |
| fee_asset | TEXT | Fee asset |
| is_maker | BOOLEAN | Maker/taker |
| level_index | INTEGER | Grid level |
| created_at | INTEGER | Creation timestamp (ms) |
| updated_at | INTEGER | Last update timestamp (ms) |

### fills
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Fill ID |
| run_id | TEXT FK | Run ID |
| order_id | TEXT FK | Order ID |
| trade_id | TEXT | Exchange trade ID |
| price | TEXT | Fill price |
| qty | TEXT | Fill quantity |
| fee | TEXT | Fee amount |
| fee_asset | TEXT | Fee asset |
| is_maker | BOOLEAN | Maker/taker |
| ts | INTEGER | Fill timestamp (ms) |
| dedupe_key | TEXT UNIQUE | Deduplication key |

### grid_state
| Column | Type | Description |
|--------|------|-------------|
| run_id | TEXT PK | Run ID |
| levels_json | TEXT | Grid levels JSON |
| updated_at | INTEGER | Last update |

### events
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Event ID |
| run_id | TEXT FK | Run ID |
| type | TEXT | Event type |
| message | TEXT | Human-readable message |
| level_index | INTEGER | Grid level |
| ts | INTEGER | Timestamp (ms) |

### balance_snapshots
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Snapshot ID |
| run_id | TEXT FK | Run ID |
| ts | INTEGER | Timestamp (ms) |
| asset | TEXT | Asset symbol |
| free | TEXT | Free balance |
| locked | TEXT | Locked balance |

### pnl_snapshots
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Snapshot ID |
| run_id | TEXT FK | Run ID |
| ts | INTEGER | Timestamp (ms) |
| realized | TEXT | Realized PnL |
| unrealized | TEXT | Unrealized PnL |
| fees | TEXT | Cumulative fees |
| equity | TEXT | Total equity (quote) |
| inventory | TEXT | Base inventory |
| price | TEXT | Current price |

### config_versions
| Column | Type | Description |
|--------|------|-------------|
| run_id | TEXT PK | Run ID |
| config_hash | TEXT | Config hash |
| config_json | TEXT | Full config JSON |

## Indexes

- `idx_orders_run_id` on orders(run_id)
- `idx_orders_client_id` on orders(client_id)
- `idx_fills_run_id` on fills(run_id)
- `idx_fills_order_id` on fills(order_id)
- `idx_events_run_id` on events(run_id)
- `idx_balance_snapshots_run_ts` on balance_snapshots(run_id, ts)
- `idx_pnl_snapshots_run_ts` on pnl_snapshots(run_id, ts)
- `idx_price_ticks_market_ts` on price_ticks(market, ts)
- `idx_candles_market_res_time` on candles(market, resolution, open_time)

## Retention

| Data | Retention |
|------|-----------|
| Price ticks (raw) | 14 days |
| Price ticks (1m bars) | 90 days |
| Candles (1m) | 90 days |
| Candles (higher) | Forever |
| Fills/Orders/PnL/Events | Forever |
| Balance snapshots | 90 days |