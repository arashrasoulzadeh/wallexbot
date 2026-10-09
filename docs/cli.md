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
Get intelligent grid suggestions.

```bash
wallexbot suggest --market USDTTMN --capital 2000000
```

### wallexbot optimize
Run parameter optimization.

```bash
wallexbot optimize --market USDTTMN --from 2024-01-01 --to 2024-06-30
```

### wallexbot regime
Check current market regime.

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