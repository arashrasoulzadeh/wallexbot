"""A neutral look back over the recent paper runs.

It adds up what the runs did and says plainly when the evidence is too thin to judge. It never says
whether to continue, switch coins or go live: those are the user's decisions.
"""

from decimal import Decimal
from typing import Any

from wallexbot.analytics.run_history import Point, parse_snapshots, run_summary
from wallexbot.storage.repository import Repository

DAY_MS = 86_400_000
MIN_COVERAGE = Decimal("0.8")  # share of the period the runs' own price history should cover
MIN_CYCLES = 10  # fewer completed buy-sell cycles than this is anecdote, not evidence


def start_point(
    repo: Repository, run_id: str, points: list[Point], since: int | None = None
) -> Point | None:
    """Where a summary is measured from: the last snapshot before `since`, or else the run's
    starting state (initial equity before the entry fee, nothing earned or paid yet)."""
    if since is not None:
        before = parse_snapshots(repo.get_snapshots(run_id, until=since - 1)[-1:])
        if before:
            return before[0]
    checkpoint = repo.get_checkpoint(run_id)
    initial = ((checkpoint or {}).get("engine") or {}).get("initial_equity")
    if initial is None or not points:
        return None  # nothing better than the first snapshot
    first = points[0]
    return Point(
        ts=first.ts,
        price=first.price,
        equity=Decimal(str(initial)),
        realized=Decimal(0),
        fees=Decimal(0),
        open_orders=0,
        fills=0,
        cycles=0,
    )


def _market_of(run: dict[str, Any]) -> str:
    config = run.get("config") or {}
    market = run.get("market") or config.get("market")
    if isinstance(market, dict):
        market = market.get("symbol")
    return str(market or "unknown")


def review(repo: Repository, now_ms: int, days: int = 7) -> dict[str, Any]:
    """Every run that started in the last `days` days, with totals and honest caveats."""
    since = now_ms - days * DAY_MS
    runs: list[dict[str, Any]] = []
    for run in repo.list_runs():
        if int(run.get("started_at") or 0) < since:
            continue
        base = {
            "id": run["id"],
            "status": run.get("status", "unknown"),
            "market": _market_of(run),
            "started_at": run.get("started_at", 0),
            "stopped_at": run.get("stopped_at") or 0,
        }
        points = parse_snapshots(repo.get_snapshots(run["id"]))
        runs.append(
            run_summary(
                base, points, repo.get_fills(run["id"]), start_point(repo, run["id"], points)
            )
        )
    runs.sort(key=lambda r: r["started_at"])

    zero = Decimal(0)
    totals = {
        "runs": len(runs),
        "hours": sum((Decimal(r["duration_ms"]) for r in runs), zero) / 3_600_000,
        "fills": sum(r["fills"] for r in runs),
        "cycles": sum(r["cycles"] for r in runs),
        "realized": sum((r["realized"] for r in runs), zero),
        "fees": sum((r["fees"] for r in runs), zero),
        "worst_drawdown_pct": max((r["max_drawdown_pct"] for r in runs), default=zero),
        "beat_holding": sum(1 for r in runs if r["return_pct"] > r["price_change_pct"]),
    }
    notes: list[dict[str, Any]] = []
    if not runs:
        notes.append({"code": "no_runs", "params": {"days": days}})
    else:
        wanted_hours = Decimal(days * 24)
        if totals["hours"] < wanted_hours * MIN_COVERAGE:
            notes.append(
                {
                    "code": "short_coverage",
                    "params": {"hours": totals["hours"], "wanted": wanted_hours},
                }
            )
        if totals["cycles"] < MIN_CYCLES:
            notes.append(
                {"code": "few_cycles", "params": {"cycles": totals["cycles"], "needed": MIN_CYCLES}}
            )
    return {"days": days, "runs": runs, "totals": totals, "notes": notes}
