"""FastAPI backend for web UI."""

from contextlib import asynccontextmanager
from typing: Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from wallexbot.storage.repository import Repository, InMemoryRepository
from wallexbot.config.schema import validate_config, Config
from wallexbot.domain.market import Symbol
from wallexbot.wallex.client import WallexRestClient
from wallexbot.wallex.models import Candle


class EngineManager:
    """Manages bot engine instances."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo
        self._running: dict[str, dict] = {}  # run_id -> {engine, config, task}

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
async def lifespan(app: FastAPI):
    """Application lifespan."""
    # Startup
    yield
    # Shutdown


def create_app(
    repo: Optional[Repository] = None,
    engine_manager: Optional[EngineManager] = None,
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
    async def health():
        return {"status": "ok"}

    # Markets
    @app.get("/api/markets")
    async def get_markets():
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
    ):
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
    async def list_runs():
        # In a real implementation, this would query the repo
        # For now, return mock data for UI testing
        return [
            {
                "id": "run_123",
                "status": "completed",
                "market": "USDTTMN",
                "mode": "arithmetic",
                "started_at": 1705238400000,
                "stopped_at": 1705324800000,
            }
        ]

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        run = repo.get_run(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return run

    @app.get("/api/runs/{run_id}/orders")
    async def get_run_orders(run_id: str):
        orders = repo.get_open_orders(run_id)
        return orders

    @app.get("/api/runs/{run_id}/fills")
    async def get_run_fills(run_id: str):
        fills = repo.get_fills(run_id)
        return fills

    @app.get("/api/runs/{run_id}/pnl")
    async def get_run_pnl(run_id: str):
        # Placeholder - would compute from fills
        return {"realized": "0", "unrealized": "0", "total": "0"}

    @app.get("/api/runs/{run_id}/grid")
    async def get_run_grid(run_id: str):
        state = repo.get_grid_state(run_id)
        if not state:
            return {"levels": []}
        return state

    # Config validation
    class ConfigValidateRequest(BaseModel):
        exchange: dict
        market: dict
        strategy: dict
        risk: dict
        simulation: dict
        logging: dict

    @app.post("/api/config/validate")
    async def validate_config_endpoint(request: ConfigValidateRequest):
        try:
            config = validate_config(request.model_dump())
            return {
                "valid": True,
                "derived": {
                    "spacing": str(config.strategy['grid'].spacing) if config.strategy['grid'].spacing else None,
                    "levels_count": config.strategy['grid'].levels_count,
                    "per_grid_investment": str(config.strategy['grid'].per_grid_investment) if config.strategy['grid'].per_grid_investment else None,
                    "min_profit_per_cycle_after_fees": str(config.strategy['grid'].min_profit_per_cycle_after_fees) if config.strategy['grid'].min_profit_per_cycle_after_fees else None,
                },
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [str(e)],
            }

    # Backtest
    class BacktestRequest(BaseModel):
        config: dict
        from_ts: int
        to_ts: int

    @app.post("/api/backtests")
    async def start_backtest(request: BacktestRequest):
        run_id = await engine_manager.start_backtest(
            validate_config(request.config),
            request.from_ts,
            request.to_ts,
        )
        return {"id": run_id}

    # Paper runs
    class PaperRunRequest(BaseModel):
        config: dict

    @app.post("/api/paper-runs")
    async def start_paper_run(request: PaperRunRequest):
        run_id = await engine_manager.start_paper_run(validate_config(request.config))
        return {"id": run_id}

    @app.post("/api/runs/{run_id}/pause")
    async def pause_run(run_id: str):
        await engine_manager.pause_run(run_id)
        return {"status": "paused"}

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: str):
        await engine_manager.resume_run(run_id)
        return {"status": "running"}

    @app.post("/api/runs/{run_id}/stop")
    async def stop_run(run_id: str):
        await engine_manager.stop_run(run_id)
        return {"status": "stopped"}

    @app.post("/api/runs/{run_id}/kill")
    async def kill_run(run_id: str):
        await engine_manager.kill_run(run_id)
        return {"status": "killed"}

    # Notification test endpoint
    @app.post("/api/notify/test")
    async def test_notification(request: Request):
        data = await request.json()
        # In real implementation, would send via Telegram
        return {"message": f"Test notification sent: {data.get('message', 'test')}"}

    # Admin endpoints
    @app.post("/api/admin/backup")
    async def backup_database():
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
    async def vacuum_database():
        import sqlite3
        try:
            conn = sqlite3.connect("wallexbot.db")
            conn.execute("VACUUM")
            conn.close()
            return {"message": "Database vacuumed"}
        except Exception as e:
            return {"message": f"Vacuum failed: {e}"}

    @app.post("/api/admin/backup-history")
    async def backup_history():
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
    async def websocket_stream(websocket):
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
    async def dashboard(request: Request):
        return templates.TemplateResponse("base.html", {"request": request})

    @app.get("/configure")
    async def configure_page(request: Request):
        return templates.TemplateResponse("configure.html", {"request": request})

    @app.get("/backtest")
    async def backtest_page(request: Request):
        return templates.TemplateResponse("backtest.html", {"request": request})

    @app.get("/paper")
    async def paper_page(request: Request):
        return templates.TemplateResponse("paper.html", {"request": request})

    @app.get("/runs")
    async def runs_page(request: Request):
        return templates.TemplateResponse("runs.html", {"request": request})

    @app.get("/history")
    async def history_page(request: Request):
        return templates.TemplateResponse("history.html", {"request": request})

    @app.get("/settings")
    async def settings_page(request: Request):
        return templates.TemplateResponse("settings.html", {"request": request})

    # Serve static files (UI)
    try:
        static_dir = Path(__file__).parent.parent / "ui" / "static"
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    except RuntimeError:
        pass

    @app.get("/")
    async def root():
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