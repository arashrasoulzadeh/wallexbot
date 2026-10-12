# Audit of the existing code vs TODO.md

Date: 2026-10-12. Scope: read-only audit of the working tree (nothing was modified). Evidence was gathered by running the tools and small repro scripts, not just reading code.

## Verdict

The project is **a broad but unreliable first draft, not a finished Phases 1-17**. The full tree exists (about 7,200 lines of source, 6,100 lines of tests, 322 passing tests, 19 commits from 2026-10-10), but the most important piece, the grid fill logic, is wrong, the quality gates fail, and several plan items are missing. **Do not run it for anything beyond experiments until the P0 items below are fixed.**

## Progress log (2026-10-12)

| Item | Status |
|---|---|
| `HEAD` could not import | fixed (checkpoint commit) |
| P0 grid fill logic, client ids, profit, fee-adjusted quantity | fixed, 17 regression tests |
| Decision D1 (wait for the full fill) | implemented, 10 tests |
| P1 config (example, break-even, min notional) | fixed, 6 tests |
| `ruff check` | **clean** (was 391 errors); code formatted with `ruff format` |
| `mypy --strict src` | **clean** (was 267 errors) |
| Tests | 367 passing (was 322); empty placeholder tests removed |
| Simulator ledger (fees, settlement, fill price, double lock) | fixed, 12 tests incl. 300-step randomized conservation check |
| Backtester | **built**: trades, answers fills, ledger-consistent PnL, candle replay, `wallexbot backtest` CLI + Markdown report (24 tests) |
| Engine | **built**: async loop on live prices, grid built on the first real tick, fills answered, kill switch, risk halt, graceful stop, SQLite recording; `wallexbot paper`; live-tested on the public WebSocket (37 tests) |
| Web UI | **rebuilt** (old pages never rendered): real RunManager + endpoints + live stream, Configure/Backtest/Paper/Runs/Dashboard in English and Persian, localhost-only by default; verified in a real browser against live prices (47 tests) |
| Coverage | **80.1%**, gate is 90% (still failing) |

Real bugs found by the type check and fixed with regression tests: `HistoricalDataStore` crashed on `Symbol.value`; the optimizer
passed a wrong keyword and raw Decimals as balances (hidden by a bare `except`, so it silently returned nothing); its random-search
price sampling produced prices near 0.2; the REST client and WebSocket parser did not match the real Wallex API at all (invented
field names, paths and frame shapes, tested only against matching mocks) and are rewritten against recorded real responses
(`tests/fixtures/wallex/`); the WebSocket reconnect loop never ran.

### Still open (found, not fixed)

1. ~~Backtester is a stub~~ **fixed** (see docs/backtesting.md). Remaining: no volume/queue modelling, no market orders.
2. ~~Engine is unfinished~~ **fixed** (docs/paper-trading.md). Remaining: no crash recovery (a restart starts a fresh grid), no fill inference from polling (the simulator reports fills directly), WebSocket gaps are not resynced.
   The web UI is now wired to the engine (see the progress table).
3. **Simulator has no market orders**: MARKET and STOP_MARKET are now rejected with a clear error (they used to be accepted and never fill); the 2% price-move cancel rule (5.4.4) is still missing.
4. **History API is stubs** (the History and Settings pages are no longer linked or served as real pages): six `/api/history/*` endpoints return `[]`; the history tables from Phase 14 (ticks, trades, candles, balance and PnL snapshots, grid cycles) are not in the schema; `/api/stream` only echoes.
5. **WebSocket**: no gap resync after reconnect (6.4.5), no 50-messages-per-channel guard (6.4.6); `PriceFeed` for live WebSocket data is not wired to the engine.
6. **Coverage 80.1%** vs 90% gate; weakest: `analytics/history.py`, `analytics/api.py`, `engine/actions.py`, `strategy/grid/sizing.py`, `sim/rate_limiter.py`.
7. **Placeholder tests**: several remaining tests are `pass` or only check `hasattr` (`test_indicators.py::TestOptimizer`, `TestHistoricalDataStore`, parts of the engine/anomaly tests).
8. Real maker/taker fee and spot minimum order size are still unknown (D16, D17); `.env` key value should be rotated if real.

## Facts measured (original audit, before fixes)

| Check | Result |
|---|---|
| `pytest` (working tree) | 322 passed, about 8 s |
| `pytest` on committed `HEAD` | **Cannot even import**: `strategy/grid/risk_guards.py` imports `wallexbot.tests.helpers.clock` (does not exist). The 42 uncommitted modified files are what make the project work at all. |
| Coverage | **67.9%** total vs the project's own `fail_under = 90`. Weak: `analytics/history.py` 26%, `analytics/data_store.py` 36%, `engine/actions.py` 54%, `api/app.py` 69%, `analytics/api.py` 48%. |
| `ruff check` | **391 errors** (288 auto-fixable). |
| `mypy --strict` | **267 errors in 22 files** (for example `cli/main.py:381` accesses `completed_cycles` on a `dict`). |
| Float use in money paths | Only time/rate values and optimizer statistics; prices and quantities use `Decimal`. OK. |
| API-key safety | No `x-api-key` header anywhere in `src`; config loader rejects `api_key`/`secret`/`password` keys. OK. |
| Real network in tests | None found in `tests`. OK. |

## P0: wrong behavior that loses the grid's purpose

