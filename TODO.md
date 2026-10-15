# Wallex Grid Bot: TODO & Roadmap

Reference docs (offline): [docs/wallex-api.md](docs/wallex-api.md) (summary), [docs/offline/INDEX.md](docs/offline/INDEX.md) (full mirror + Swagger).

## Status (2026-10-15)

The checkboxes below were not ticked as work landed, so they understate the project. This block is the honest summary;
[docs/AUDIT.md](docs/AUDIT.md) has the dated log of bugs found and fixed. Everything is paper trading on public data.

| Area | State |
|---|---|
| Domain, strategy core, simulated exchange, config (Phases 2-5) | Built and tested; ledger, fees and ladder rule were rewritten after the audit. |
| Public Wallex client and feeds (6) | Built against recorded real responses; REST and WebSocket, reconnect, polling fallback. |
| Engine, backtester (7, 8) | Built; the backtester and the engine share one trading session. |
| Persistence and crash recovery (9) | Built (SQLite, checkpoints, replay of downtime, tested at 40 crash points and with a real SIGKILL). |
| CLI, reports (10) | Built: markets, config, fetch-candles, backtest, fees, paper (`--resume`), report, ui, suggest, optimize, regime. |
| History and analytics (14) | Built: equity and price charts with trade markers, daily results, trades, CSV, per-run summaries. |
| Web UI (13) | Built, English and Persian: dashboard, configure, backtest, paper, market status, all coins, history, runs, settings. |
| All Wallex coins | Every spot market, per-coin defaults assuming worst-case fees and the week's volatility. |
| Extras (15) | Telegram alerts (env-configured), Docker files, strategy registry. Docker is packaging only, never needed for dev. |
| Auto re-centering | Optional, paper and backtest, crash-safe; `wallexbot compare` judges it against a static grid and buy and hold. |
| Hardening (11) | Partial: fuzz/property tests and 40-point crash equivalence exist; a week of paper results has not been reviewed. |
| Intelligence (17) | Partial: indicators, suggest, optimizer, walk-forward and Monte Carlo exist behind CLI commands; adaptive decisions are not wired into the engine; no strategy comparison harness. |
| Documentation (16) | Mostly current: paper-trading, backtesting, runbook, CLI, config reference, API notes. |
| Live trading (12) | Not built and not planned without the user lifting the no-API-key rule. |

Open questions that only the user can answer: the real Wallex fee tier and minimum order (D16/D17), and whether live trading
is ever wanted. Coverage is above the 90 % gate.

## 0. Ground rules

- **No API keys, ever, in this roadmap.** All phases use only public endpoints (markets, depth, trades, candles, public WebSocket) plus a local simulated exchange. Real trading is a *separate future roadmap* (Phase 12 is a design stub only, nothing in it is built or enabled).
- **TDD is mandatory.** Every checkbox that adds behaviour follows red -> green -> refactor:
  1. write a failing test that names the behaviour,
  2. write the minimum code to pass,
  3. refactor with tests green,
  4. commit (one logical change per commit).
  No production code without a failing test first. Bug found = write the regression test first.
- **Develop and test LOCALLY, NOT in Docker.** **All development, running and testing happens directly on the local machine (venv). Docker is only a packaging/deployment option (Phase 15) and is never required for dev or tests.**
- **Tests never touch the network.** Network code is tested against recorded fixtures / fake transports. Only the explicit `-m live_public` marker may hit public endpoints, and it is off by default.
- **Money math uses `Decimal`, never `float`.** Prices/quantities are strings on the wire, `Decimal` in code.
- **Pure core, thin edges.** Strategy logic is pure functions/state machines with no I/O; clock, exchange, and storage are injected.
- Definition of done for any task: tests green, `ruff` + `mypy --strict` clean, coverage not decreased, **docs updated (Phase 16)**, config example updated.
- Offline Wallex docs live in [docs/offline/INDEX.md](docs/offline/INDEX.md) and the cheat-sheet in [docs/wallex-api.md](docs/wallex-api.md); each phase below lists the exact pages to read first. If a page conflicts with Swagger, trust Swagger and note it in the ADR/docs.

## Tech stack

| Layer | Choice | Why / notes |
|---|---|---|
| Language | Python 3.12+ | Decided. Typed everywhere (`mypy --strict`). |
| Packaging / env | `pyproject.toml`, `src` layout, local `venv` | Local dev only, **not Docker** (Docker is Phase 15 packaging). |
| Money math | `decimal.Decimal` (stdlib) | Never `float` for prices, quantities, fees. |
| Config | YAML + `pydantic` v2 (fallback: stdlib `dataclasses` + manual validation if D6 fails) | Unknown keys rejected; secrets rejected. |
| HTTP client | `httpx` (async) | Injectable transport for tests. Fallback: `urllib` in a thread. |
| WebSocket | `websockets` | Injectable connection for tests. |
| Async runtime | `asyncio` | Single-writer state in the engine. |
| Database | SQLite (stdlib `sqlite3`) + plain SQL migrations | Zero-setup, one file, backup = copy. |
| Web backend | FastAPI + Uvicorn (D7) | REST + SSE/WebSocket; OpenAPI snapshot test. |
| Web frontend | Jinja2 templates + HTMX, vendored chart lib (lightweight-charts) | No Node build; English + Persian (RTL) i18n. |
| Math / analytics | stdlib first; `numpy` only if profiling shows need (Phase 17) | Keeps install light; core stays pure Python. |
| Tests | `pytest`, `pytest-asyncio`, `pytest-cov`, `hypothesis`, `mutmut` | TDD mandatory; property tests for money and grid invariants. |
| Quality | `ruff` (lint + format), `mypy --strict`, `bandit`, `pip-audit` | One `make check`. |
| CLI | `argparse` (stdlib) or `typer` | Decide in Phase 10 based on D6. |
| Logging | stdlib `logging` with JSON formatter | Run id on every line; secret redaction filter. |
| Alerts | Telegram Bot API over `httpx` | Optional (Phase 15). |
| Packaging for deploy | Docker + compose | Phase 15, optional, never needed for dev/tests. |

Dependency policy: stdlib first; every third-party package needs a one-line justification in `docs/decisions/`. Pin versions in a lock file. Core packages (`domain`, `strategy`, `sim`) import **no** third-party code except `pydantic` models at the edges.

Module map (`src/wallexbot/`): `domain/` (types, money) -> `strategy/` (grid, plugins) -> `intelligence/` (indicators, regime, optimizer) -> `sim/` (paper exchange) -> `wallex/` (public data client) -> `engine/` -> `storage/` (SQLite, history) -> `analytics/` -> `api/` + `ui/` -> `cli.py`. Dependencies point inward only: `domain` imports nothing from the others.

---

## Roadmap details

Rough effort (one developer, TDD included; adjust after Phase 3 actuals):

