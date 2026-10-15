# Backtesting

Replays a price path through the real grid strategy and the simulated exchange. Paper trading only:
no API key is used or needed. Source: `src/wallexbot/analytics/` (`backtest.py`, `replay.py`, `report.py`).

## Run it

```bash
.venv/bin/python -m pip install -e .          # once
wallexbot backtest config/grid.example.yaml --from 2026-10-01 --to 2026-10-10 \
    --resolution 15 --output reports/run.md
```

`--from/--to` take ISO dates or unix seconds; `--resolution` is `1, 15, 60, 240, 1D` (Wallex UDF).
The command fetches public candles, runs the grid from `config/`, prints a summary and (with
`--output`) writes a Markdown report that lists its own assumptions.

## What happens in a run

1. First price: the grid is placed. The coins the initial sell levels need are bought as a simulated
   taker at that price (decision D2), so the first sells are funded.
2. Each later price point is offered to the exchange as a trade. Orders whose limit price was traded
   *through* fill (conservative model, decision D4); the strategy answers each fill with its
   counter-order (buy at *i* -> sell at *i+1*, sell at *i* -> buy at *i-1*).
3. Equity (quote + base valued at the current price) is recorded at every point.

## Price path inside a candle

Candles give only open/high/low/close, so four price points are generated: open, the two extremes,
close. A candle that closed up is assumed to have dipped first (open, low, high, close); one that
closed down is assumed to have spiked first (open, high, low, close). Timestamps are spread evenly
inside the candle.

## Accounting (same as the exchange)

- BUY locks `price * quantity` of quote; SELL locks `quantity` of base. No fee is locked.
- A resting limit order fills at **its own price**.
- The fee is charged in the **asset received**: BUY pays it in base, SELL pays it in quote
  (matches Wallex's trade events).

## Metrics

| Metric | Meaning |
|---|---|
| Total return | `(final equity - initial equity) / initial equity`, equity marked at the last price |
| Realized PnL | profit of completed grid cycles: spacing x quantity minus maker fees on both legs |
| Unrealized PnL | total PnL minus realized: held inventory re-valuation and the entry fee |
| Completed cycles / avg profit | number of sells that closed a cycle, and realized / cycles |
| Fees paid | all fees valued in quote |
| Max drawdown | largest peak-to-trough fall of the equity curve |
| Time in range | share of time the price was inside the grid |
| Buy and hold | price change from first to last point (what holding the coin would have returned) |

## Known limitations (read before trusting a number)

- **Fees and minimum order size are placeholders.** The real Wallex tier is not public (decisions
  D16, D17). Re-run with your real rates before drawing conclusions.
- Unlimited liquidity per price point: no queue position, no partial fills, no slippage, no latency.
- Candle extremes are visited in a fixed order; the true intra-candle order is unknown.
- Market orders and the exchange's "2% price move" rule are not simulated; the grid uses limit
  orders only.
- A pause (price left the range) is recorded as an event; counter-orders are still placed.
- One backtest object runs once; create a new one to rerun (exchange state is consumed).
- A short window says little. Judge a grid over weeks and across trending and sideways periods.

## Sanity checks covered by tests

- Sideways price swings produce many profitable cycles; a crash through the whole grid produces
  zero cycles, a negative return and a drawdown.
- A single buy/sell cycle's profit matches an independent calculation from the ledger fills.
- Two fresh runs on the same data give identical results.
- Underfunded grids count rejected orders instead of crashing.


## Fee tiers: `wallexbot fees`

The real Wallex fee is only visible with an API key, so run the same grid at several fees instead of trusting one number:

```bash
wallexbot fees config/grid.example.yaml --from 2026-10-01 --to 2026-10-14 --resolution 240
wallexbot fees my.yaml --from ... --to ... --fees 0.001,0.0025,0.0035   # your own tiers (fractions)
```

It prints cycles, realised profit, fees paid and total return per fee, whether the config check accepts that fee, and the
**break-even fee** for the grid: spacing / (2 x 1.5). Above it the config check refuses the grid, because a cycle would not
beat its round-trip fees with margin. Use `--resolution 240` (hourly bars) for windows longer than a day; see
docs/wallex-api.md for why. Example, USDTTMN example grid, 14 days: 0.05 % earned about 5.1 %, 0.35 % about 4.1 %, break-even
0.63 %. Fills are "conservative" and the result is a replay, not a forecast.


## Does re-centering pay? `wallexbot compare`

Backtests honour `recenter_after_minutes` from the config (the engine and the backtester share one trading session, so the
move is identical in both). `compare` runs the same candles three ways and prints return, realised profit, max drawdown,
cycles and how often the grid moved:

```bash
wallexbot compare config/grid.example.yaml --from 2026-09-15 --to 2026-10-14 --resolution 240 --recenter-after 180
```

Example, USDTTMN example grid, 30 days of hourly candles: the static grid returned 13.1 % (7 cycles), the grid that follows
the price 8.2 % (15 cycles, 6 moves, but 95k realised against 33k), and holding the coin 16.1 %. Following the price earned
more cycle profit and still did worse overall, because it kept re-buying coins at higher prices. Treat this as a reason to look
at your own period before turning the option on, not as a verdict. Replays use conservative fills and are not forecasts.
