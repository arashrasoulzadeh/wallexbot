# Runbook

## Starting the Bot

### Paper Trading (CLI)
```bash
wallexbot paper config/grid.example.yaml
```

### Backtesting
```bash
wallexbot backtest config/grid.example.yaml --from 2026-10-01 --to 2026-10-10 --resolution 15
```
See [backtesting.md](backtesting.md).

### Web UI
```bash
wallexbot ui      # http://127.0.0.1:8080
```
**Status:** the pages and read endpoints exist, but starting, pausing and killing runs from the UI is
not connected to the engine yet (the run-control endpoints are placeholders). Use the CLI.

## Stopping the Bot

### Ctrl+C
Stops the engine, cancels all resting orders (unless `cancel_on_shutdown` is off), prints the final
summary and exits.

### Kill switch
Automatic: a risk limit (`risk.max_drawdown`, `risk.daily_loss_limit`) cancels every order and halts
the run, and says why in the summary. Programmatic: `engine.kill("reason")`. There is no UI button yet.

## Crash recovery

**Not implemented.** A run is recorded with `--db` (run, orders, fills, events), but restarting does
not resume it; a new run starts a fresh grid at the current price. Since paper orders exist only in
memory, nothing can be left resting on an exchange after a crash.

See [paper-trading.md](paper-trading.md) for how a paper run behaves.

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