| Milestone | Phases | Est. effort | Exit criteria |
|---|---|---|---|
| M1 Green skeleton | 1 | 0.5 day | `make check` green, smoke test passes |
| M2 Pure grid math | 2, 3 | 3-4 days | All grid scenario + property tests green; no I/O in core |
| M3 Paper exchange + engine | 4, 5, 7 | 4-5 days | Grid runs end-to-end on a scripted feed; balances match hand calculations |
| M4 Real data in | 6, 8 | 3-4 days | Backtest on real USDTTMN candles; WS client survives reconnect tests |
| M5 Usable tool | 9, 14, 10 | 4-5 days | Restart recovery works; history queryable; CLI paper run on live public prices |
| M5b Dashboard | 13 | 4-5 days | Configure, backtest, live paper dashboard, History page in EN/FA |
| M5c Extras | 15 | 2-3 days | Telegram alerts, Docker files, strategy plugin API |
| M5d Intelligence | 17 | 4-6 days | Adaptive range/spacing + optimizer beat the static grid in walk-forward backtests (or are documented as not helping) |
| M6 Trust | 11, 16 | 3-4 days + 7-day paper run | Fuzz/soak/failure suites green, docs complete, week of paper results reviewed |

Dependency graph (an arrow means "must finish first"):

```
1 -> 2 -> 3 -> 4 -> 5 -> 7 -> 8 -> 9 -> 14 -> 10 -> 13 -> 15 -> 17 -> 11
          \-> 6 (data client) -----^                        \-> 16 (docs, continuous)
```

Critical path: 1 -> 2 -> 3 -> 5 -> 7 -> 8. Phase 6 (public data) can run in parallel with 4 and 5 once Phase 2 types exist. Phase 16 (docs) runs continuously.

Go / no-go gates:
- [ ] Gate A (after M3): grid ledger reconciles to the last unit on 100 random paths. If not, stop and fix before any data work.
- [ ] Gate B (after M4): backtest results are stable across two runs (determinism) and sane versus buy-and-hold. If not, fix the fill model first.
- [ ] Gate C (after M5): 3 days of paper run without a crash or unexplained PnL. If not, hardening comes before the UI.
- [ ] Gate D (before any live-trading discussion): week of paper results reviewed with the user, and Phase 12 sign-off. Live trading stays out of scope until then.

---

## Roadmap at a glance

| Phase | Goal | Output |
|---|---|---|
| 1 | Project scaffold and TDD toolchain | Runnable empty package, CI-style local check script |
| 2 | Domain model | Typed `Market`, `Order`, `Fill`, `Balance`, money/rounding helpers |
| 3 | Grid strategy core (pure) | Deterministic grid math + state machine |
| 4 | Config system | Validated YAML config, sane limits |
| 5 | Simulated exchange (paper) | In-memory exchange with order matching, fees, balances |
| 6 | Public Wallex data client | Read-only REST + WebSocket client (no keys) |
| 7 | Bot engine | Event loop wiring strategy <-> exchange <-> data |
| 8 | Backtester | Replay candles/trades through engine, produce metrics |
| 9 | Persistence and recovery | SQLite state, crash-safe restart |
| 10 | CLI, logging, reports | `wallexbot` commands, structured logs, PnL report |
| 17 | Intelligence (after 15) | Regime detection, auto range/spacing, optimizer, walk-forward validation, anomaly guards |
| 16 | Documentation (alongside every phase, finished last) | README, architecture, config/CLI/UI guides, runbook, ADRs |
| 15 | Extras (after 13) | Telegram alerts, Docker packaging (not for dev), strategy plugins |
| 14 | History and analytics (built after Phase 9, feeds 10 and 13) | Time-series store of prices, trades, orders, PnL, balances; query, export, charts |
| 13 | Web UI (built after Phase 10, before 11) | Local dashboard: configure, backtest, paper-run, monitor |
| 11 | Hardening | Property/fuzz tests, soak test, failure injection |
| 12 | (Future, NOT built) live-trading design stub | Design doc + safety checklist only |

---

## Phase 1: Project scaffold and TDD toolchain

Docs: [docs/wallex-api.md](docs/wallex-api.md) section 1 (general), section 9 (bot notes).

- [ ] 1.1 Python version: floor **3.12+**, developed on the installed 3.14.7 (record in `pyproject.toml` `requires-python`)
- [ ] 1.2 `git init` check, `.gitignore` (venv, `__pycache__`, `.env`, `*.db`, `.coverage`, `reports/`, `data/`)
- [ ] 1.3 Create layout:
  - [ ] `src/wallexbot/` (package, `__init__.py`, `py.typed`)
  - [ ] `tests/unit/`, `tests/integration/`, `tests/fixtures/`
  - [ ] `config/` (example configs), `data/` (gitignored, recorded market data), `docs/`
- [ ] 1.4 `pyproject.toml` with project metadata, `src` layout, console script `wallexbot`
- [ ] 1.5 Dev dependencies pinned: `pytest`, `pytest-cov`, `pytest-asyncio`, `hypothesis`, `ruff`, `mypy`, `freezegun` (or own fake clock)
- [ ] 1.6 Runtime dependencies (keep minimal): `pydantic` (config validation), `PyYAML`, `httpx`, `websockets`
  - [x] 1.6a Package index reachability verified (D6); keep a `requirements.lock` so installs are reproducible
- [ ] 1.7 Virtualenv instructions in `README.md` (`python3 -m venv .venv`, install, run tests); `.venv` already created at the project root and must be gitignored
- [ ] 1.8 `pytest` config: strict markers, `-ra`, `--strict-config`, default deselect marker `live_public`
- [ ] 1.9 `ruff` config (lint + format), `mypy --strict` config
- [ ] 1.10 Coverage config: branch coverage, fail-under 90% (core packages 100% target)
- [ ] 1.11 `Makefile` (or `scripts/check.sh`) with targets: `test`, `lint`, `type`, `cov`, `check` (all of them)
- [ ] 1.12 Pre-commit hook running `check` (optional but wanted)
- [ ] 1.13 **First test (red -> green):** `tests/unit/test_smoke.py` asserts `wallexbot.__version__` exists
- [ ] 1.14 Fake clock utility `tests/helpers/clock.py` (injectable `Clock` protocol: `now()`, `sleep()`)
- [ ] 1.15 Commit: "chore: scaffold project with TDD toolchain"

## Phase 2: Domain model

Docs: [docs/wallex-api.md](docs/wallex-api.md) sections 4-6; offline: [markets](docs/offline/pages/basic-services-markets.md), [create order](docs/offline/pages/spot-create-order.md), [order types](docs/offline/pages/spot-types.md), [fees](docs/offline/pages/basic-services-account-fee.md); schemas in [spot Swagger](docs/offline/swagger/) (`definitions`).

Tests first for each item. Package: `wallexbot.domain`.

- [ ] 2.1 `Decimal` helpers (`money.py`)
  - [ ] 2.1.1 Test + impl `quantize_down(value, step_or_precision)` (round toward zero to precision)
  - [ ] 2.1.2 Test + impl `quantize_to_precision(value, digits)` used for `price_precision` / `amount_precision`
  - [ ] 2.1.3 Test: never returns float; rejects float input with clear error
  - [ ] 2.1.4 Test: parse wire strings (`"82494"`, `"0.00001136"`, `"255.7500000000000000"`)
- [ ] 2.2 `Symbol` / `Market` model (from `/hector/web/v1/markets`): `symbol, base, quote, price_precision, amount_precision, is_spot`
  - [ ] 2.2.1 Test: build from recorded markets fixture; skip non-spot
  - [ ] 2.2.2 Test: unknown/missing precision handled explicitly (error, not silent default)
