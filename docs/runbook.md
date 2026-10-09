# Runbook

## Starting the Bot

### Paper Trading (CLI)
```bash
wallexbot paper config/grid.example.yaml
```

### Paper Trading (Web UI)
```bash
wallexbot ui
# Open http://127.0.0.1:8080
```

### Backtesting
```bash
wallexbot backtest config/grid.example.yaml --from 2024-01-01 --to 2024-01-31
```

## Stopping the Bot

### Graceful Shutdown (SIGINT/Ctrl+C)
1. Stops placing new orders
2. Waits for pending order confirmations
3. Cancels all open orders (configurable)
4. Flushes state to SQLite
5. Exits

### Kill Switch (Web UI / API)
Immediately cancels all orders and halts the engine.

### Emergency Stop
If the bot crashes, restart it — it will recover from SQLite.

## Crash Recovery

On restart, the bot:
1. Loads last run from SQLite
2. Reconciles open orders by `client_id` with exchange
3. Replays any missed fills from event log
4. Resumes grid from recovered state

## Reading Logs

Logs are JSON lines with:
- `timestamp`: ISO8601
- `level`: DEBUG/INFO/WARNING/ERROR
- `logger`: Module name
- `message`: Human-readable
- `run_id`: Current run ID (if applicable)
- `event`: Structured event data

Example:
```json
{"timestamp": "2024-01-15T10:30:00Z", "level": "INFO", "logger": "engine", "message": "Fill at level 3", "run_id": "run_abc123", "event": {"type": "fill", "level": 3, "qty": "10.0000"}}
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "Insufficient free balance" | Not enough quote/base for orders | Check initial_balance in config |
| "Order notional below minimum" | Grid too tight / capital too low | Increase range or investment |
| "Rate limit exceeded" | Too many orders placed | Reduce grid_count or increase spacing |
| "Price out of range" | Market moved beyond grid | Bot pauses automatically; check UI |

## Backup/Restore

### Backup Database
```bash
cp wallexbot.db wallexbot.db.backup
```

### Restore Database
```bash
cp wallexbot.db.backup wallexbot.db
```

## Monitoring

Key metrics to watch:
- `orders_placed` / `orders_cancelled` / `orders_filled`
- `realized_pnl` / `unrealized_pnl`
- `max_drawdown`
- `feed_latency_ms`
- `errors_total`

## Health Check

```bash
curl http://127.0.0.1:8080/api/health
# {"status": "ok"}
```