# CLI Guide

## Commands

### wallexbot markets
List all spot markets with precision info.

```bash
wallexbot markets
```

### wallexbot config check
Validate config file and show derived values.

```bash
wallexbot config check config/grid.example.yaml
```

### wallexbot fetch-candles
Download historical candles to CSV.

```bash
wallexbot fetch-candles USDTTMN --resolution 60 --from 2024-01-01 --to 2024-01-31 --output candles.csv
```

### wallexbot backtest
Run backtest on historical data.

```bash
wallexbot backtest config/grid.example.yaml --from 2024-01-01 --to 2024-01-31 --output report.md
```

### wallexbot fees
Backtest one grid at several fee tiers and print the break-even fee (the real Wallex fee needs an API key, so
this replaces guessing). See [backtesting.md](backtesting.md#fee-tiers-wallexbot-fees).

```bash
wallexbot fees config/grid.example.yaml --from 2026-10-01 --to 2026-10-14 --resolution 240
wallexbot fees my.yaml --from 2026-10-01 --to 2026-10-14 --fees 0.001,0.0035
```

### wallexbot paper
Run paper trading on live public prices.

```bash
wallexbot paper config/grid.example.yaml
```

Press `Ctrl+C` to stop gracefully.

### wallexbot report
Generate report for a completed run.

```bash
wallexbot report run_abc123
```

### wallexbot ui
Start web dashboard.

```bash
wallexbot ui --host 127.0.0.1 --port 8080
```

Then open http://127.0.0.1:8080 in browser.

### wallexbot suggest
Get intelligent grid suggestions from the last 14 days of hourly candles.

```bash
wallexbot suggest --market USDTTMN --capital 2000000
```

### wallexbot optimize
Run parameter optimization.

```bash
wallexbot optimize --market USDTTMN --from 2024-01-01 --to 2024-06-30
```

### wallexbot regime
Check the current market regime from the last 14 days of hourly candles.

```bash
wallexbot regime --market USDTTMN
```

## Global Options

- `--help`: Show help
- `--version`: Show version
- `-v, --verbose`: Verbose logging
- `-q, --quiet`: Quiet mode

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Config validation failed |
| 130 | Interrupted (Ctrl+C) |