- [ ] 2.3 Enums: `Side(BUY, SELL)`, `OrderType(LIMIT, MARKET, STOP_LIMIT, STOP_MARKET)`, `OrderStatus` (NEW, PARTIALLY_FILLED, FILLED/FINISHED, CANCELED, REJECTED; map unknown wire values to `UNKNOWN`, never crash)
- [ ] 2.4 `Order` dataclass (frozen) + transition helpers (immutable updates)
  - [ ] 2.4.1 Test: `client_id` validation regex `^[A-Za-z0-9_]+$`
  - [ ] 2.4.2 Test: remaining quantity, filled percent, is_active
- [ ] 2.5 `Fill` (price, qty, fee, fee_asset, is_maker, ts) and `Trade` (public tick)
- [ ] 2.6 `Balance` (`free`, `locked`) with invariants (never negative)
- [ ] 2.7 `OrderRequest` (what the strategy wants) separate from `Order` (what the exchange has)
- [ ] 2.8 Fee model: `FeeSchedule(maker_rate, taker_rate)`; test fee calc in quote and base asset
- [ ] 2.9 Min-notional/min-qty rule object (value configurable since Wallex does not publish it)
- [ ] 2.10 Property tests (hypothesis): quantize is idempotent, never increases magnitude, `quantize(x) <= x`

## Phase 3: Grid strategy core (pure logic, no I/O)

Docs: order semantics in [spot-types](docs/offline/pages/spot-types.md) (stop trigger rules, market-order 2% rule); rate limit in [spot-create-order](docs/offline/pages/spot-create-order.md) (20 req / 10 s); fees in [docs/wallex-api.md](docs/wallex-api.md) section 5.

Package: `wallexbot.strategy.grid`. Everything here is deterministic and takes data in, returns decisions out.

- [ ] 3.1 Define grid parameters model: `lower_price, upper_price, grid_count, mode (arithmetic|geometric), total_investment (quote), per_grid_qty (optional), stop_loss_price?, take_profit_price?`
- [ ] 3.2 Level generation
  - [ ] 3.2.1 Test arithmetic levels: equal spacing, endpoints included, count correct
  - [ ] 3.2.2 Test geometric levels: equal ratio spacing
  - [ ] 3.2.3 Test every level rounded to `price_precision`, strictly increasing, no duplicates after rounding (error if rounding collapses levels)
  - [ ] 3.2.4 Property test: N levels -> N-1 intervals, all within [lower, upper]
- [ ] 3.3 Order sizing
  - [ ] 3.3.1 Test equal-quote-per-grid sizing: qty = quote_per_grid / level price, rounded down to `amount_precision`
  - [ ] 3.3.2 Test equal-base-qty sizing
  - [ ] 3.3.3 Test: every order satisfies min-notional/min-qty, else config rejected with explicit message
- [ ] 3.4 Initial placement given current price
  - [ ] 3.4.1 Test: buy orders at all levels below price, sell orders at all levels above
  - [ ] 3.4.2 Test: level equal/very close to market price is skipped (no crossing orders)
  - [ ] 3.4.3 Test: base-asset inventory needed for initial sells is computed (and the "buy base at market first" option vs "sells only after buys" option)
- [ ] 3.5 Fill handling (core of grid): when buy at level *i* fills -> place sell at level *i+1*; when sell at *i* fills -> place buy at *i-1*
  - [ ] 3.5.1 Test single full fill both directions
  - [ ] 3.5.2 Test partial fill: place counter-order for filled quantity only (or wait for full fill; decide + test the chosen policy)
  - [ ] 3.5.3 Test counter-order quantity accounts for fees so base balance never goes negative
  - [ ] 3.5.4 Test top level sell fill / bottom level buy fill edge cases (no level beyond range)
  - [ ] 3.5.5 Test duplicate fill event (idempotent), out-of-order fill events
- [ ] 3.6 Grid state model: map `level_index -> {open order id | empty}`; invariant tests (at most one open order per level, exactly one "gap" level around current price)
- [ ] 3.7 Range exit handling
  - [ ] 3.7.1 Price above upper: policy (hold, stop, or re-center); test chosen default = pause + alert
  - [ ] 3.7.2 Price below lower: same
  - [ ] 3.7.3 Optional stop-loss / take-profit triggers (pure check against price)
- [ ] 3.8 Profit accounting: per-cycle (buy->sell) realized profit net of fees; test against hand-computed examples
- [ ] 3.9 Risk guards (pure checks returning allow/deny + reason)
  - [ ] 3.9.1 Max open orders
  - [ ] 3.9.2 Max exposure (quote and base)
  - [ ] 3.9.3 Max drawdown / daily loss limit -> trip kill switch
  - [ ] 3.9.4 Order-rate budget: <= 20 placements / 10 s (matches Wallex limit), token-bucket with fake clock
- [ ] 3.10 Strategy interface (`on_start`, `on_price`, `on_fill`, `on_cancel`, `on_stop`) returning a list of `Action`s (`Place`, `Cancel`, `Pause`, `Alert`)
- [ ] 3.11 Scenario tests (table-driven): up-trend through all levels, down-trend, sideways oscillation, gap/jump over several levels, whipsaw at one level
- [ ] 3.12 Property test: after any random price path + fills, invariants hold (no negative balances, order count bounded, levels consistent)

## Phase 4: Configuration

Docs: [markets](docs/offline/pages/basic-services-markets.md) (precision fields); write `docs/config-reference.md` (task 16.4).

- [ ] 4.1 Config schema (pydantic): `exchange`, `market`, `strategy.grid.*`, `risk.*`, `simulation.*`, `logging.*`
- [ ] 4.2 Example `config/grid.example.yaml` with comments on every field; defaults per decisions: market `USDTTMN`, paper capital 2,000,000 TMN, partial fills = wait for full, out-of-range = pause + alert, fill model = conservative, start inventory = simulated market buy
- [ ] 4.3 Tests: valid config loads; each invalid case gives a precise error message
  - [ ] lower >= upper
  - [ ] grid_count < 2 or absurdly large
  - [ ] investment <= 0, per-grid below min notional
  - [ ] unknown keys rejected (typo protection)
  - [ ] symbol not in recorded markets / not spot
  - [ ] profit-per-grid smaller than 2x fee (warn or reject; configurable)
- [ ] 4.4 Derived-values report: show spacing, per-level size, min profit per cycle after fees, capital required
- [ ] 4.5 Env/CLI overrides precedence (CLI > env > file) with tests
- [ ] 4.6 Hard rule test: config containing anything named `api_key`/`secret` is **rejected** in this version (no-keys guarantee)

## Phase 5: Simulated exchange (paper trading engine)

Docs: [create order](docs/offline/pages/spot-create-order.md), [cancel](docs/offline/pages/spot-cancel-order.md), [order detail](docs/offline/pages/spot-single-order-detail.md), [open orders](docs/offline/pages/spot-active-orders.md), [order types](docs/offline/pages/spot-types.md), private events in [socket-private-channel](docs/offline/pages/socket-private-channel.md); error body in spot Swagger `resources.ErrorResponse`.

Package: `wallexbot.sim`. Implements the same `Exchange` protocol the future live client would.

