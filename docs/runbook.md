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
wallexbot ui                  # http://127.0.0.1:8080, runs kept in memory
wallexbot ui --db runs.db     # keep runs in SQLite
```
Pages: **Configure** (live checks that the grid can beat its fees, save/reset), **Backtest**,
**Paper trading** (start, pause, resume, stop, kill switch, live ladder, orders, fills, balances),
**Runs**, **Dashboard**. English and Persian (RTL) with a switch in the header. The configuration you
save on the Configure page is kept in the browser and used by Backtest and Paper trading.

The dashboard has no login and can start runs, so it only listens on this machine. `--allow-remote`
overrides that (with a warning); put it behind something that authenticates before you do.

The History and Settings pages are not implemented yet and are not linked.

## Stopping the Bot

### Ctrl+C
Stops the engine, cancels all resting orders (unless `cancel_on_shutdown` is off), prints the final
summary and exits.

### Kill switch
Automatic: a risk limit (`risk.max_drawdown`, `risk.daily_loss_limit`) cancels every order and halts
the run, and says why in the summary. By hand: the **Kill switch** button on the Paper trading page
(or `POST /api/runs/{id}/kill`, or `engine.kill("reason")` in code).

## Crash recovery

A paper run saves a **checkpoint** (the whole state of its simulated exchange, grid, balances and
bookkeeping) to the database whenever something changes, and at least every 20 prices. This needs
`--db` (CLI) or `wallexbot ui --db` (dashboard). If the process dies (crash, power loss, `kill -9`),
the run is left marked `running` with its checkpoint.

```bash
wallexbot paper --resume --db runs.db            # the interrupted run (asks if there are several)
wallexbot paper --resume RUN_ID --db runs.db     # a specific one
```
In the dashboard, an interrupted run shows as **Interrupted** on the Runs page and a **Recover**
banner appears on the Paper trading page.

What recovery does:
1. Restores the exact state: balances, resting orders (including part-filled ones), grid levels,
   profit so far, fees, risk baselines. The run keeps its id and record.
2. Fetches the public one-minute prices for the downtime and replays them on simulated time, so
   orders that would have filled while the bot was off do fill, at their own limit prices, as resting
   orders would on a real exchange.
3. Carries on with live prices.

Limits to know about:
- Replay uses one-minute candles (four price points each), not the real trade prints, so what
  happened inside a minute is approximated. A gap longer than 24 hours is **not** replayed; the first
  live price is used instead, and the recovery note says so.
- Prices seen after the last checkpoint and before the crash are covered by the same replay.
- Only runs that were interrupted can be recovered. A run you stopped, or that the kill switch or a
  risk limit halted, is finished and is refused (with the reason).
- This is a simulator, so a crash can never leave real orders on an exchange: there are none.

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