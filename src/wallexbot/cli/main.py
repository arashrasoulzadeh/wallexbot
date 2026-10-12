"""Main CLI entry point."""

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from wallexbot.analytics.backtest import Backtester
from wallexbot.analytics.replay import candles_to_ticks
from wallexbot.analytics.report import (
    format_engine_status,
    format_status_line,
    format_summary,
    render_markdown,
)
from wallexbot.config.schema import load_config
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Symbol
from wallexbot.engine import BotEngine, EngineConfig, RiskMonitor
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.storage.repository import SQLiteRepository
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridMode, GridParameters
from wallexbot.wallex.client import WallexRestClient
from wallexbot.wallex.price_feed import PriceFeedReplay


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="wallexbot",
        description="Wallex Grid Trading Bot (paper trading only)",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # markets command
    subparsers.add_parser("markets", help="List spot markets")

    # config check command
    config_parser = subparsers.add_parser("config", help="Config commands")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    check_parser = config_subparsers.add_parser("check", help="Validate config file")
    check_parser.add_argument("file", help="Config YAML file")

    # fetch-candles command
    fetch_parser = subparsers.add_parser("fetch-candles", help="Download candles")
    fetch_parser.add_argument("symbol", help="Market symbol (e.g., USDTTMN)")
    fetch_parser.add_argument("--resolution", default="60", help="Candle resolution")
    fetch_parser.add_argument(
        "--from", dest="from_ts", required=True, help="Start timestamp or date"
    )
    fetch_parser.add_argument("--to", dest="to_ts", required=True, help="End timestamp or date")
    fetch_parser.add_argument("--output", help="Output CSV file")

    # backtest command
    backtest_parser = subparsers.add_parser("backtest", help="Run backtest")
    backtest_parser.add_argument("config", help="Config YAML file")
    backtest_parser.add_argument("--from", dest="from_ts", required=True, help="Start date")
    backtest_parser.add_argument("--to", dest="to_ts", required=True, help="End date")
    backtest_parser.add_argument("--output", help="Write a Markdown report to this file")
    backtest_parser.add_argument(
        "--resolution", default="60", help="Candle resolution: 1, 15, 60, 240, 1D (default 60)"
    )

    # paper command
    paper_parser = subparsers.add_parser("paper", help="Run paper trading on live prices")
    paper_parser.add_argument("config", help="Config YAML file")
    paper_parser.add_argument(
        "--feed", choices=["ws", "poll"], default="ws", help="Price source (default: ws)"
    )
    paper_parser.add_argument(
        "--duration", type=float, help="Stop after this many seconds (default: run until Ctrl+C)"
    )
    paper_parser.add_argument("--db", help="Record the run in this SQLite database")
    paper_parser.add_argument(
        "--status-every", type=float, default=30.0, help="Seconds between status lines"
    )

    # report command
    report_parser = subparsers.add_parser("report", help="Generate report for run")
    report_parser.add_argument("run_id", help="Run ID")

    # ui command
    ui_parser = subparsers.add_parser("ui", help="Start web dashboard")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    ui_parser.add_argument("--port", type=int, default=8080, help="Port to bind")

    # suggest command
    suggest_parser = subparsers.add_parser("suggest", help="Get intelligent grid suggestions")
    suggest_parser.add_argument("--market", default="USDTTMN", help="Market symbol")
    suggest_parser.add_argument("--capital", default="2000000", help="Capital in quote currency")

    # optimize command
    optimize_parser = subparsers.add_parser("optimize", help="Run parameter optimization")
    optimize_parser.add_argument("--market", default="USDTTMN", help="Market symbol")
    optimize_parser.add_argument("--from", dest="from_ts", required=True, help="Start date")
    optimize_parser.add_argument("--to", dest="to_ts", required=True, help="End date")
    optimize_parser.add_argument(
        "--iterations", type=int, default=50, help="Random search iterations"
    )

    # regime command
    regime_parser = subparsers.add_parser("regime", help="Check current market regime")
    regime_parser.add_argument("--market", default="USDTTMN", help="Market symbol")
    regime_parser.add_argument("--period", type=int, default=20, help="Lookback period")

    return parser


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configure structured logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    if json_format:
        import json

        class JSONFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_obj = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if hasattr(record, "run_id"):
                    log_obj["run_id"] = record.run_id
                return json.dumps(log_obj)

        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = [handler]


