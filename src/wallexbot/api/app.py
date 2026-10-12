"""FastAPI backend for web UI."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError

from wallexbot.config.schema import Config, validate_config
from wallexbot.storage.repository import InMemoryRepository, Repository
from wallexbot.wallex.client import WallexRestClient


class EngineManager:
    """Manages bot engine instances."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo
        self._running: dict[str, dict[str, Any]] = {}  # run_id -> {engine, config, task}

    async def start_backtest(self, config: Config, from_ts: int, to_ts: int) -> str:
        """Start a backtest."""
        # Placeholder
        return "backtest_123"

    async def start_paper_run(self, config: Config) -> str:
        """Start a paper run."""
        # Placeholder
        return "paper_123"

    async def pause_run(self, run_id: str) -> None:
        """Pause a run."""
        pass

    async def resume_run(self, run_id: str) -> None:
        """Resume a run."""
        pass

    async def stop_run(self, run_id: str) -> None:
        """Stop a run."""
        pass

    async def kill_run(self, run_id: str) -> None:
        """Kill a run."""
        pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Application lifespan."""
    # Startup
    yield
    # Shutdown


def create_app(
    repo: Repository | None = None,
    engine_manager: EngineManager | None = None,
) -> FastAPI:
    """Create FastAPI application."""

    if repo is None:
        repo = InMemoryRepository()

    if engine_manager is None:
        engine_manager = EngineManager(repo)

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

    # Runs
    @app.get("/api/runs")
    async def list_runs() -> Any:
        runs = repo.list_runs()
        return [
            {
                "id": r["id"],
                "status": r.get("status", "unknown"),
                "market": r.get("config", {}).get("market", {}).get("symbol", "unknown"),
                "mode": r.get("config", {})
                .get("strategy", {})
                .get("grid", {})
                .get("mode", "unknown"),
                "started_at": r.get("created_at", 0),
                "stopped_at": r.get("stopped_at", 0),
            }
            for r in runs
        ]

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> Any:
        run = repo.get_run(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return run

    @app.get("/api/runs/{run_id}/orders")
    async def get_run_orders(run_id: str) -> Any:
        orders = repo.get_open_orders(run_id)
        return orders

    @app.get("/api/runs/{run_id}/fills")
    async def get_run_fills(run_id: str) -> Any:
        fills = repo.get_fills(run_id)
        return fills

    @app.get("/api/runs/{run_id}/pnl")
    async def get_run_pnl(run_id: str) -> Any:
        # Placeholder - would compute from fills
        return {"realized": "0", "unrealized": "0", "total": "0"}

    @app.get("/api/runs/{run_id}/grid")
    async def get_run_grid(run_id: str) -> Any:
        state = repo.get_grid_state(run_id)
        if not state:
            return {"levels": []}
        return state

    # Config validation
    class ConfigValidateRequest(BaseModel):
        exchange: dict[str, Any]
        market: dict[str, Any]
        strategy: dict[str, Any]
        risk: dict[str, Any]
        simulation: dict[str, Any]
        logging: dict[str, Any]

    @app.post("/api/config/validate")
    async def validate_config_endpoint(request: ConfigValidateRequest) -> Any:
        try:
            config = validate_config(request.model_dump())
            return {
                "valid": True,
                "derived": {
                    "spacing": str(config.strategy["grid"].spacing)
                    if config.strategy["grid"].spacing
                    else None,
                    "levels_count": config.strategy["grid"].levels_count,
                    "per_grid_investment": str(config.strategy["grid"].per_grid_investment)
                    if config.strategy["grid"].per_grid_investment
                    else None,
                    "min_profit_per_cycle_after_fees": str(
                        config.strategy["grid"].min_profit_per_cycle_after_fees
                    )
                    if config.strategy["grid"].min_profit_per_cycle_after_fees
                    else None,
                },
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [str(e)],
            }

    # Backtest
    class BacktestRequest(BaseModel):
        config: dict[str, Any]
        from_ts: int
        to_ts: int

    @app.post("/api/backtests")
    async def start_backtest(request: BacktestRequest) -> Any:
        try:
            config = validate_config(request.config)
        except ValidationError as e:
            raise HTTPException(422, detail=e.errors()) from e
        run_id = await engine_manager.start_backtest(
            config,
            request.from_ts,
            request.to_ts,
        )
        return {"id": run_id}

    # Paper runs
    class PaperRunRequest(BaseModel):
        config: dict[str, Any]

    @app.post("/api/paper-runs")
    async def start_paper_run(request: PaperRunRequest) -> Any:
        try:
            config = validate_config(request.config)
        except ValidationError as e:
            raise HTTPException(422, detail=e.errors()) from e
        run_id = await engine_manager.start_paper_run(config)
        return {"id": run_id}

    @app.post("/api/runs/{run_id}/pause")
    async def pause_run(run_id: str) -> Any:
        await engine_manager.pause_run(run_id)
        return {"status": "paused"}

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: str) -> Any:
        await engine_manager.resume_run(run_id)
        return {"status": "running"}

    @app.post("/api/runs/{run_id}/stop")
    async def stop_run(run_id: str) -> Any:
        await engine_manager.stop_run(run_id)
        return {"status": "stopped"}

    @app.post("/api/runs/{run_id}/kill")
    async def kill_run(run_id: str) -> Any:
        await engine_manager.kill_run(run_id)
        return {"status": "killed"}

    # Notification test endpoint
    @app.post("/api/notify/test")
    async def test_notification(request: Request) -> Any:
        data = await request.json()
        # In real implementation, would send via Telegram
        return {"message": f"Test notification sent: {data.get('message', 'test')}"}

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

    # WebSocket for live updates
    @app.websocket("/api/stream")
    async def websocket_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                # Echo for now
                await websocket.send_text(data)
        except Exception:
            await websocket.close()

    # UI Routes - serve templates
    @app.get("/dashboard")
    async def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "base.html")

    @app.get("/configure")
    async def configure_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "configure.html")

    @app.get("/backtest")
    async def backtest_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "backtest.html")

    @app.get("/paper")
    async def paper_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "paper.html")

    @app.get("/runs")
    async def runs_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "runs.html")

    @app.get("/history")
    async def history_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "history.html")

    @app.get("/settings")
    async def settings_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "settings.html")

    # Serve static files (UI)
    try:
        static_dir = Path(__file__).parent.parent / "ui" / "static"
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    except RuntimeError:
        pass

    @app.get("/")
    async def root() -> Any:
        return HTMLResponse("""
        <html>
            <head><title>Wallex Grid Bot</title></head>
            <body>
                <h1>Wallex Grid Bot Dashboard</h1>
                <p><a href="/docs">API Documentation</a></p>
                <p><a href="/dashboard">Dashboard</a></p>
            </body>
        </html>
        """)

    return app