**Status 2026-10-12: items 1-4 below are FIXED** (regression tests in `tests/unit/strategy/grid/test_fill_ladder.py`, 17 tests; suite now 339 passing). Remaining related gap: decision D1 (wait for the full fill before the counter-order) is still NOT implemented; `on_fill` has no notion of partial vs full fills.

1. **Grid fill handling is broken** (`src/wallexbot/strategy/grid/fill_handling.py`, uncommitted "gap-based" rewrite).
   Repro: 9 levels 90..110, price 100, then the three nearest buy levels fill (price drops through them):
   - fill at level 3 -> `cancel sell@5` + `place sell@5` (replaces an existing sell instead of adding a sell next to the filled level, and shrinks its size to the fill quantity);
   - fill at level 2 -> **no actions**; fill at level 1 -> **no actions**.
   Result: coins are bought and never get a matching sell order, so the grid stalls holding inventory. This directly violates plan items 3.5 and 3.11 (jump over several levels). The rule must be "buy at level i -> sell at i+1; sell at level i -> buy at i-1", independent of a single global gap. The tests were rewritten together with the code (155 lines changed), so they no longer catch this.
2. **`client_id` collisions**: counter orders use `GRID_{level}_{side}_1` (constant suffix). Wallex rejects a repeated `client_id`, so the second cycle at any level would be rejected; the executor uses the action's id when present. Needs a per-run, per-sequence unique id (plan 7.3).
3. **`profit` is always 0** in `FillResult`; per-cycle realized profit (plan 3.8) is not computed here.
4. **Counter-order quantity is not fee-adjusted** (the code comment trails off with "wait..."). A sell for the full bought quantity can fail with insufficient balance if the fee is taken in the base asset (plan 3.5.3). Also `ValueError` is raised on a too-small counter order instead of handling it.

## P1: configuration does not match the decisions

**Status 2026-10-12: FIXED** (tests in `tests/unit/config/test_breakeven.py`): example config now targets USDTTMN with Toman prices, 2M TMN, placeholder fees/min-notional clearly marked; config validation rejects grids below the fee break-even (1.5x round-trip maker fee) or with per-level size below `min_notional`; "profit per cycle after fees" formula corrected. Still open: the `json` field-name warning in `LoggingConfig`.

- `config/grid.example.yaml` uses **lower 90 / upper 110** for USDTTMN, whose price is about 264,000 TMN. `min_notional` is `10.00` (should be around 90,000 TMN placeholder, D11/D17); fees `0.001/0.002` are placeholders with no source (D16).
- **Fee break-even check is not enforced in config validation** (plan 4.3 / D16). It exists only as advisory text in `intelligence/smart_grid.py`. A grid whose spacing is below twice the maker fee is accepted.
- Risk defaults in the example (`max_drawdown 0.05`, `daily_loss_limit 0.02`) match D12; capital 2,000,000 TMN matches D8.
- `LoggingConfig` has a field named `json` that shadows a pydantic attribute (runtime `UserWarning`).

## P1: plan items missing or only partly done

| Plan item | Status |
|---|---|
| 5.4.4 market-order "cancel if it moves price more than 2%" | not found in `sim/` |
| 6.4.4 WS reconnect before the 30-minute cutoff | reconnect/pong present; no 30-minute logic found |
| Phase 14 tables `price_ticks`, `market_trades`, `candles`, `depth_snapshots`, `balance_snapshots`, `pnl_snapshots`, `grid_cycles`, `config_versions` | **not in the schema**; storage has only `runs, orders, fills, grid_state, events` |
| 14.x history API/analytics | exist (`analytics/history.py`) but 26% covered |
| 13.11 i18n (English + Persian, RTL) | no `fa` catalog or `dir="rtl"` found in `ui/` |
| Gate A (ledger reconciles on 100 random paths) | one reconciliation test exists; not clearly a 100-path property test |
| README "paper only, no keys" statement | not verified |

Items that look genuinely present: pure grid level generation/sizing/placement, risk guards, simulated exchange with rate limiter and fault injection, public Wallex REST/WS clients with fakes, backtester, SQLite migrations/repository, CLI, FastAPI app with HTMX templates, Telegram notifier, strategy plugins, intelligence module, 15 decision records, docs set.

## P2: hygiene and security

- A `.env` file exists in the project root with a variable named `WALLEX_API_KEY_DONT_USE`. It is gitignored and untracked, and no code reads it. Its value was not read during this audit. **If it contains a real key, rotate it**; a plan rule is that no keys are used at all.
- Comments in code show unresolved reasoning (`fill_handling.py` "wait...").
- `tests` directory is imported as `wallexbot.tests...` in production code (the HEAD import bug); production code must not depend on test helpers. The `Clock` protocol belongs in `wallexbot.domain`.
- `requirements.lock` (plan 1.6a) not present; `pyproject.toml` uses `>=` ranges only.

## Recommended fix order

1. Commit the pending working-tree changes as-is so `HEAD` imports (safe checkpoint), then fix in small commits.
2. **Write the failing regression tests first**: multi-level jump fill, repeated-cycle `client_id` uniqueness, fee-adjusted counter quantity, cycle profit. Then fix `fill_handling.py` (P0 1-4).
3. Make `ruff` and `mypy --strict` pass (auto-fix first), raise coverage to the 90% gate.
4. Fix the example config and enforce the fee break-even and min-notional rules in config validation; keep fee/min-notional as clearly-marked placeholders until D16/D17 are answered.
5. Fill the missing Phase 14 tables and the 2% market-order rule, add the 30-minute WS rotation, add the Persian UI catalog.
6. Then update `TODO.md` checkboxes only for items verified by tests.
