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

## From the web UI

`wallexbot ui` starts the same engine behind a dashboard. The **Paper trading** page starts a run with
the configuration saved on the **Configure** page, shows it live (a WebSocket pushes a snapshot every
second) and has pause, resume, stop and kill buttons. Several runs can exist; the page follows the one
you started (its id is remembered in the browser).

API (JSON, all paper only): `POST /api/paper-runs`, `GET /api/runs`, `GET /api/runs/{id}` (plus
`/orders`, `/fills`, `/pnl`, `/grid`), `POST /api/runs/{id}/pause|resume|stop|kill`,
`POST /api/backtests`, `GET /api/backtests/{id}`, `GET /api/config/default`,
`POST /api/config/validate`, `GET /api/markets`, `GET /api/markets/{symbol}/defaults`, `WS /api/stream?run_id=`. Unknown runs are 404, a request that does not
fit the run's state (e.g. pausing a stopped run) is 409. There is no endpoint that accepts an API key
and no live mode.

Live figures exist for runs of the current server process. After a restart, runs are listed from the
database (with `--db`); one that was interrupted can be recovered (see the runbook), and the others
show their stored record.

`POST /api/runs/{id}/recover` continues an interrupted run (404 unknown, 409 if it is already live or
finished).

## Auto re-centering (optional)

By default a grid is fixed: when the price leaves its range the run pauses and says so (and alerts you on Telegram).
Set `recenter_after_minutes` (Configure page: "Move the grid after (minutes)", or `strategy.grid.recenter_after_minutes`
in the YAML) and, once the price has stayed outside the range that long, the engine cancels the resting orders and builds
a grid of the same width and level count around the current price.

- Nothing is sold to do it. Coins already held fund the new sell orders and only a shortfall is bought (as a simulated
  taker, like at the start). Profit totals, cycle counts and order numbering carry on; the new grid's order ids carry a
  generation tag so they never collide with the cancelled ones.
- At most one move per hour, so a coin that keeps running away is not chased every minute. Coming back inside the range
  resets the wait.
- The stored run config is updated with the new range, so a crash recovers into the grid that was live, not the original
  one (tested end to end). The risk limits (max drawdown, daily loss) keep working on the whole run.
- It does not realise the loss on coins bought higher: moving the grid up after a rise leaves you holding them, and moving
  it down after a fall means the new sells sit below your cost. That is the nature of re-centering; watch the drawdown.
- Paper only, off by default; an alert of kind `recentered` is sent to Telegram when it happens.

## All Wallex coins

Every Wallex spot market (373 at the last check, TMN- and USDT-quoted) can be used, not only USDTTMN.

- The **All coins** page (`/markets`) lists them with price, 24 h change and minimum order; search, filter by
  quote currency, sort by name or change. Each row links to Configure and to Market status.
- `GET /api/markets/{symbol}/defaults` returns a starting grid sized for that coin
  (`src/wallexbot/market_defaults.py`): half-width 1-5 % around the price, spacing about 0.45 %
  (clear of the round-trip fee), 3-20 levels, and enough capital per level to clear the minimum order after
  quantity-step rounding. Starting capital defaults to 2,000,000 TMN or 100 USDT. The response says whether the
  grid passes validation. It is a place to start, not a recommendation; 404 for an unknown market, 422 for one
  with no price (inactive).
- Configure loads these values when you pick a coin (or open `/configure?symbol=BTCTMN`); you review and save.
  Market status accepts `?symbol=` the same way.
- The list also shows each coin's 7-day change (Wallex's `change_7D`). Market status has a "last 7 days" card from
  hourly candles (`GET /api/markets/{symbol}/week`): high, low, range, where the price sits in it, and the average and
  biggest hourly high-low span. Those hourly figures show how far a coin usually travels in an hour, which is the
  scale a grid's spacing should be compared with. The grid defaults do not use them yet.
- Every table with a header row sorts by clicking a column (again to reverse); the choice survives refreshes. Empty
  values always go last. The grid ladder on the Paper page is not sortable.
- Wallex does not currently report 24 h turnover for spot markets, so the list cannot be ranked by popularity;
  the page then sorts by name and shows "-" for turnover.
- Per-coin defaults assume the **worst published fee tier** (TMN 0.35 %, USDT 0.20 %, from a third-party article about
  a year old; the account's real fee needs an API key) and space the levels at least 10 % above the validator's
  break-even (round trip x 1.5). With a 0.35 % fee that means levels about 1.2-1.5 % apart, so the grid trades far less
  often than the old 0.45 % spacing did, but a cycle really earns money. When the week's candles are available,
  busier coins get wider spacing (about three-quarters of the usual hourly high-low span, at most 3 %). The generic
  example config (`config/grid.example.yaml`) uses the same 0.35 % fee and a 255,000-275,000 grid of 5 levels.
- The minimum order shown is Wallex's OTC minimum, used as a hint; the real spot minimum and fee tier are still
  unknown (placeholders: maker 0.0005, taker 0.001, 90,000 TMN).
- Tests run the defaults for all 373 recorded markets and start paper runs from them
  (`tests/unit/test_market_defaults.py`, `tests/unit/api/test_api_live.py`).

## Crash recovery

`wallexbot paper --resume --db runs.db` continues a run that a crash interrupted, from its last
checkpoint, replaying the downtime's public prices first. Details and limits: [runbook.md](runbook.md).

## History

Every recorded run (CLI with `--db`, or `wallexbot ui`) keeps a time series of price and equity (one
point at the first price, on every fill, and at most every 30 s otherwise) next to its trades and events.
The **History** page and `GET /api/history/runs[/{id}]` turn that into:

- headline numbers (return, price change if you had just held, realized PnL, fees, cycles, fills,
  max drawdown, traded volume, duration);
- an equity curve and a price chart with a marker for every buy and sell;
- a day-by-day table (days end at midnight **Tehran time**, UTC+03:30; `?tz=` changes the zone);
- the trades (filter by side) and the event log;
- CSV downloads of the trades and of the price/equity history.

A time range (last hour / 24 h / 7 d / whole run) limits all of it at once. For a range, the summary
counts only what happened inside it, measured from the last snapshot before it; for the whole run it
starts from the initial equity, so the entry fee is included and the return matches the engine's own.
Charts are thinned to at most 600 points (`max_points`), the numbers use every point.
