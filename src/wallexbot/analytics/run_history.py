"""History analytics: pure functions over a run's snapshots and fills.

Everything is stored in UTC milliseconds. Days are cut at midnight in a display time zone
(default Asia/Tehran, decision D15; Iran has had no daylight saving since 2022, UTC+03:30).
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "Asia/Tehran"
_FALLBACK_ZONES: dict[str, tzinfo] = {
    "Asia/Tehran": timezone(timedelta(hours=3, minutes=30)),
    "UTC": UTC,
}


@dataclass(frozen=True)
class Point:
    """One snapshot of a run."""

    ts: int
    price: Decimal | None
    equity: Decimal
    realized: Decimal
    fees: Decimal
    open_orders: int
    fills: int
    cycles: int


def parse_snapshots(rows: list[dict[str, Any]]) -> list[Point]:
    """Stored snapshot rows -> exact Decimal points."""
    return [
        Point(
            ts=int(r["ts"]),
            price=None if r.get("price") is None else Decimal(str(r["price"])),
            equity=Decimal(str(r["equity"])),
            realized=Decimal(str(r["realized"])),
            fees=Decimal(str(r["fees"])),
            open_orders=int(r["open_orders"]),
            fills=int(r["fills"]),
            cycles=int(r["cycles"]),
        )
        for r in rows
    ]


def filter_range(points: list[Point], since: int | None, until: int | None) -> list[Point]:
    """Points with since <= ts <= until (either bound optional)."""
    return [
        p for p in points if (since is None or p.ts >= since) and (until is None or p.ts <= until)
    ]


def downsample(points: list[Point], max_points: int) -> list[Point]:
    """At most `max_points`, evenly spread, always keeping the first and the last."""
    n = len(points)
    if n <= max_points:
        return list(points)
    if max_points <= 1:
        return [points[-1]] if n else []
    indexes = sorted({round(i * (n - 1) / (max_points - 1)) for i in range(max_points)})
    return [points[i] for i in indexes]


def max_drawdown_pct(points: list[Point]) -> Decimal:
    """Largest fall from a running peak of equity, in percent."""
    peak = Decimal(0)
    worst = Decimal(0)
    for p in points:
        peak = max(peak, p.equity)
        if peak > 0:
            worst = max(worst, (peak - p.equity) / peak * 100)
    return worst


def _zone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return _FALLBACK_ZONES.get(name, UTC)


def local_day(ts_ms: int, tz: str = DEFAULT_TZ) -> str:
    """The calendar day (YYYY-MM-DD) of a timestamp in the given time zone."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=_zone(tz)).strftime("%Y-%m-%d")


def _volume(fill: dict[str, Any]) -> Decimal:
    return Decimal(str(fill["price"])) * Decimal(str(fill["quantity"]))


def daily_breakdown(
    points: list[Point], fills: list[dict[str, Any]], tz: str = DEFAULT_TZ
) -> list[dict[str, Any]]:
    """One row per local day: equity/realized/fee/cycle change and trading activity.

    Each day is measured from where the previous day ended; the first day from the run's first
    snapshot.
    """
    by_day: dict[str, list[Point]] = {}
    for p in sorted(points, key=lambda p: p.ts):
        by_day.setdefault(local_day(p.ts, tz), []).append(p)
    fills_by_day: dict[str, list[dict[str, Any]]] = {}
    for f in fills:
        fills_by_day.setdefault(local_day(int(f["timestamp"]), tz), []).append(f)

    rows = []
    previous_end: Point | None = None
    for day in sorted(set(by_day) | set(fills_by_day)):
        day_points = by_day.get(day, [])
        day_fills = fills_by_day.get(day, [])
        if day_points:
            start = previous_end or day_points[0]
            end = day_points[-1]
            previous_end = end
            changes = {
                "equity_change": end.equity - start.equity,
                "realized_change": end.realized - start.realized,
                "fees": end.fees - start.fees,
                "cycles": end.cycles - start.cycles,
                "equity_end": end.equity,
            }
        else:
            changes = {
                "equity_change": Decimal(0),
                "realized_change": Decimal(0),
                "fees": Decimal(0),
                "cycles": 0,
                "equity_end": previous_end.equity if previous_end else Decimal(0),
            }
        rows.append(
            {
                "date": day,
                **changes,
                "fills": len(day_fills),
                "buys": sum(1 for f in day_fills if f.get("side") == "BUY"),
                "sells": sum(1 for f in day_fills if f.get("side") == "SELL"),
                "volume": sum((_volume(f) for f in day_fills), Decimal(0)),
            }
        )
    return rows


def run_summary(
    run: dict[str, Any], points: list[Point], fills: list[dict[str, Any]]
) -> dict[str, Any]:
    """Headline numbers of one run, from whatever history was recorded."""
    first = points[0] if points else None
    last = points[-1] if points else None
    zero = Decimal(0)
    return_pct = (
        (last.equity - first.equity) / first.equity * 100
        if first and last and first.equity > 0
        else zero
    )
    price_change = (
        (last.price - first.price) / first.price * 100
        if first and last and first.price and last.price
        else zero
    )
    started = int(run.get("started_at") or 0)
    ended = int(run.get("stopped_at") or 0) or (last.ts if last else started)
    return {
        "id": run["id"],
        "status": run.get("status", "unknown"),
        "market": run.get("market", ""),
        "started_at": started,
        "ended_at": ended,
        "duration_ms": max(ended - started, 0),
        "return_pct": return_pct,
        "max_drawdown_pct": max_drawdown_pct(points),
        "realized": last.realized if last else zero,
        "fees": last.fees if last else zero,
        "cycles": last.cycles if last else 0,
        "fills": len(fills),
        "buys": sum(1 for f in fills if f.get("side") == "BUY"),
        "sells": sum(1 for f in fills if f.get("side") == "SELL"),
        "volume": sum((_volume(f) for f in fills), zero),
        "first_price": first.price if first else None,
        "last_price": last.price if last else None,
        "price_change_pct": price_change,
    }


def _iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fills_csv(fills: list[dict[str, Any]]) -> str:
    """The trades as CSV (times in UTC)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["time_utc", "timestamp_ms", "side", "price", "quantity", "fee", "fee_asset", "level"]
    )
    for f in fills:
        ts = int(f["timestamp"])
        writer.writerow(
            [
                _iso(ts),
                ts,
                f.get("side") or "",
                f["price"],
                f["quantity"],
                f["fee"],
                f["fee_asset"],
                "" if f.get("level_index") is None else f["level_index"],
            ]
        )
    return out.getvalue()


def snapshots_csv(points: list[Point]) -> str:
    """The price/equity history as CSV (times in UTC)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "time_utc",
            "timestamp_ms",
            "price",
            "equity",
            "realized",
            "fees",
            "open_orders",
            "fills",
            "cycles",
        ]
    )
    for p in points:
        writer.writerow(
            [
                _iso(p.ts),
                p.ts,
                "" if p.price is None else p.price,
                p.equity,
                p.realized,
                p.fees,
                p.open_orders,
                p.fills,
                p.cycles,
            ]
        )
    return out.getvalue()