- [ ] 5.1 Define `Exchange` protocol: `place_order`, `cancel_order`, `get_order`, `open_orders`, `balances`, `fee_schedule`, `market_info`
- [ ] 5.2 In-memory ledger
  - [ ] 5.2.1 Test: initial balances; locking funds on order placement (BUY locks quote, SELL locks base)
  - [ ] 5.2.2 Test: insufficient funds -> rejection with reason
  - [ ] 5.2.3 Test: cancel releases locked funds
- [ ] 5.3 Order validation mirroring Wallex rules: precision, min notional, stop_Price only for STOP_*, unique `client_id`, enum values
- [ ] 5.4 Matching against a price/trade feed
  - [ ] 5.4.1 LIMIT BUY fills when a trade/price <= limit; LIMIT SELL when >= limit
  - [ ] 5.4.2 Conservative fill model option (needs trade *through* the price) vs optimistic (touch); tested, default conservative
  - [ ] 5.4.3 Partial fills driven by traded volume (optional model)
  - [ ] 5.4.4 MARKET orders walk a depth snapshot (or candle) with slippage; reproduce the "cancel if >2% move" rule
  - [ ] 5.4.5 STOP_LIMIT / STOP_MARKET trigger rules (both directions, per docs)
- [ ] 5.5 Fee application with maker/taker rates; fee asset deducted correctly
- [ ] 5.6 Order status transitions match what Wallex reports (NEW -> partial -> FINISHED / canceled)
- [ ] 5.7 Rate limiter that emulates 20 req / 10 s and raises like the real API (so the bot learns to respect it)
- [ ] 5.8 Fault injection hooks: latency, rejected order, dropped fill event, duplicate fill event (used in Phase 11)
- [ ] 5.9 Event stream out of the sim (`OrderUpdated`, `FillOccurred`, `BalanceUpdated`) mirroring Wallex private-event shapes
- [ ] 5.10 Determinism test: same feed + same seed -> identical results

## Phase 6: Public Wallex data client (read-only, no keys)

Docs: [markets](docs/offline/pages/basic-services-markets.md), [depth](docs/offline/pages/basic-services-depth.md), [latest trades](docs/offline/pages/basic-services-latest-trades.md), [candles](docs/offline/pages/basic-services-candles.md), WebSocket: [intro/limits](docs/offline/pages/socket-intro.md), [buyDepth](docs/offline/pages/socket-buy-depth.md), [sellDepth](docs/offline/pages/socket-sell-depth.md), [trade](docs/offline/pages/socket-trade.md), [all@price](docs/offline/pages/socket-all-price.md); [basic Swagger](docs/offline/swagger/).

Package: `wallexbot.wallex`. Auth code is **not written** in this phase.

- [ ] 6.1 Record fixtures from the offline docs / real public responses into `tests/fixtures/` (markets, depth, trades, candles, WS frames). Sanitize nothing needed (public data)
- [ ] 6.2 REST client on `httpx`, base URL `https://api.wallex.ir`, injectable transport so tests use a fake
  - [ ] 6.2.1 `get_markets()` -> `list[Market]` (test with fixture)
  - [ ] 6.2.2 `get_depth(symbol)` -> bids/asks (`result.bid`, `result.ask`)
  - [ ] 6.2.3 `get_latest_trades(symbol)`
  - [ ] 6.2.4 `get_candles(symbol, resolution, from, to)` -> parse parallel arrays `t,o,h,l,c,v`; handle `s != "ok"` / empty
  - [ ] 6.2.5 Response envelope handling: `success:false`, error body `{code,message,result}`, HTTP 4xx/5xx, malformed JSON
  - [ ] 6.2.6 Timeouts, bounded retries with backoff + jitter (fake clock), no retry on 4xx
  - [ ] 6.2.7 Client-side throttle so public polling never hammers the API
- [ ] 6.3 Candle history pager: fetch long ranges in chunks, dedupe, sort; tested with fake pages
- [ ] 6.4 WebSocket client (`wss://api.wallex.ir/ws`), injectable connection
  - [ ] 6.4.1 Subscribe frame builder: `["subscribe", {"channel": "USDTTMN@trade"}]`
  - [ ] 6.4.2 Parse `@trade`, `@buyDepth`, `@sellDepth`, `all@price` frames (fixtures)
  - [ ] 6.4.3 Heartbeat: answer server PING with PONG (respect max 100 PONGs)
  - [ ] 6.4.4 Auto-reconnect before the 30-minute cutoff; resubscribe; backoff on failures
  - [ ] 6.4.5 Gap handling after reconnect (resync by REST snapshot)
  - [ ] 6.4.6 Max 50 messages/channel respected
  - [ ] 6.4.7 Unknown/garbage frames logged and skipped, never crash
- [ ] 6.5 `PriceFeed` abstraction: one interface implemented by (a) live public WS, (b) historical replay (Phase 8), (c) scripted test feed
- [ ] 6.6 Opt-in `live_public` marker tests (manual only): markets endpoint shape still matches fixtures (detects API drift)
- [ ] 6.7 Nothing in this package imports/reads credentials; test asserts no `x-api-key` header is ever set

## Phase 7: Bot engine

Docs: [docs/wallex-api.md](docs/wallex-api.md) section 9 (idempotent `client_id`, rate budget); design doc to write: `docs/architecture.md` (task 16.2).

Package: `wallexbot.engine`.

- [ ] 7.1 Engine loop: `PriceFeed` -> strategy -> actions -> `Exchange`; async, single-writer state
- [ ] 7.2 Startup sequence (each tested with fakes):
  - [ ] load + validate config
  - [ ] fetch market info (precision) and fee schedule
  - [ ] check balances sufficient for grid
  - [ ] reconcile with any existing open orders (Phase 9)
  - [ ] place initial grid (respecting rate budget, batched)
- [ ] 7.3 Action executor: translates `Place/Cancel` to exchange calls with idempotent `client_id` generation (`GRID_<run>_<level>_<seq>`)
- [ ] 7.4 Timeout handling: place call times out -> look up by `client_id` before retrying (no duplicate orders); tested
- [ ] 7.5 Fill handling path: exchange event -> strategy `on_fill` -> actions
- [ ] 7.6 Polling fallback: if event stream is down, poll open orders and diff to infer fills
- [ ] 7.7 Kill switch: stop placing, cancel all open orders, mark run `halted` (manual + automatic via risk guards)
- [ ] 7.8 Graceful shutdown (SIGINT/SIGTERM): cancel orders or leave them, per config; flush state
- [ ] 7.9 Pause/resume when price leaves range
- [ ] 7.10 Metrics counters: orders placed/cancelled/filled, errors, latency
- [ ] 7.11 Integration tests: engine + sim exchange + scripted feed over table-driven price paths, asserting final balances and PnL by hand-calculation

## Phase 8: Backtester

Docs: [candles](docs/offline/pages/basic-services-candles.md) (resolutions `1,15,60,240,480,720,1D,2D,3D`, unix seconds); write `docs/backtesting.md` (task 16.6).

