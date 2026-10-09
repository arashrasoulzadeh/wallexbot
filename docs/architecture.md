# Architecture

## Overview

Wallex Grid Bot is a paper trading grid trading bot for Wallex exchange. It uses only public endpoints and a local simulated exchange — no API keys are ever stored or used.

## Layers

```
┌─────────────────────────────────────┐
│  CLI / Web UI                       │
├─────────────────────────────────────┤
│  Engine (async event loop)          │
├─────────────────────────────────────┤
│  Strategy (pure grid logic)         │
├─────────────────────────────────────┤
│  Simulated Exchange / Wallex Client │
├─────────────────────────────────────┤
│  Domain (types, money math)         │
├─────────────────────────────────────┤
│  Storage (SQLite)                   │
└─────────────────────────────────────┘
```

## Data Flow

```
Price Feed (WebSocket/Replay)
         │
         ▼
    Strategy.on_price()
         │
         ▼
    Actions (Place/Cancel/Pause/Alert)
         │
         ▼
    ActionExecutor ──▶ Exchange
         │                │
         ▼                ▼
    Fill Events ◀──── Order Events
         │
         ▼
    Strategy.on_fill()
         │
         ▼
    Counter Actions ──▶ Exchange
         │
         ▼
    History/Analytics (SQLite)
```

## Module Map

| Package | Responsibility |
|---------|----------------|
| `wallexbot.domain` | Core types, money math (pure, no I/O) |
| `wallexbot.strategy.grid` | Grid strategy logic (pure functions/state machines) |
| `wallexbot.sim` | Simulated exchange (paper trading) |
| `wallexbot.wallex` | Public Wallex data client (REST + WebSocket) |
| `wallexbot.engine` | Bot engine (wiring strategy ↔ exchange ↔ data) |
| `wallexbot.storage` | SQLite persistence and recovery |
| `wallexbot.analytics` | Backtesting, history, metrics |
| `wallexbot.api` | FastAPI backend for web UI |
| `wallexbot.ui` | Jinja2 + HTMX frontend |
| `wallexbot.cli` | Command-line interface |
| `wallexbot.intelligence` | Adaptive grid, optimizer, indicators |
| `wallexbot.alerts` | Telegram notifications |
| `wallexbot.strategies` | Plugin registry for strategies |

## Dependency Rules

- **Pure core, thin edges**: Domain imports nothing from other packages
- **Strategy** imports only from domain
- **Sim/Engine/Wallex** import from domain and strategy
- **API/UI/CLI** import from engine, storage, analytics
- **Intelligence** imports from analytics, strategy, domain

## Concurrency Model

- Single-writer state in the engine (asyncio)
- All state mutations go through the engine's event loop
- No shared mutable state across tasks
- Fake clock for deterministic testing