def main(args: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = create_parser()
    parsed = parser.parse_args(args)

    # Setup logging
    setup_logging()

    try:
        if parsed.command == "markets":
            return cmd_markets()
        elif parsed.command == "config":
            return cmd_config_check(parsed.file)
        elif parsed.command == "fetch-candles":
            return cmd_fetch_candles(
                parsed.symbol, parsed.resolution, parsed.from_ts, parsed.to_ts, parsed.output
            )
        elif parsed.command == "backtest":
            return cmd_backtest(
                parsed.config, parsed.from_ts, parsed.to_ts, parsed.output, parsed.resolution
            )
        elif parsed.command == "paper":
            return cmd_paper(
                parsed.config, parsed.feed, parsed.duration, parsed.db, parsed.status_every
            )
        elif parsed.command == "report":
            return cmd_report(parsed.run_id)
        elif parsed.command == "ui":
            return cmd_ui(parsed.host, parsed.port)
        elif parsed.command == "suggest":
            return cmd_suggest(parsed.market, parsed.capital)
        elif parsed.command == "optimize":
            return cmd_optimize(parsed.market, parsed.from_ts, parsed.to_ts, parsed.iterations)
        elif parsed.command == "regime":
            return cmd_regime(parsed.market, parsed.period)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        logging.exception("Command failed")
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_markets() -> int:
    """List spot markets."""
    client = WallexRestClient()
    markets = client.get_markets()

    print(f"{'Symbol':<12} {'Base':<8} {'Quote':<8} {'Price Prec':<10} {'Amt Prec':<10}")
    print("-" * 60)
    for m in markets:
        print(
            f"{m.symbol:<12} {m.base_asset:<8} {m.quote_asset:<8} {m.price_precision:<10} {m.amount_precision:<10}"
        )

    return 0


def cmd_config_check(config_file: str) -> int:
    """Validate config and show derived values."""
    try:
        config = load_config(config_file)
        print("✓ Config is valid")
        print()
        print("Derived values:")
        print(f"  Symbol: {config.market.symbol}")
        print(
            f"  Grid range: {config.strategy['grid'].lower_price} - {config.strategy['grid'].upper_price}"
        )
        print(f"  Grid count: {config.strategy['grid'].grid_count}")
        print(f"  Mode: {config.strategy['grid'].mode.value}")
        print(f"  Spacing: {config.strategy['grid'].spacing}")
        print(f"  Levels: {config.strategy['grid'].levels_count}")
        print(f"  Per-grid investment: {config.strategy['grid'].per_grid_investment}")
        print(
            f"  Min profit per cycle (after fees): {config.strategy['grid'].min_profit_per_cycle_after_fees}"
        )
        return 0
    except Exception as e:
        print(f"✗ Config validation failed: {e}")
        return 1


def cmd_fetch_candles(
    symbol: str, resolution: str, from_ts: str, to_ts: str, output: str | None
) -> int:
    """Download candles."""
    client = WallexRestClient()

    # Parse timestamps
    from_ts_int = int(from_ts) if from_ts.isdigit() else _parse_date(from_ts)
    to_ts_int = int(to_ts) if to_ts.isdigit() else _parse_date(to_ts)

    candles = client.get_candles(symbol, resolution, from_ts_int, to_ts_int)

    if output:
        import csv

        with open(output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for c in candles:
                writer.writerow([c.open_time, c.open, c.high, c.low, c.close, c.volume])
        print(f"Saved {len(candles)} candles to {output}")
    else:
        for c in candles:
            print(f"{c.open_time} O:{c.open} H:{c.high} L:{c.low} C:{c.close} V:{c.volume}")

    return 0


def _parse_date(date_str: str) -> int:
    """Parse date string to timestamp."""
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except ValueError:
        return int(date_str)


def make_rest_client() -> WallexRestClient:
    """Public Wallex client (a function so tests can swap in a fake)."""
    return WallexRestClient()


def make_price_feed(kind: str, symbol: Symbol, client: WallexRestClient) -> Any:
    """Live price feed for paper trading: public WebSocket trades ("ws") or REST polling ("poll")."""
    from wallexbot.wallex.live_feed import RestPollingFeed, WebSocketTradeFeed

    if kind == "poll":
        return RestPollingFeed(symbol, client)
    return WebSocketTradeFeed(symbol)


@dataclass
class _GridSetup:
    """A validated config turned into the objects a run needs."""

    symbol: str
    market: Market
    params: GridParameters
    fees: FeeSchedule
    min_rule: MinNotionalRule
    maker: Decimal
    taker: Decimal
    min_notional: Decimal
    risk: RiskMonitor
    initial_quote: Decimal
    initial_base: Decimal

    def new_exchange(self) -> SimulatedExchange:
        return SimulatedExchange(
            market=self.market,
            fee_schedule_config=self.fees,
            min_notional_rule=self.min_rule,
            initial_balances={
                self.market.quote: Balance(free=self.initial_quote, locked=Decimal(0)),
                self.market.base: Balance(free=self.initial_base, locked=Decimal(0)),
            },
        )

    def new_strategy(self) -> GridStrategy:
        return GridStrategy(
            self.market, self.params, fee_schedule=self.fees, min_notional_rule=self.min_rule
        )


def _load_grid_setup(config_file: str, client: WallexRestClient) -> _GridSetup | None:
    """Load the config and the market's real precisions; prints the problem and returns None."""
    try:
        config = load_config(config_file)
    except (ValueError, OSError) as exc:
        print(f"Error: invalid config: {exc}")
        return None

    symbol = str(config.market.symbol)
    info = next((m for m in client.get_markets() if str(m.symbol) == symbol), None)
    if info is None:
        print(f"Error: market {symbol} not found (is it a spot market?)")
        return None
    market = Market(
        symbol=Symbol(symbol),
        base=info.base_asset,
        quote=info.quote_asset,
        price_precision=info.price_precision,
        amount_precision=info.amount_precision,
        is_spot=info.is_spot,
    )

    grid = config.strategy["grid"]
    sim = config.simulation
    maker, taker = Decimal(sim.fee_maker), Decimal(sim.fee_taker)
    min_notional = Decimal(sim.min_notional)
    return _GridSetup(
        symbol=symbol,
        market=market,
        params=GridParameters(
            lower_price=Decimal(grid.lower_price),
            upper_price=Decimal(grid.upper_price),
            grid_count=grid.grid_count,
            mode=grid.mode,
            total_investment=Decimal(grid.total_investment),
        ),
        fees=FeeSchedule(maker_rate=maker, taker_rate=taker),
        min_rule=MinNotionalRule(min_notional=min_notional, min_quantity=Decimal(sim.min_quantity)),
        maker=maker,
        taker=taker,
        min_notional=min_notional,
        risk=RiskMonitor(
            max_drawdown=Decimal(config.risk.max_drawdown),
            daily_loss_limit=Decimal(config.risk.daily_loss_limit),
        ),
        initial_quote=Decimal(sim.initial_balance_quote),
        initial_base=Decimal(sim.initial_balance_base),
    )


def cmd_backtest(
    config_file: str,
    from_ts: str,
    to_ts: str,
    output: str | None,
    resolution: str = "60",
) -> int:
    """Backtest the configured grid on public candles (paper trading, no API key)."""
    try:
        start, end = _parse_date(from_ts), _parse_date(to_ts)
    except ValueError:
        print("Error: dates must be ISO dates (2024-01-31) or unix seconds")
        return 1
    if start >= end:
        print("Error: --from must be before --to")
        return 1

    client = make_rest_client()
    setup = _load_grid_setup(config_file, client)
    if setup is None:
        return 1

    print(f"Fetching {setup.symbol} candles ({resolution}) ...")
    candles = client.get_candles(setup.symbol, resolution, start, end)
    if not candles:
        print("Error: no candle data for that period")
        return 1

    backtester = Backtester(
        strategy=setup.new_strategy(),
        exchange=setup.new_exchange(),
        price_feed=PriceFeedReplay(candles_to_ticks(candles)),
    )
    try:
        result = backtester.run()
    except ValueError as exc:  # e.g. grid orders below the minimum size
        print(f"Error: {exc}")
        return 1

    print(format_summary(setup.symbol, result))
    if output:
        Path(output).write_text(
            render_markdown(
                setup.symbol,
                result,
                maker_fee=setup.maker,
                taker_fee=setup.taker,
                min_notional=setup.min_notional,
                candles=len(candles),
            ),
            encoding="utf-8",
        )
        print(f"Report written to {output}")
    return 0


async def _run_paper(engine: BotEngine, symbol: str, duration: float | None, every: float) -> None:
    """Run the engine, printing a status line periodically, until it ends or time is up."""
    task = engine.start()
    elapsed = 0.0
    try:
        while not task.done():
            wait = every if duration is None else min(every, max(duration - elapsed, 0.0))
            await asyncio.wait({task}, timeout=wait)
            elapsed += wait
            if not task.done():
                print(format_status_line(engine.status()))
            if duration is not None and elapsed >= duration:
                break
    finally:
        await engine.stop()
    if task.done() and not task.cancelled() and task.exception() is not None:
        raise task.exception()  # type: ignore[misc]


def cmd_paper(
    config_file: str,
    feed: str = "ws",
    duration: float | None = None,
    db: str | None = None,
    status_every: float = 30.0,
) -> int:
    """Paper-trade the configured grid on live public prices (no API key, no real orders)."""
    client = make_rest_client()
    setup = _load_grid_setup(config_file, client)
    if setup is None:
        return 1

    price_feed = make_price_feed(feed, setup.market.symbol, client)
    repository = SQLiteRepository(db) if db else None
    engine = BotEngine(
        EngineConfig(
            strategy=setup.new_strategy(),
            exchange=setup.new_exchange(),
            price_feed=price_feed,
            risk=setup.risk,
            repository=repository,
            run_name=f"paper-{setup.symbol}",
        )
    )

    print(f"Paper trading {setup.symbol} on live prices ({feed}). Press Ctrl+C to stop.")
    print("Paper only: orders exist inside the simulator, nothing is sent to Wallex.")
    try:
        asyncio.run(_run_paper(engine, setup.symbol, duration, status_every))
    except KeyboardInterrupt:
        print("\nInterrupted, stopping...")
    finally:
        closer = getattr(price_feed, "close", None)
        if closer is not None:
            asyncio.run(closer())

    print(format_engine_status(setup.symbol, engine.status()))
    return 0


def cmd_report(run_id: str) -> int:
    """Generate report for run."""
    from wallexbot.storage.repository import SQLiteRepository

    repo = SQLiteRepository("wallexbot.db")
    run = repo.get_run(run_id)

    if not run:
        print(f"Run {run_id} not found")
        return 1

    print(f"Run: {run['id']}")
    print(f"Status: {run['status']}")
    print(f"Started: {run['started_at']}")
    print(f"Stopped: {run['stopped_at']}")

    fills = repo.get_fills(run_id)
    print(f"\nFills: {len(fills)}")
    for f in fills[:10]:
        print(f"  {f['price']} x {f['quantity']} fee={f['fee']} {f['fee_asset']}")

    return 0


def cmd_ui(host: str, port: int) -> int:
    """Start web dashboard."""
    print(f"Starting web dashboard on {host}:{port}")
    print("Press Ctrl+C to stop")
    # This would start the FastAPI server
    import uvicorn

    from wallexbot.api.app import create_app
    from wallexbot.storage.repository import InMemoryRepository

    repo = InMemoryRepository()
    app = create_app(repo=repo)
    uvicorn.run(app, host=host, port=port)
    return 0


def cmd_suggest(market: str, capital: str) -> int:
    """Get intelligent grid suggestions."""
    from decimal import Decimal

    from wallexbot.intelligence.smart_grid import (
        should_run_grid,
        suggest_range,
        suggest_spacing,
    )
    from wallexbot.wallex.client import WallexRestClient

    print(f"Analyzing {market} with {capital} capital...")

    client = WallexRestClient()
    candles = client.get_candles(market, "60", 0, 0)  # Get recent candles

    if not candles:
        print("No candle data available")
        return 1

    capital_dec = Decimal(capital)

    # Get suggestions
    range_sugg = suggest_range(candles, capital_dec)
    spacing_sugg = suggest_spacing(candles, capital_dec, Decimal("0.001"))
    decision = should_run_grid(candles, capital_dec)

    print("\nRange Suggestion:")
    print(f"  Lower: {range_sugg.lower:.2f}")
    print(f"  Upper: {range_sugg.upper:.2f}")
    print(f"  Reasoning: {range_sugg.reasoning}")

    print("\nSpacing Suggestion:")
    print(f"  Spacing: {spacing_sugg.spacing:.4f}")
    print(f"  Grid Count: {spacing_sugg.grid_count}")
    print(f"  Min Profit/Grid: {spacing_sugg.min_profit_per_grid:.4f}")
    print(f"  Reasoning: {spacing_sugg.reasoning}")

    print("\nRun Decision:")
    print(f"  Should Run: {decision.should_run}")
    print(f"  Regime: {decision.regime}")
    print(f"  Reason: {decision.reason}")
    print(f"  Confidence: {decision.confidence:.0%}")

    return 0


def cmd_optimize(market: str, from_ts: str, to_ts: str, iterations: int) -> int:
    """Run parameter optimization."""
    from decimal import Decimal

    from wallexbot.intelligence.optimizer import random_search_optimizer
    from wallexbot.wallex.client import WallexRestClient

    print(f"Optimizing {market} from {from_ts} to {to_ts} ({iterations} iterations)...")

    client = WallexRestClient()

    # Parse timestamps
    from_ts_int = int(from_ts) if from_ts.isdigit() else _parse_date(from_ts)
    to_ts_int = int(to_ts) if to_ts.isdigit() else _parse_date(to_ts)

    candles = client.get_candles(market, "60", from_ts_int, to_ts_int)

    if not candles:
        print("No candle data available")
        return 1

    # Define parameter ranges
    param_ranges = {
        "lower_price": (Decimal("80.00"), Decimal("95.00")),
        "upper_price": (Decimal("105.00"), Decimal("120.00")),
        "grid_count": (10, 30),
        "mode": [GridMode.ARITHMETIC, GridMode.GEOMETRIC],
        "total_investment": (Decimal("1000000"), Decimal("5000000")),
    }

    base_config = {
        "lower_price": Decimal("90.00"),
        "upper_price": Decimal("110.00"),
        "grid_count": 20,
        "mode": GridMode.ARITHMETIC,
        "total_investment": Decimal("2000000"),
    }

    results = random_search_optimizer(
        param_ranges=param_ranges,
        candles=candles,
        base_config=base_config,
        n_iterations=iterations,
        objective="risk_adjusted_return",
    )

    print("\nTop 5 Results:")
    for i, r in enumerate(results[:5]):
        print(f"  {i + 1}. Score: {r.score:.4f}")
        print(f"     Range: {r.params.lower_price} - {r.params.upper_price}")
        print(f"     Grids: {r.params.grid_count} ({r.params.mode.value})")
        print(f"     Investment: {r.params.total_investment}")
        print(f"     Return: {r.metrics.total_return_pct:.2f}%")
        print(f"     Max DD: {r.metrics.max_drawdown:.2f}%")
        print(f"     Cycles: {r.metrics.completed_cycles}")

    return 0


def cmd_regime(market: str, period: int) -> int:
    """Check current market regime."""
    from wallexbot.intelligence.indicators import calculate_adx, calculate_atr, detect_regime
    from wallexbot.wallex.client import WallexRestClient

    print(f"Analyzing regime for {market} (period={period})...")

    client = WallexRestClient()
    candles = client.get_candles(market, "60", 0, 0)

    if not candles:
        print("No candle data available")
        return 1

    # Use recent candles
    recent = candles[-period:] if len(candles) >= period else candles

    regime = detect_regime(recent)
    atr = calculate_atr(recent)
    adx = calculate_adx(recent)

    print(f"\nMarket Regime: {regime.upper()}")
    print(f"ATR: {atr:.4f}")
    print(f"ADX: {adx:.2f}")

    if regime == "ranging":
        print("✓ Good for grid trading")
    elif regime == "volatile":
        print("⚠ Volatile - check spacing covers fees")
    else:
        print("✗ Trending - grid may accumulate losses")

    return 0


if __name__ == "__main__":
    sys.exit(main())
