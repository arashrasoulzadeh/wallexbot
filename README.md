# Wallex Grid Bot

A grid trading bot for Wallex exchange — **paper trading only, no API keys required**.

## ⚠️ Safety Statement

This bot **does not trade real money**. It uses only public Wallex endpoints (markets, depth, trades, candles, public WebSocket) and a local simulated exchange. No API keys are ever stored or used. Real trading is explicitly out of scope.

## Quickstart

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run tests
make check

# Run the CLI
wallexbot --help
```

## Commands

```bash
# List spot markets
wallexbot markets

# Validate config and show derived values
wallexbot config check config/grid.example.yaml

# Run backtest
wallexbot backtest config/grid.example.yaml --from 2024-01-01 --to 2024-01-31

# Run paper trading on live public prices
wallexbot paper config/grid.example.yaml

# Generate report for a run
wallexbot report <run-id>

# Start web dashboard
wallexbot ui
```

## Configuration

See `config/grid.example.yaml` for a complete example with all options documented.

## Project Structure

```
src/wallexbot/
├── domain/      # Core types, money math (pure, no I/O)
├── strategy/    # Grid strategy logic (pure functions/state machines)
├── sim/         # Simulated exchange (paper trading)
├── wallex/      # Public Wallex data client (REST + WebSocket)
├── engine/      # Bot engine (wiring strategy ↔ exchange ↔ data)
├── storage/     # SQLite persistence and history
├── analytics/   # Backtesting and analytics
├── api/         # FastAPI backend for web UI
├── ui/          # Jinja2 + HTMX frontend
└── cli.py       # Command-line interface
```

## Development

All development and testing happens locally in a venv. Docker is only for packaging (Phase 15).

```bash
# Run all quality checks
make check

# Run tests only
make test

# Run with coverage
make cov

# Type checking
make type

# Linting
make lint
```

## Documentation

- [Architecture](docs/architecture.md)
- [Config Reference](docs/config-reference.md)
- [CLI Guide](docs/cli.md)
- [Backtesting](docs/backtesting.md)
- [UI Guide](docs/ui-guide.md)
- [Runbook](docs/runbook.md)
- [Decisions](docs/decisions/)

## License

MIT