- [ ] 8.1 Historical data store: download candles via public client -> CSV/Parquet-free (plain CSV) in `data/`
- [ ] 8.2 Replay feed: candles -> synthetic intra-candle path (open, then high/low in pessimistic order, then close); tested
- [ ] 8.3 Optional trade-tick replay when tick data is recorded
- [ ] 8.4 Run engine + sim exchange over replay; deterministic
- [ ] 8.5 Metrics (each unit-tested against known series):
  - [ ] realized PnL, unrealized PnL, total return %
  - [ ] number of completed grid cycles, avg profit per cycle
  - [ ] max drawdown, fees paid, time in range
  - [ ] comparison vs buy-and-hold
- [ ] 8.6 Parameter sweep runner (grid_count, range, mode) with results table
- [ ] 8.7 Sanity scenarios: pure sideways must profit, strong trend must show known grid weakness; encoded as tests
- [ ] 8.8 Report output (Markdown + CSV) to `reports/`

## Phase 9: Persistence and recovery

Docs: design doc `docs/data-model.md` (task 16.3); order lookup by `client_id`: [order detail](docs/offline/pages/spot-single-order-detail.md).

- [ ] 9.1 SQLite schema: `runs`, `orders`, `fills`, `grid_state`, `events` (migrations as plain SQL files, versioned)
- [ ] 9.2 Repository layer behind an interface; in-memory fake for tests
- [ ] 9.3 Write-ahead rule: persist intent before calling the exchange, update after; tested
- [ ] 9.4 Restart recovery tests:
  - [ ] crash after placing, before saving -> reconcile finds order by `client_id`
  - [ ] crash mid-fill handling -> no double counter-order
  - [ ] orders filled while bot was down -> detected and processed in order
- [ ] 9.5 Idempotent event processing (fill dedupe key)
- [ ] 9.6 State export (JSON) for debugging

## Phase 10: CLI, logging, reports

Docs: write `docs/cli.md` (task 16.5) and `README.md`.

- [ ] 10.1 CLI (`argparse` or `typer`) commands:
  - [ ] `wallexbot markets` (list spot markets + precision)
  - [ ] `wallexbot config check <file>` (validate + derived-values report)
  - [ ] `wallexbot fetch-candles ...`
  - [ ] `wallexbot backtest <config> --from --to`
  - [ ] `wallexbot paper <config>` (live public prices, simulated orders)
  - [ ] `wallexbot report <run-id>`
- [ ] 10.2 CLI tests via in-process invocation with fake clients (no network)
- [ ] 10.3 Structured logging (JSON lines) with run id, level, event; redaction helper (future-proof for secrets)
- [ ] 10.4 Console status view (levels, open orders, PnL) refreshing in place
- [ ] 10.5 Alerts interface (stdout now; Telegram/webhook later), tested with fake sink
- [ ] 10.6 `README.md`: install, quickstart, config guide, safety statement ("no keys, paper only")

## Phase 15: Extras (Telegram alerts, Docker packaging, pluggable strategies)

