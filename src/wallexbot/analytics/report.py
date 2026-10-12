"""Human-readable backtest summaries (terminal text and Markdown)."""

from decimal import Decimal

from wallexbot.analytics.backtest import BacktestResult


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _pct(value: Decimal) -> str:
    return f"{value:.2f}%"


def summary_rows(result: BacktestResult) -> list[tuple[str, str]]:
    """The headline numbers, in display order."""
    m = result.metrics
    return [
        ("Total return", _pct(m.total_return_pct)),
        ("Buy and hold", _pct(m.buy_and_hold_return)),
        ("Outperformance", _pct(m.outperformance)),
        ("Realized PnL (cycles, net of fees)", _money(m.realized_pnl)),
        ("Unrealized PnL (inventory, entry fee)", _money(m.unrealized_pnl)),
        ("Completed cycles", str(m.completed_cycles)),
        ("Avg profit per cycle", _money(m.avg_profit_per_cycle)),
        ("Fees paid", _money(m.fees_paid)),
        ("Max drawdown", _pct(m.max_drawdown)),
        ("Time in range", _pct(m.time_in_range)),
        ("Rejected orders", str(m.rejected_orders)),
    ]


def format_summary(symbol: str, result: BacktestResult) -> str:
    """Plain text for the terminal."""
    lines = [f"Backtest {symbol}"]
    width = max(len(label) for label, _ in summary_rows(result))
    lines += [f"{label:<{width}}  {value}" for label, value in summary_rows(result)]
    return "\n".join(lines)


def render_markdown(
    symbol: str,
    result: BacktestResult,
    *,
    maker_fee: Decimal,
    taker_fee: Decimal,
    min_notional: Decimal,
    candles: int,
) -> str:
    """A Markdown report that states its assumptions, not just the results."""
    rows = "\n".join(f"| {label} | {value} |" for label, value in summary_rows(result))
    events = "\n".join(f"- {e}" for e in result.events[:50]) or "- none"
    return f"""# Backtest {symbol}

Paper trading on {candles} candles (4 price points each: open, extremes, close).
No API keys were used.

| Metric | Value |
|---|---|
{rows}

## Fee assumptions

- Maker fee {maker_fee:.4%}, taker fee {taker_fee:.4%} (charged in the asset received).
- Minimum order value {min_notional}.
- These are **configuration values, not Wallex's published rates**: the real fee tier is only
  visible with an authenticated account. Results are only as good as these numbers.

## Modelling limits

- Unlimited liquidity per price point: an order fills completely once price trades through it.
- No queue position, slippage or latency.
- Candle highs/lows are visited in a fixed order (up candles dip first, down candles spike first).

## Events

{events}
"""
