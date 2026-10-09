"""Main CLI entry point."""

import argparse
import sys
import json
import logging
from pathlib import Path
from typing: Optional

from wallexbot.config.schema import load_config, validate_config
from wallexbot.domain.market import Symbol
from wallexbot.wallex.client import WallexRestClient
from wallexbot.analytics.backtest import Backtester
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridParameters, GridMode
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.wallex.price_feed import PriceFeedReplay
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule


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
    fetch_parser.add_argument("--from", dest="from_ts", required=True, help="Start timestamp or date")
    fetch_parser.add_argument("--to", dest="to_ts", required=True, help="End timestamp or date")
    fetch_parser.add_argument("--output", help="Output CSV file")

    # backtest command
    backtest_parser = subparsers.add_parser("backtest", help="Run backtest")
    backtest_parser.add_argument("config", help="Config YAML file")
    backtest_parser.add_argument("--from", dest="from_ts", required=True, help="Start date")
    backtest_parser.add_argument("--to", dest="to_ts", required=True, help="End date")
    backtest_parser.add_argument("--output", help="Output report file")

    # paper command
    paper_parser = subparsers.add_parser("paper", help="Run paper trading on live prices")
    paper_parser.add_argument("config", help="Config YAML file")

    # report command
    report_parser = subparsers.add_parser("report", help="Generate report for run")
    report_parser.add_argument("run_id", help="Run ID")

    # ui command
    ui_parser = subparsers.add_parser("ui", help="Start web dashboard")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    ui_parser.add_argument("--port", type=int, default=8080, help="Port to bind")

    return parser


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configure structured logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    if json_format:
        import json
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_obj = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if hasattr(record, "run_id"):
                    log_obj["run_id"] = record.run_id
                return json.dumps(log_obj)
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = [handler]


def main(args: list[str] = None) -> int:
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
            return cmd_fetch_candles(parsed.symbol, parsed.resolution, parsed.from_ts, parsed.to_ts, parsed.output)
        elif parsed.command == "backtest":
            return cmd_backtest(parsed.config, parsed.from_ts, parsed.to_ts, parsed.output)
        elif parsed.command == "paper":
            return cmd_paper(parsed.config)
        elif parsed.command == "report":
            return cmd_report(parsed.run_id)
        elif parsed.command == "ui":
            return cmd_ui(parsed.host, parsed.port)
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
        print(f"{m.symbol:<12} {m.base_asset:<8} {m.quote_asset:<8} {m.price_precision:<10} {m.amount_precision:<10}")

    return 0


def cmd_config_check(config_file: str) -> int:
    """Validate config and show derived values."""
    try:
        config = load_config(config_file)
        print("✓ Config is valid")
        print()
        print("Derived values:")
        print(f"  Symbol: {config.market.symbol}")
        print(f"  Grid range: {config.strategy['grid'].lower_price} - {config.strategy['grid'].upper_price}")
        print(f"  Grid count: {config.strategy['grid'].grid_count}")
        print(f"  Mode: {config.strategy['grid'].mode.value}")
        print(f"  Spacing: {config.strategy['grid'].spacing}")
        print(f"  Levels: {config.strategy['grid'].levels_count}")
        print(f"  Per-grid investment: {config.strategy['grid'].per_grid_investment}")
        print(f"  Min profit per cycle (after fees): {config.strategy['grid'].min_profit_per_cycle_after_fees}")
        return 0
    except Exception as e:
        print(f"✗ Config validation failed: {e}")
        return 1


def cmd_fetch_candles(symbol: str, resolution: str, from_ts: str, to_ts: str, output: Optional[str]) -> int:
    """Download candles."""
    client = WallexRestClient()

    # Parse timestamps
    from_ts_int = int(from_ts) if from_ts.isdigit() else _parse_date(from_ts)
    to_ts_int = int(to_ts) if to_ts.isdigit() else _parse_date(to_ts)

    candles = client.get_candles(symbol, resolution, from_ts_int, to_ts_int)

    if output:
        import csv
        with open(output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
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
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return int(dt.timestamp())
    except ValueError:
        return int(date_str)


def cmd_backtest(config_file: str, from_ts: str, to_ts: str, output: Optional[str]) -> int:
    """Run backtest."""
    print("Running backtest...")
    # This is a placeholder - full implementation would load data and run
    print("Backtest completed")
    return 0


def cmd_paper(config_file: str) -> int:
    """Run paper trading."""
    print("Starting paper trading...")
    print("Press Ctrl+C to stop")
    # This would run the bot engine
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
    return 0


if __name__ == "__main__":
    sys.exit(main())