Docs: external only: Telegram Bot API (https://core.telegram.org/bots/api); write `docs/strategies.md` for the plugin API (task 16.8) and `docs/docker.md`.

Build order: after Phase 13; none of this blocks the core bot. **Reminder: development and testing stay local, not in Docker.**

### 15.A Telegram alerts (outbound only, uses a bot token, which is NOT a Wallex key)
- [ ] 15.1 `Notifier` interface already exists (10.5); add `TelegramNotifier` with injected HTTP transport (tests use a fake, never the network)
- [ ] 15.2 Events: out-of-range, risk limit / kill switch, feed disconnected > N s, run halted, daily summary, completed-cycle digest (rate-limited, batched)
- [ ] 15.3 Token and chat id come from env vars only; never logged (redaction test); config rejects them in YAML files
- [ ] 15.4 Message templates in English and Persian; tests for formatting and Telegram rate limits/backoff
- [ ] 15.5 `wallexbot notify test` command; notification failures never crash the bot

### 15.B Docker setup (packaging only)
- [ ] 15.6 **Docker is NOT used for development or testing; all work and tests run locally in the venv.**
- [ ] 15.7 `Dockerfile` (slim Python, non-root user, no secrets baked in) and `docker-compose.yml` (bot + UI, volume for the SQLite `data/` dir, bind UI to localhost)
- [ ] 15.8 Health check using `/api/health`; documented run commands in README
- [ ] 15.9 Static lint of Docker files (e.g. hadolint if available); no test depends on Docker being installed

### 15.C Pluggable strategies
- [ ] 15.10 Formalize the strategy interface from 3.10 as a plugin protocol (`Strategy`: params model, `on_start/on_price/on_fill/on_stop`) with a registry (`name -> class`)
- [ ] 15.11 Contract test suite that any strategy must pass (no I/O, deterministic, respects risk guards, only emits valid actions)
- [ ] 15.12 Config selects strategy by name; UI configure page renders form fields from the strategy's params model
- [ ] 15.13 Refactor grid into the plugin API with all existing tests staying green
- [ ] 15.14 Backlog (each its own TDD mini-phase, not scheduled): DCA, trailing grid, trailing stop, rebalancing

## Phase 14: History and analytics (everything, by time)

Docs: candles/trades formats in [candles](docs/offline/pages/basic-services-candles.md) and [latest trades](docs/offline/pages/basic-services-latest-trades.md); write `docs/data-model.md` (task 16.3).

Build order: right after Phase 9 (shares its SQLite database and repository layer). Goal: every price the bot saw, every order/fill/event it produced, and every profit/loss number, queryable by time range, per run and across runs. Phases 8, 10 and 13 read from this.

### 14.A What gets recorded (all timestamps UTC, ms precision, `Decimal` as text)
- [ ] 14.1 `price_ticks`: market, ts, price (from `all@price` / trades), source (`live`, `replay`)
- [ ] 14.2 `market_trades`: public trades (market, ts, price, qty, is_buy) for markets we follow
- [ ] 14.3 `candles`: market, resolution, open_time, o/h/l/c/v (backfilled via public API; unique on market+resolution+open_time)
- [ ] 14.4 `depth_snapshots` (optional, sampled, top-N levels, off by default to save space)
- [ ] 14.5 `orders` and `order_events` (placed, partial, filled, canceled, rejected): full audit trail per order, per run
- [ ] 14.6 `fills`: ts, run, order, level index, price, qty, fee, fee asset, maker/taker
- [ ] 14.7 `grid_cycles`: buy fill + matching sell fill, realized profit net of fees, duration
- [ ] 14.8 `balance_snapshots`: ts, run, free/locked per asset (on every fill + periodic)
- [ ] 14.9 `pnl_snapshots`: ts, run, realized, unrealized, fees, equity (quote), inventory, price at the time
- [ ] 14.10 `run_events`: start/stop/pause/range-exit/risk-trip/kill-switch/errors/reconnects with reason text
- [ ] 14.11 `config_versions`: exact config used per run (hash + JSON), so any result is reproducible
- [ ] 14.12 Mode column everywhere: `paper | backtest` (and nothing else in this version)

### 14.B Storage (tests first, in-memory SQLite in tests)
- [ ] 14.13 Schema migrations (versioned SQL), indexes on `(market, ts)`, `(run_id, ts)`; test migrate from empty and from each prior version
- [ ] 14.14 Idempotent inserts (dedupe keys) so replays/reconnects never double-count; tested
- [ ] 14.15 Batch/async writer so recording never slows the trading loop; test back-pressure and flush on shutdown/crash
- [ ] 14.16 Tick downsampling policy: keep raw ticks N days, then roll up to 1s/1m bars; retention config + test (never delete fills/orders/pnl)
- [ ] 14.17 Backfill job: fill missing candle gaps for a market and range; gap detection tested
- [ ] 14.18 DB size guard and `wallexbot db stats|vacuum|backup`
- [ ] 14.19 Time handling tests: DST-free (UTC only), Tehran-time display conversion at the edge only

### 14.C Queries and analytics (pure functions over rows; table-driven tests with hand-calculated expected values)
- [ ] 14.20 Query layer: by run, market, side, time range, with pagination and stable ordering
- [ ] 14.21 PnL time series: realized/unrealized/equity at arbitrary resolution (1m, 1h, 1d, 1w, all)
- [ ] 14.22 Profit/loss breakdowns: per day, per week, per month; per grid level; per cycle; wins vs losses
- [ ] 14.23 Fees paid over time; maker vs taker split
- [ ] 14.24 Drawdown series, max drawdown, time underwater
- [ ] 14.25 Trade stats: count, avg size, avg holding time per cycle, fill rate, time in range, out-of-range episodes
- [ ] 14.26 Compare runs side by side (same period, different configs) and vs buy-and-hold
- [ ] 14.27 Reconciliation test: sum of fills and fees reproduces final balance change exactly (ledger integrity check)
- [ ] 14.28 "What happened at time T": reconstruct grid state (open orders, balances, price) at any past timestamp from events; tested by replaying event logs

### 14.D Export and tools
- [ ] 14.29 Export to CSV/JSON for any table and range (`wallexbot export ...`); round-trip test
- [ ] 14.30 Daily summary report (Markdown) generated automatically per run
- [ ] 14.31 CLI: `wallexbot history prices|trades|orders|fills|pnl --market --from --to --run`

### 14.E History in the UI (lands in Phase 13 pages; backend endpoints first, tests first)
- [ ] 14.32 API: `GET /api/history/prices|trades|candles|orders|fills|cycles|balances|pnl|events` with `from/to/resolution/run/market/limit/cursor`
- [ ] 14.33 History page: global time-range picker (1h, 1d, 7d, 30d, custom) + zoom-able chart synced across panels
- [ ] 14.34 Price chart with buy/sell fill markers and grid levels overlaid for the selected run
- [ ] 14.35 PnL charts: equity curve, realized vs unrealized, drawdown, daily/weekly/monthly profit bars (green/red)
- [ ] 14.36 Tables: trades, orders, cycles, events log with filters, sort, search, and CSV download
- [ ] 14.37 Time-travel slider: scrub to time T and see the grid ladder and balances as they were (uses 14.28)
- [ ] 14.38 Run comparison view (14.26)
- [ ] 14.39 Component tests for chart data mappers and time-range handling; E2E: finish a backtest -> open History -> see matching totals

## Phase 13: Web UI (local dashboard)

Docs: write `docs/ui-guide.md` (task 16.7); API reference generated from the FastAPI OpenAPI schema.

Build order: after Phase 10, before Phase 11. The UI is a thin layer over the same engine/CLI services; it contains **no trading logic**. Runs on `127.0.0.1` only, no auth needed because there are no keys and no real orders.

Stack (decided, D7): backend **FastAPI** (REST + SSE/WebSocket) in `wallexbot.api`; frontend **server-rendered Jinja2 templates + HTMX** in `src/wallexbot/ui/` with a vendored charting lib (e.g. lightweight-charts) under `static/`. No Node build step. Bilingual **English + Persian (RTL)** per D9. One command starts everything.

### 13.A Backend API (TDD with FastAPI `TestClient`, fakes for engine/exchange)
- [ ] 13.1 App factory `create_app(deps)` with injected engine manager, repo, clock (tests never start a real bot)
- [ ] 13.2 Bind guard: refuse to start on non-loopback host unless `--allow-remote` is passed; test it
- [ ] 13.3 Read endpoints (each: failing test first, then impl):
  - [ ] `GET /api/health`
  - [ ] `GET /api/markets` (spot markets + precision, cached)
  - [ ] `GET /api/candles?symbol&resolution&from&to`
  - [ ] `GET /api/runs`, `GET /api/runs/{id}` (config, state, status)
  - [ ] `GET /api/runs/{id}/orders`, `/fills`, `/pnl`, `/grid` (levels + which have open orders)
- [ ] 13.4 Config endpoints:
  - [ ] `POST /api/config/validate` returns the same errors + derived-values report as the CLI (spacing, per-level size, profit after fees, capital needed)
  - [ ] saving/loading named config presets
- [ ] 13.5 Run control endpoints:
  - [ ] `POST /api/backtests` (start, returns id), `GET /api/backtests/{id}` (progress/result)
  - [ ] `POST /api/paper-runs` (start), `POST /api/runs/{id}/pause|resume|stop`
  - [ ] kill switch `POST /api/runs/{id}/kill`
  - [ ] only one active paper run per market (409 otherwise); tested
  - [ ] runs execute in background tasks; API never blocks
- [ ] 13.6 Live updates: `WS /api/stream` (or SSE) pushing price, order, fill, PnL, status events; test reconnect and `last_event_id` resume
- [ ] 13.7 Errors: uniform JSON error body, input validation (422) matches config validator messages
- [ ] 13.8 Hard rule tests: no endpoint accepts or stores API keys/secrets; `/api` exposes mode `paper|backtest` only, with no `live`
- [ ] 13.9 OpenAPI schema snapshot test (detects accidental API changes)

### 13.B Frontend (component tests with Vitest/Playwright-free DOM tests; E2E with a fake backend)
- [ ] 13.10 Scaffold `src/wallexbot/ui/` (templates, static, i18n); test runner = pytest (HTML assertions on rendered fragments) + a few browser-free HTMX endpoint tests
- [ ] 13.11 i18n layer: message catalogs `en.json`/`fa.json`, language switch persisted in a cookie, RTL via `dir="rtl"`, test that every key exists in both catalogs and no template has hardcoded text
- [ ] 13.12 Layout: sidebar (Dashboard, Configure, Backtest, Runs, Settings), responsive, dark/light theme
- [ ] 13.13 **Configure grid page**
  - [ ] market picker (search spot markets), shows price and precision
  - [ ] fields: lower, upper, grid count, arithmetic/geometric, investment, risk limits
  - [ ] live validation + derived-values panel (calls validate endpoint, debounced)
  - [ ] **price chart with the grid levels drawn over it** (buy levels vs sell levels in different colors)
  - [ ] warnings: profit per grid below fees, range far from current price
  - [ ] save/load presets
- [ ] 13.14 **Backtest page**: choose config + date range + candle resolution, run, progress bar, results (equity curve, drawdown, cycles, fees, vs buy-and-hold), export CSV/MD
- [ ] 13.15 Parameter sweep view: table/heatmap of results across grid count and range
- [ ] 13.16 **Paper-run dashboard** (live)
  - [ ] status badge (running/paused/halted/out-of-range) and big PAPER-MODE banner always visible
  - [ ] live price chart + grid ladder (open order per level, filled levels highlighted)
  - [ ] balances, realized/unrealized PnL, cycles completed, fees paid
  - [ ] open orders table and recent fills table
  - [ ] controls: pause, resume, stop, kill switch (with confirm dialog)
  - [ ] connection indicator, auto-reconnect, stale-data warning when feed is old
- [ ] 13.17 Runs history page: list, open any past run's report
- [ ] 13.18 Alerts/toasts for: out-of-range, risk limit hit, feed disconnected, run halted
- [ ] 13.19 Accessibility (keyboard nav, contrast, labels) and number formatting (Decimal-safe, no float rounding on display; Toman/USDT formatting; Persian digits toggle; Jalali date display option with UTC underneath), all tested
- [ ] 13.20 Empty/error/loading states for every page
- [ ] 13.21 Component tests for: derived-values panel, grid-level overlay math, order table, PnL formatting
- [ ] 13.22 E2E smoke test: start backend with fake feed -> configure -> start paper run -> see fills appear -> stop

### 13.C Packaging
- [ ] 13.23 `wallexbot ui` command: starts API + serves built UI, opens browser, prints URL
- [ ] 13.24 Templates and static files shipped inside the Python package (package-data test)
- [ ] 13.25 README section with screenshots and the "paper only, no keys" statement

## Phase 11: Hardening

Docs: failure modes and limits from [socket-intro](docs/offline/pages/socket-intro.md) and [spot-create-order](docs/offline/pages/spot-create-order.md); write `docs/runbook.md` (task 16.9).

- [ ] 11.1 Property/fuzz tests on strategy + sim (random paths, random fill orders, random partials)
- [ ] 11.2 Failure injection suite: API timeouts, 5xx bursts, rate-limit errors, WS drops, duplicate/out-of-order events, corrupted frames
- [ ] 11.3 Soak test: 24h of recorded ticks replayed fast; no memory growth, no leaked tasks
- [ ] 11.4 Concurrency review: single-writer state, no shared mutation across tasks
- [ ] 11.5 Mutation testing pass on `strategy` and `sim` (e.g. `mutmut`), fix surviving mutants with new tests
- [ ] 11.6 Static checks in CI-style script: ruff, mypy strict, bandit, dependency audit
- [ ] 11.7 Paper-trade live public prices for >= 7 days; compare sim PnL to backtest expectations; record findings
- [ ] 11.8 Review fees/min-order assumptions against what Wallex actually enforces (learned from public data and support answers, still no keys)

## Phase 17: Intelligence (adaptive and data-driven decisions, paper/backtest only)

Build order: after Phase 15 (needs the plugin API, history store and backtester). **Principle: intelligence only suggests or adapts parameters inside hard risk limits; the Phase 3.9 risk guards always have the final say. Everything is deterministic and backtestable. No black-box model trades by itself.** Docs: [candles](docs/offline/pages/basic-services-candles.md) for the data; write `docs/intelligence.md`.

### 17.A Market analysis (pure functions over candles; hand-checked expected values)
- [ ] 17.1 Volatility measures: ATR, standard deviation of returns, realized volatility per hour/day
- [ ] 17.2 Trend vs range detection: ADX or linear-regression slope + range-bound score; labels `ranging | trending_up | trending_down | volatile`
- [ ] 17.3 Support/resistance and recent high/low bands (Donchian), percentile of current price within range
- [ ] 17.4 Liquidity/spread check from depth snapshots: skip markets where the spread or thin book makes the grid unprofitable
- [ ] 17.5 Indicator unit tests against known series; property tests (no NaN, bounded outputs)

### 17.B Smart grid setup
- [ ] 17.6 **Auto range suggestion**: choose lower/upper from volatility bands (e.g. mean +- k*ATR) so the grid covers the expected range; tested on recorded sideways vs trending data
- [ ] 17.7 **Auto spacing**: choose level count so spacing >= minimum profitable step (>= 2x round-trip fee + safety margin) and orders meet min notional with the available capital
- [ ] 17.8 **Capital allocator**: split 2M TMN across levels (equal, or weighted toward levels near price); verify never exceeds balance
- [ ] 17.9 "Should I run a grid now?" score: regime = ranging and volatility in the profitable band, otherwise suggest waiting; explains the reasoning in plain text (EN/FA)
- [ ] 17.10 Suggestions are advisory by default (UI shows "apply suggestion"); auto-apply is an explicit opt-in config flag

### 17.C Adaptive behavior while running (opt-in, bounded)
- [ ] 17.11 Re-center / shift-grid policy as a plugin variant: only when out of range for N minutes and drawdown within limits; every shift logged as a run event
- [ ] 17.12 Dynamic spacing: widen when volatility spikes, narrow when calm; rate-limited changes (max one rebuild per T minutes) to respect the 20 orders / 10 s budget
- [ ] 17.13 Trend guard: when a strong trend is detected, pause new buys (avoid catching a falling knife) and alert
- [ ] 17.14 Anomaly guard: halt on price jump beyond X sigma, stale feed, crossed/empty depth, or abnormal fill rate; tested with injected anomalies
- [ ] 17.15 Cooldown after a stop-loss or kill switch before the bot may restart itself

### 17.D Optimization and validation
- [ ] 17.16 Parameter optimizer: grid search (then random search) over range, count, mode using the backtester; objective = risk-adjusted return (e.g. return / max drawdown), penalizing fee drag
- [ ] 17.17 **Walk-forward validation**: optimize on window N, test on window N+1, roll forward; report out-of-sample vs in-sample gap (overfitting detector)
- [ ] 17.18 Monte Carlo robustness: shuffle/bootstrap return paths, report distribution of PnL and probability of hitting the drawdown limit
- [ ] 17.19 Strategy comparison harness: static grid vs adaptive grid vs buy-and-hold on the same data; results saved to history (Phase 14) and shown in the UI comparison view
- [ ] 17.20 Honest-result rule: if the intelligence features do not beat the static grid out-of-sample, document that in `docs/intelligence.md` and leave them off by default

### 17.E Optional later: ML / LLM helpers (not scheduled, separate approval)
- [ ] 17.21 Feature store from history (volatility, regime, order-book imbalance, time of day) as a dataset export
- [ ] 17.22 Simple, explainable models first (logistic regression / gradient boosting) predicting "range-bound next N hours"; must beat the rule-based regime detector in walk-forward tests to be kept
- [ ] 17.23 Read-only LLM "analyst": summarizes a run's history and anomalies in EN/FA for the daily report; never places orders and never receives secrets

### 17.F UI and CLI for intelligence
- [ ] 17.24 Configure page: "Suggest settings" button, regime badge, explanation panel, apply/dismiss
- [ ] 17.25 Optimizer page: run a sweep, heatmap of results, walk-forward chart, Monte Carlo histogram
- [ ] 17.26 CLI: `wallexbot suggest`, `wallexbot optimize`, `wallexbot regime --market USDTTMN`

## Phase 16: Documentation (written alongside code, finished last)

Rule: a feature is not done until its doc is updated (part of the Definition of done). Keep docs in `docs/`, link them from `README.md`.

- [ ] 16.1 `README.md`: purpose, "paper only, no keys" statement, install (local venv, not Docker), quickstart, links to all docs
- [ ] 16.2 `docs/architecture.md`: layers, data flow diagram (feed -> strategy -> actions -> exchange -> events -> history), module map, dependency rules (pure core, thin edges)
- [ ] 16.3 `docs/data-model.md`: every SQLite table/column, keys, indexes, retention, migration process
- [ ] 16.4 `docs/config-reference.md`: every config field, type, default, valid range, example; generated from the pydantic schema with a test that docs and schema stay in sync
- [ ] 16.5 `docs/cli.md`: every command, flags, examples, exit codes
- [ ] 16.6 `docs/backtesting.md`: fill model assumptions (conservative vs touch), intra-candle path, known limits, how to read the metrics
- [ ] 16.7 `docs/ui-guide.md`: each page, screenshots, English/Persian, how to read the grid ladder and PnL charts
- [ ] 16.17 `docs/intelligence.md`: indicators used, how suggestions are computed, validation results, honest limits
- [ ] 16.8 `docs/strategies.md`: grid explained (math, examples, fees, when it loses), plugin API for new strategies
- [ ] 16.9 `docs/runbook.md`: start/stop, crash recovery, kill switch, reading logs, common errors and fixes, backup/restore the DB
- [ ] 16.10 `docs/decisions/` ADRs: one short file per decision D1-D15 (context, choice, consequences)
- [ ] 16.11 `docs/glossary.md`: grid terms (level, cycle, spread, inventory, maker/taker), English + Persian
- [ ] 16.12 `docs/wallex-api.md` kept as the API cheat-sheet; add "last verified" date and a script check (`docs/offline/scrape.py`) to refresh the offline mirror and diff for API changes
- [ ] 16.13 `CHANGELOG.md` (Keep a Changelog format), updated per milestone
- [ ] 16.14 Docstrings on public functions (what/why, units, Decimal rules); `ruff` pydocstyle rules for the core packages
- [ ] 16.15 Doc link checker test (no broken relative links, every doc listed in README)
- [ ] 16.16 Doc review pass at each milestone M1-M6: walk through README quickstart on a clean checkout

## Phase 12: Future, NOT built (design stub only)

Docs: [create-api-key](docs/offline/pages/create-api-key.md) (permissions, IP whitelist, expiry), [docs/wallex-api.md](docs/wallex-api.md) section 2.

Only after Phases 1-11 are done and the user explicitly approves a separate plan.

- [ ] 12.1 Write `docs/live-trading-design.md`: authenticated client (`x-api-key`), key storage (OS keychain/env, never in repo), trade-only permission, IP whitelist, no withdraw permission
- [ ] 12.2 Live safety checklist: tiny-capital canary, max loss cap, kill switch, reconciliation on every start, alerts
- [ ] 12.3 Decide private-event strategy (stream key vs polling `openOrders`)
- [ ] 12.4 Explicit user sign-off required before any code in this phase

---

## Suggested order of work (milestones)

Note: phase numbers are IDs, not build order; the build order is the milestone list below and the dependency graph above.

1. **M1: Green skeleton**: Phase 1 complete, `make check` passes with the smoke test.
2. **M2: Pure grid math**: Phases 2-3 complete, all strategy tests green (no I/O anywhere).
3. **M3: Paper exchange + engine**: Phases 4, 5, 7 complete: the grid runs end-to-end on a scripted feed.
4. **M4: Real data in**: Phase 6 (public client, fixtures) + Phase 8 (backtest on real candles).
5. **M5: Usable tool**: Phases 9, 14, 10: persistence, full history store and analytics, CLI, reports; paper-trade on live public prices.
6. **M5b: Dashboard**: Phase 13 web UI (API first, then configure/backtest/live pages).
7. **M5c: Extras**: Phase 15 (Telegram, Docker packaging, plugin API).
8. **M5d: Intelligence**: Phase 17 (adaptive grid, optimizer, walk-forward validation).
9. **M6: Trust**: Phase 11 hardening and a week of paper results.

## Decisions

Resolved (2026-10-10):
- [x] D1 Partial fills: **wait for full fill**, then place the counter-order.
- [x] D2 Starting inventory: **simulated market buy** of the base needed for the sell levels at start.
- [x] D3 Out of range: **pause and alert**.
- [x] D4 Fill model: **conservative** (trade-through); touch model available as a config option for comparison.
- [x] D5 First market: **USDTTMN** (quote: TMN).
- [x] D7 UI stack: **FastAPI + HTMX** (server-rendered, no Node build); charting library vendored as a static file (no CDN at runtime).
- [x] D8 Default paper capital: **2,000,000 TMN** (configurable).
- [x] D9 UI language: **English + Persian (fa) with RTL layout** and optional Persian digits; language switch in the UI.
- [x] D12 Risk profile default: **conservative**: max drawdown 5%, daily loss limit 2%, wider spacing, fewer grids (all configurable; encoded as the default config and in risk-guard tests).
- [x] D13 Retention: **90 days of 1m candles**, raw ticks 14 days then rolled up; fills/orders/PnL/events kept forever (Phase 14.16).
- [x] D14 Runtime: **this Mac, on demand** (no 24/7 uptime, launchd, or keep-awake work scheduled; crash recovery from Phase 9 still required).
- [x] D15 Time display: **Asia/Tehran, Gregorian dates**; UTC stored everywhere; Jalali is a UI toggle.
- [x] D10 Extras to include: Telegram alerts, Docker setup (packaging only), pluggable strategies.

- [x] D6 Dependencies: **package install works** (checked 2026-10-12: `pytest`, `httpx`, `websockets`, `pyyaml`, `fastapi` installed into a project `.venv`; `pydantic` 2.x already on the system Python). Use the full stack from the Tech stack table; no stdlib-only fallback needed. Local Python is **3.14.7** (project floor stays 3.12+; test on the installed version). Node is NOT needed (HTMX decision).
- [x] D11 USDTTMN facts from public `GET /hector/web/v1/markets` and `/v1/depth` (2026-10-12):
  - `price_precision = 0` (prices are whole Toman), `amount_precision = 2` (USDT to 2 decimals), price about 264,000 TMN.
  - 24h high/low 265,871 / 263,190 = about **1.0% daily range**; top-of-book spread 59 TMN = **0.022%**; order book is deep (thousands of USDT near the top).
  - **Spot minimum order size is NOT published** anywhere in the docs or market data (only OTC `otc_min_notional = 90,000 TMN`). Plan: use 90,000 TMN as a conservative placeholder minimum, make it configurable, and confirm with Wallex support (api@wallex.ir / @wallexapi).
  - 2M TMN is about 7.5 USDT: 10 levels at about 200,000 TMN each is above the placeholder minimum, so a small grid is feasible.
  - **Key risk found:** a grid level spacing of about 0.1% only profits if round-trip fees are below that. The Wallex fee rate is only visible via the authenticated `/v1/account/fee` endpoint, so it is unknown without a key. Until known, the sim treats fees as a config value and the config validator (4.3) must refuse grids whose spacing is under 2x the maker fee plus margin.

Still open:
- [ ] D16 (Phase 4): actual Wallex maker/taker fee for USDTTMN. (`wallexbot fees` now backtests a grid across a fee range and prints the break-even; the true tier is still unknown.) Without API keys, find it from Wallex's public fee-schedule page or support; until then run backtests across a fee range (for example 0.05% to 0.35%) and report break-even spacing.
- [ ] D17 (Phase 3/5): real spot minimum order size/notional; confirm with Wallex support, keep 90,000 TMN placeholder meanwhile.
