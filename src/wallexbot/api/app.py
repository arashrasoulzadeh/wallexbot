"""FastAPI backend for the web UI (paper trading and backtests only; no API keys)."""

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError
from starlette.websockets import WebSocketDisconnect

from wallexbot.analytics.run_history import (
    DEFAULT_TZ,
    daily_breakdown,
    downsample,
    fills_csv,
    filter_range,
    parse_snapshots,
    run_summary,
    snapshots_csv,
    valid_timezone,
)
from wallexbot.api.manager import InvalidRunState, RunManager, UnknownRun
from wallexbot.config.defaults import default_config
from wallexbot.config.schema import validate_config
from wallexbot.engine.recovery import RecoveryError
from wallexbot.storage.repository import InMemoryRepository, Repository
from wallexbot.wallex.client import WallexRestClient

FINAL_STATES = ("stopped", "halted", "failed")


def _validation_errors(error: ValidationError) -> list[dict[str, Any]]:
    """Pydantic errors without the exception objects in `ctx`, so they serialize to JSON."""
    return [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()]


def _jsonable(value: Any) -> Any:
    """Decimals as strings (exact), recursively, so nothing is rounded on the way out."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _repo_summary(run: dict[str, Any]) -> dict[str, Any]:
    """Uniform run summary from a stored run (in-memory and SQLite repositories differ)."""
    config = run.get("config") or {}
    market = run.get("market") or config.get("market")
    if isinstance(market, dict):
        market = market.get("symbol")
    return {
        "id": run["id"],
        "status": run.get("status", "unknown"),
        "market": market or "unknown",
        "mode": run.get("mode") or config.get("mode") or "paper",
        "started_at": run.get("started_at", 0),
        "stopped_at": run.get("stopped_at") or 0,
    }


def create_app(
    repo: Repository | None = None,
    engine_manager: RunManager | None = None,
    stream_interval: float = 1.0,
) -> FastAPI:
    """Create FastAPI application."""

    if repo is None:
        repo = InMemoryRepository()
    manager = engine_manager if engine_manager is not None else RunManager(repo)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        yield
        await manager.shutdown()  # stop running engines so no run outlives the server

    # Templates
    template_dir = Path(__file__).parent.parent / "ui" / "templates"
    templates = Jinja2Templates(directory=str(template_dir))

    app = FastAPI(
        title="Wallex Grid Bot API",
        description="Paper trading dashboard API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/api/health")
    async def health() -> Any:
        return {"status": "ok"}

    # Markets
    @app.get("/api/markets")
    async def get_markets() -> Any:
        client = WallexRestClient()
        markets = client.get_markets()
        return [
            {
                "symbol": str(m.symbol),
                "base": m.base_asset,
                "quote": m.quote_asset,
                "price_precision": m.price_precision,
                "amount_precision": m.amount_precision,
            }
            for m in markets
        ]

    # Candles
    @app.get("/api/candles")
    async def get_candles(
        symbol: str,
        resolution: str = "60",
        from_ts: int = 0,
        to_ts: int = 0,
    ) -> Any:
        client = WallexRestClient()
        candles = client.get_candles(symbol, resolution, from_ts, to_ts)
        return [
            {
                "timestamp": c.open_time,
                "open": str(c.open),
                "high": str(c.high),
                "low": str(c.low),
                "close": str(c.close),
                "volume": str(c.volume),
            }
            for c in candles
        ]

    # Runs --------------------------------------------------------------------------

    @app.get("/api/runs")
    async def list_runs() -> Any:
        rows = []
        recoverable = {r["id"] for r in manager.recoverable()}
        for run in repo.list_runs():
            row = _repo_summary(run)
            row["recoverable"] = row["id"] in recoverable
            snap = manager.snapshot(row["id"])
            if snap is not None:  # this process owns the run: show its live state
                row["status"] = snap["status"]["state"]
            rows.append(row)
        return rows

    def _live_or_none(run_id: str) -> dict[str, Any] | None:
        snap = manager.snapshot(run_id)
        return snap if isinstance(snap, dict) else None

    def _stored_run(run_id: str) -> dict[str, Any]:
        run = repo.get_run(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return run

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> Any:
        snap = _live_or_none(run_id)
        if snap is not None:
            stored = repo.get_run(run_id)
            summary = _repo_summary(stored) if stored else {"id": run_id}
            return {**summary, **snap, "status": snap["status"]}
        run = _stored_run(run_id)
        return {**run, **_repo_summary(run), "status": {"state": run.get("status", "unknown")}}

    @app.get("/api/runs/{run_id}/orders")
    async def get_run_orders(run_id: str) -> Any:
        snap = _live_or_none(run_id)
        if snap is not None:
            return snap["orders"]
        _stored_run(run_id)
        return repo.get_open_orders(run_id)

    @app.get("/api/runs/{run_id}/fills")
    async def get_run_fills(run_id: str) -> Any:
        snap = _live_or_none(run_id)
        if snap is not None:
            return snap["fills"]
        _stored_run(run_id)
        return repo.get_fills(run_id)

    @app.get("/api/runs/{run_id}/pnl")
    async def get_run_pnl(run_id: str) -> Any:
        snap = _live_or_none(run_id)
        if snap is not None:
            s = snap["status"]
            return {
                "realized": s["realized_pnl"],
                "unrealized": s["unrealized_pnl"],
                "total": s["total_pnl"],
                "fees": s["fees_paid"],
                "equity": s["equity"],
            }
        _stored_run(run_id)
        return {
            "realized": "0",
            "unrealized": "0",
            "total": "0",
            "fees": "0",
            "equity": None,
            "note": "live figures exist only for runs of the current server process",
        }

    @app.get("/api/runs/{run_id}/grid")
    async def get_run_grid(run_id: str) -> Any:
        snap = _live_or_none(run_id)
        if snap is not None:
            return snap["grid"]
        _stored_run(run_id)
        state = repo.get_grid_state(run_id)
        return state or {"levels": []}

    # History -----------------------------------------------------------------------

    def _history_run(run_id: str) -> dict[str, Any]:
        """The stored run as a summary dict (live state wins over the stored status)."""
        run = repo.get_run(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        base = _repo_summary(run)
        live = _live_or_none(run_id)
        if live is not None:
            base["status"] = live["status"]["state"]
        return base

    @app.get("/api/history/runs")
    async def history_runs() -> Any:
        rows = []
        for run in repo.list_runs():
            base = _history_run(run["id"])
            points = parse_snapshots(repo.get_snapshots(run["id"]))
            rows.append(run_summary(base, points, repo.get_fills(run["id"])))
        rows.sort(key=lambda r: r["started_at"], reverse=True)
        return _jsonable(rows)

    @app.get("/api/history/runs/{run_id}")
    async def history_run(
        run_id: str,
        since: int | None = None,
        until: int | None = None,
        max_points: int = Query(600, ge=1, le=5000),
        fills_limit: int = Query(500, ge=1, le=5000),
        side: Literal["BUY", "SELL"] | None = None,
        tz: str = DEFAULT_TZ,
    ) -> Any:
        """One run's history for the History page, limited to a time range (milliseconds)."""
        if not valid_timezone(tz):
            raise HTTPException(422, f"unknown time zone {tz!r}")
        base = _history_run(run_id)
        points = parse_snapshots(repo.get_snapshots(run_id, since, until))
        all_fills = [
            f
            for f in repo.get_fills(run_id)
            if (since is None or f["timestamp"] >= since)
            and (until is None or f["timestamp"] <= until)
        ]
        shown = [f for f in all_fills if side is None or f.get("side") == side]
        events = repo.get_events(run_id)[-200:]
        return _jsonable(
            {
                "summary": run_summary(base, points, all_fills),
                "series": [
                    {"ts": p.ts, "price": p.price, "equity": p.equity, "realized": p.realized}
                    for p in downsample(points, max_points)
                ],
                "daily": daily_breakdown(points, all_fills, tz),
                "fills": list(reversed(shown))[:fills_limit],
                "events": list(reversed(events)),
                "tz": tz,
                "range": {"since": since, "until": until},
            }
        )

    def _csv(name: str, text: str) -> Response:
        return Response(
            content=text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/api/history/runs/{run_id}/fills.csv")
    async def history_fills_csv(
        run_id: str, since: int | None = None, until: int | None = None
    ) -> Response:
        _history_run(run_id)
        fills = [
            f
            for f in repo.get_fills(run_id)
            if (since is None or f["timestamp"] >= since)
            and (until is None or f["timestamp"] <= until)
        ]
        return _csv(f"{run_id}_fills.csv", fills_csv(fills))

    @app.get("/api/history/runs/{run_id}/snapshots.csv")
    async def history_snapshots_csv(
        run_id: str, since: int | None = None, until: int | None = None
    ) -> Response:
        _history_run(run_id)
        points = filter_range(parse_snapshots(repo.get_snapshots(run_id)), since, until)
        return _csv(f"{run_id}_history.csv", snapshots_csv(points))

    # Config ------------------------------------------------------------------------

    class ConfigValidateRequest(BaseModel):
        exchange: dict[str, Any]
        market: dict[str, Any]
        strategy: dict[str, Any]
        risk: dict[str, Any]
        simulation: dict[str, Any]
        logging: dict[str, Any]

    @app.get("/api/config/default")
    async def get_default_config() -> Any:
        return default_config()

    @app.post("/api/config/validate")
    async def validate_config_endpoint(request: ConfigValidateRequest) -> Any:
        try:
            config = validate_config(request.model_dump())
        except ValidationError as e:
            return {
                "valid": False,
                "errors": [
                    err["msg"].removeprefix("Value error, ") for err in _validation_errors(e)
                ],
            }
        except ValueError as e:
            return {"valid": False, "errors": [str(e)]}
        grid = config.strategy["grid"]
        return {
            "valid": True,
            "derived": {
                "spacing": str(grid.spacing) if grid.spacing else None,
                "spacing_pct": str(grid.spacing_pct) if grid.spacing_pct else None,
                "levels_count": grid.levels_count,
                "per_grid_investment": str(grid.per_grid_investment)
                if grid.per_grid_investment
                else None,
                "min_profit_per_cycle_after_fees": str(grid.min_profit_per_cycle_after_fees)
                if grid.min_profit_per_cycle_after_fees
                else None,
                "round_trip_fee_rate": str(grid.round_trip_fee_rate)
                if grid.round_trip_fee_rate
                else None,
            },
        }

    # Backtests ---------------------------------------------------------------------

    class BacktestRequest(BaseModel):
        config: dict[str, Any]
        from_ts: int
        to_ts: int
        resolution: str = "60"

    @app.post("/api/backtests")
    async def start_backtest(request: BacktestRequest) -> Any:
        try:
            config = validate_config(request.config)
        except ValidationError as e:
            raise HTTPException(422, detail=_validation_errors(e)) from e
        if request.from_ts >= request.to_ts:
            raise HTTPException(422, detail="from_ts must be before to_ts")
        bt_id = await manager.start_backtest(
            config, request.from_ts, request.to_ts, request.resolution
        )
        return {"id": bt_id}

    @app.get("/api/backtests/{bt_id}")
    async def get_backtest(bt_id: str) -> Any:
        result = manager.backtest(bt_id)
        if not isinstance(result, dict):
            raise HTTPException(404, "Backtest not found")
        return result

    # Paper runs --------------------------------------------------------------------

    class PaperRunRequest(BaseModel):
        config: dict[str, Any]
        feed: str = Field(default="ws", pattern="^(ws|poll)$")

    @app.post("/api/paper-runs")
    async def start_paper_run(request: PaperRunRequest) -> Any:
        try:
            config = validate_config(request.config)
        except ValidationError as e:
            raise HTTPException(422, detail=_validation_errors(e)) from e
        try:
            run_id = await manager.start_paper_run(config, request.feed)
        except ValueError as e:
            raise HTTPException(422, detail=str(e)) from e
        return {"id": run_id}

    async def _control(action: str, run_id: str, result: str) -> dict[str, str]:
        try:
            await getattr(manager, action)(run_id)
        except UnknownRun as e:
            raise HTTPException(404, "Run not found") from e
        except InvalidRunState as e:
            raise HTTPException(409, str(e)) from e
        return {"status": result}

    @app.post("/api/runs/{run_id}/pause")
    async def pause_run(run_id: str) -> Any:
        return await _control("pause_run", run_id, "paused")

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: str) -> Any:
        return await _control("resume_run", run_id, "running")

    @app.post("/api/runs/{run_id}/stop")
    async def stop_run(run_id: str) -> Any:
        return await _control("stop_run", run_id, "stopped")

    @app.post("/api/runs/{run_id}/kill")
    async def kill_run(run_id: str) -> Any:
        return await _control("kill_run", run_id, "killed")

    class RecoverRequest(BaseModel):
        feed: str = Field(default="ws", pattern="^(ws|poll)$")

    @app.post("/api/runs/{run_id}/recover")
    async def recover_run(run_id: str, request: RecoverRequest | None = None) -> Any:
        """Continue a run that a crash left unfinished (same id, same record)."""
        if not repo.get_run(run_id):
            raise HTTPException(404, "Run not found")
        try:
            await manager.recover_run(run_id, request.feed if request else "ws")
        except (InvalidRunState, RecoveryError) as e:
            raise HTTPException(409, str(e)) from e
        return {"id": run_id, "status": "running"}

    # Notifications -----------------------------------------------------------------

    @app.post("/api/notify/test")
    async def test_notification(request: Request) -> Any:
        return {"message": "Telegram is not configured: no notification was sent"}

    # Admin endpoints
    @app.post("/api/admin/backup")
    async def backup_database() -> Any:
        import shutil
        import time

        src = "wallexbot.db"
        dst = f"wallexbot.db.backup.{int(time.time())}"
        try:
            shutil.copy2(src, dst)
            return {"message": f"Backup created: {dst}"}
        except Exception as e:
            return {"message": f"Backup failed: {e}"}

    @app.post("/api/admin/vacuum")
    async def vacuum_database() -> Any:
        import sqlite3

        try:
            conn = sqlite3.connect("wallexbot.db")
            conn.execute("VACUUM")
            conn.close()
            return {"message": "Database vacuumed"}
        except Exception as e:
            return {"message": f"Vacuum failed: {e}"}

    @app.post("/api/admin/backup-history")
    async def backup_history() -> Any:
        import shutil
        import time

        src = "wallexbot_history.db"
        dst = f"wallexbot_history.db.backup.{int(time.time())}"
        try:
            shutil.copy2(src, dst)
            return {"message": f"History backup created: {dst}"}
        except Exception as e:
            return {"message": f"Backup failed: {e}"}

    # Live updates ------------------------------------------------------------------

    @app.websocket("/api/stream")
    async def websocket_stream(websocket: WebSocket, run_id: str = "") -> None:
        """Push a snapshot of one run every `stream_interval` seconds until it finishes."""
        await websocket.accept()
        try:
            while True:
                snap = _live_or_none(run_id)
                if snap is None:
                    await websocket.close(code=4404)
                    return
                final = snap["status"]["state"] in FINAL_STATES
                await websocket.send_json({"type": "snapshot", "final": final, "run": snap})
                if final:
                    await websocket.close()
                    return
                await asyncio.sleep(stream_interval)
        except (WebSocketDisconnect, RuntimeError):
            return  # the browser went away

    # Static files and pages --------------------------------------------------------
    static_dir = Path(__file__).parent.parent / "ui" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def page(path: str, template: str, key: str) -> None:
        async def render(request: Request) -> HTMLResponse:
            return templates.TemplateResponse(request, template, {"page": key})

        app.add_api_route(
            path, render, methods=["GET"], response_class=HTMLResponse, include_in_schema=False
        )

    page("/", "dashboard.html", "dashboard")
    page("/dashboard", "dashboard.html", "dashboard")
    page("/configure", "configure.html", "configure")
    page("/backtest", "backtest.html", "backtest")
    page("/paper", "paper.html", "paper")
    page("/runs", "runs.html", "runs")
    page("/history", "history.html", "history")
    page("/settings", "unavailable.html", "settings")

    return app
