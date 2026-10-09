"""FastAPI backend for web UI."""

from contextlib import asynccontextmanager
from typing: Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
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
        return []

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
        # Placeholder
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

    # Serve static files (UI)
    try:
        app.mount("/static", StaticFiles(directory="src/wallexbot/ui/static"), name="static")
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
                <p><a href="/static/index.html">UI</a></p>
            </body>
        </html>
        """)

    return app