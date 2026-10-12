# Paper trading (live prices, simulated orders)

`wallexbot paper` runs the grid against **live public Wallex prices** with **simulated orders**. No
API key is used and nothing is ever sent to Wallex except public reads, so no real money can move.

```bash
wallexbot paper config/grid.example.yaml                       # until Ctrl+C
wallexbot paper config/grid.example.yaml --duration 3600       # stop after an hour
wallexbot paper config/grid.example.yaml --feed poll           # REST polling instead of WebSocket
wallexbot paper config/grid.example.yaml --db reports/run.db   # also record the run in SQLite
```

## What it does

1. Loads the config and the market's real precisions (`GET /hector/web/v1/markets`).
2. Waits for the **first live trade** and builds the grid around that price. The coins the sell
   levels need are bought as a simulated taker (decision D2).
3. Offers every later trade price to the simulated exchange. Orders whose limit price was traded
   *through* fill (conservative model, D4). Each fill is answered with a counter-order.
4. Watches the risk limits from the config (`risk.max_drawdown`, `risk.daily_loss_limit`). If one
   is exceeded the engine **halts**: all orders are cancelled and trading stops.
5. Prints a status line every `--status-every` seconds and a summary at the end.

## Price feeds

| Feed | Source | Notes |
|---|---|---|
| `ws` (default) | public `wss://api.wallex.ir/ws`, channel `<SYMBOL>@trade` | reconnects with backoff; rotates the connection before the server's 30-minute cutoff |
| `poll` | `GET /v1/trades`, latest trade every 2 s | slower, needs only HTTPS |

Only real trade prints become ticks. A quiet market produces few ticks (about 5 in 40 seconds on
USDTTMN in a test run), which is normal.

## States

`idle -> running -> stopped | halted | failed`

- **stopped**: the feed ended, or you stopped it (Ctrl+C). Resting orders are cancelled
  (`cancel_on_shutdown`, default on).
- **halted**: the kill switch or a risk limit fired. All orders are cancelled. This is a normal
  outcome, not an error.
- **failed**: an unexpected error. Orders are cancelled and the error is raised.

## Rate limit

Wallex allows 20 order placements per 10 seconds; the simulator enforces the same. A grid with more
than 20 levels is placed in batches: orders over the limit wait and go out on later ticks
(they are *deferred*, not dropped). Cancellations are not limited.

## What is simulated, and what is not

- Orders only exist in the simulator. Fills assume unlimited liquidity at the traded price: no
  queue position, partial fills, slippage or latency. Real trading would do worse.
- Fees are charged in the asset received, using the rates in the config's `simulation` section.
  **Those rates are placeholders** (the real tier is only visible with a Wallex account).
- Market orders are not simulated.

## In code

```python
from wallexbot.engine import BotEngine, EngineConfig, RiskMonitor

engine = BotEngine(EngineConfig(strategy=..., exchange=..., price_feed=..., risk=RiskMonitor(...)))
task = engine.start()      # or: await engine.run()
engine.status()            # snapshot: state, price, equity, orders, fills, cycles, PnL, events
engine.kill("reason")      # kill switch, safe from anywhere
await engine.stop()        # graceful stop
```
