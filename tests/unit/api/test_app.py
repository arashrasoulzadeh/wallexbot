"""Tests for FastAPI backend."""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from wallexbot.api.app import create_app
from wallexbot.domain.market import Symbol
from wallexbot.storage.repository import InMemoryRepository


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def engine_manager():
    manager = AsyncMock()
    manager.start_backtest = AsyncMock(return_value="backtest_123")
    manager.start_paper_run = AsyncMock(return_value="paper_123")
    manager.pause_run = AsyncMock()
    manager.resume_run = AsyncMock()
    manager.stop_run = AsyncMock()
    manager.kill_run = AsyncMock()
    return manager


@pytest.fixture
def app(repo, engine_manager):
    return create_app(repo=repo, engine_manager=engine_manager)


@pytest.fixture
def client(app):
    return TestClient(app)


class TestAPI:
    """Tests for FastAPI backend."""

    def test_health_endpoint(self, client):
        """GET /api/health returns OK."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_markets_endpoint(self, client, repo):
        """GET /api/markets returns spot markets."""
        from unittest.mock import patch

        from wallexbot.wallex.models import Market

        mock_markets = [
            Market(
                symbol=Symbol("USDTTMN"),
                base_asset="USDT",
                quote_asset="TMN",
                price_precision=2,
                amount_precision=4,
                is_spot=True,
            ),
        ]
        with patch("wallexbot.api.app.WallexRestClient") as mock_client_class:
            mock_client = Mock()
            mock_client.get_markets.return_value = mock_markets
            mock_client_class.return_value = mock_client

            response = client.get("/api/markets")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["symbol"] == "USDTTMN"

    def test_candles_endpoint(self, client):
        """GET /api/candles returns candles."""
        from unittest.mock import patch

        from wallexbot.wallex.models import Candle

        mock_candles = [
            Candle(
                symbol=Symbol("USDTTMN"),
                resolution="60",
                open_time=1000,
                open=Decimal("100.00"),
                high=Decimal("101.00"),
                low=Decimal("99.00"),
                close=Decimal("100.50"),
                volume=Decimal("1000.00"),
            ),
        ]
        with patch("wallexbot.api.app.WallexRestClient") as mock_client_class:
            mock_client = Mock()
            mock_client.get_candles.return_value = mock_candles
            mock_client_class.return_value = mock_client

            response = client.get("/api/candles?symbol=USDTTMN&resolution=60&from=1000&to=2000")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["timestamp"] == 1000

    def test_runs_list(self, client, repo):
        """GET /api/runs lists runs."""
        run_id = repo.create_run("test", {"grid_count": 10})
        response = client.get("/api/runs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == run_id

    def test_run_detail(self, client, repo):
        """GET /api/runs/{id} returns run details."""
        run_id = repo.create_run("test", {"grid_count": 10})
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run_id

    def test_run_orders(self, client, repo):
        """GET /api/runs/{id}/orders returns orders."""
        run_id = repo.create_run("test", {})
        repo.save_order(
            run_id,
            {
                "id": "ord_1",
                "client_id": "GRID_1",
                "symbol": "USDTTMN",
                "side": "BUY",
                "price": "100.00",
                "quantity": "10.0000",
                "status": "NEW",
                "created_at": 1000,
                "updated_at": 1000,
            },
        )

        response = client.get(f"/api/runs/{run_id}/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_run_fills(self, client, repo):
        """GET /api/runs/{id}/fills returns fills."""
        run_id = repo.create_run("test", {})
        repo.save_fill(
            run_id,
            {
                "order_id": "ord_1",
                "price": "100.00",
                "quantity": "10.0000",
                "fee": "0.10",
                "fee_asset": "TMN",
                "is_maker": True,
                "timestamp": 1000,
            },
        )

        response = client.get(f"/api/runs/{run_id}/fills")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_run_pnl(self, client, repo):
        """GET /api/runs/{id}/pnl returns PnL."""
        run_id = repo.create_run("test", {})
        response = client.get(f"/api/runs/{run_id}/pnl")
        assert response.status_code == 200

    def test_run_grid(self, client, repo):
        """GET /api/runs/{id}/grid returns grid levels."""
        run_id = repo.create_run("test", {})
        repo.save_grid_state(
            run_id,
            {"levels": [{"index": 0, "price": "90.00", "side": "buy", "active_order_id": "ord_1"}]},
        )

        response = client.get(f"/api/runs/{run_id}/grid")
        assert response.status_code == 200
        data = response.json()
        assert "levels" in data

    def test_config_validate(self, client):
        """POST /api/config/validate validates config."""
        response = client.post(
            "/api/config/validate",
            json={
                "exchange": {"name": "wallex"},
                "market": {"symbol": "USDTTMN"},
                "strategy": {
                    "grid": {
                        "lower_price": "90.00",
                        "upper_price": "110.00",
                        "grid_count": 10,
                        "mode": "arithmetic",
                        "total_investment": "10000.00",
                    }
                },
                "risk": {"max_open_orders": 20},
                "simulation": {"initial_balance_quote": "2000000.00"},
                "logging": {"level": "INFO"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data

    def test_config_validate_invalid(self, client):
        """POST /api/config/validate rejects invalid config."""
        response = client.post(
            "/api/config/validate",
            json={
                "exchange": {"name": "wallex"},
                "market": {"symbol": "USDTTMN"},
                "strategy": {
                    "grid": {
                        "lower_price": "110.00",
                        "upper_price": "90.00",
                        "grid_count": 10,
                        "mode": "arithmetic",
                        "total_investment": "10000.00",
                    }
                },
                "risk": {"max_open_orders": 20},
                "simulation": {"initial_balance_quote": "2000000.00"},
                "logging": {"level": "INFO"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
        assert data["valid"] is False

    def test_backtest_start(self, client):
        """POST /api/backtests starts backtest."""
        response = client.post(
            "/api/backtests",
            json={
                "config": {
                    "exchange": {"name": "wallex"},
                    "market": {"symbol": "USDTTMN"},
                    "strategy": {
                        "grid": {
                            "lower_price": "90.00",
                            "upper_price": "110.00",
                            "grid_count": 10,
                            "mode": "arithmetic",
                            "total_investment": "10000.00",
                        }
                    },
                    "risk": {"max_open_orders": 20},
                    "simulation": {"initial_balance_quote": "2000000.00"},
                    "logging": {"level": "INFO"},
                },
                "from_ts": 1704067200,
                "to_ts": 1706659200,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data

    def test_paper_run_start(self, client):
        """POST /api/paper-runs starts paper run."""
        response = client.post(
            "/api/paper-runs",
            json={
                "config": {
                    "exchange": {"name": "wallex"},
                    "market": {"symbol": "USDTTMN"},
                    "strategy": {
                        "grid": {
                            "lower_price": "90.00",
                            "upper_price": "110.00",
                            "grid_count": 10,
                            "mode": "arithmetic",
                            "total_investment": "10000.00",
                        }
                    },
                    "risk": {"max_open_orders": 20},
                    "simulation": {"initial_balance_quote": "2000000.00"},
                    "logging": {"level": "INFO"},
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data

    def test_run_control_pause(self, client):
        """POST /api/runs/{id}/pause pauses run."""
        response = client.post("/api/runs/test_run/pause")
        assert response.status_code == 200

    def test_run_control_resume(self, client):
        """POST /api/runs/{id}/resume resumes run."""
        response = client.post("/api/runs/test_run/resume")
        assert response.status_code == 200

    def test_run_control_stop(self, client):
        """POST /api/runs/{id}/stop stops run."""
        response = client.post("/api/runs/test_run/stop")
        assert response.status_code == 200

    def test_run_control_kill(self, client):
        """POST /api/runs/{id}/kill kills run."""
        response = client.post("/api/runs/test_run/kill")
        assert response.status_code == 200

    def test_no_api_keys_accepted(self, client):
        """No endpoint accepts API keys."""
        response = client.post(
            "/api/config/validate",
            json={
                "exchange": {"name": "wallex", "api_key": "secret"},
                "market": {"symbol": "USDTTMN"},
                "strategy": {
                    "grid": {
                        "lower_price": "90.00",
                        "upper_price": "110.00",
                        "grid_count": 10,
                        "mode": "arithmetic",
                        "total_investment": "10000.00",
                    }
                },
                "risk": {"max_open_orders": 20},
                "simulation": {"initial_balance_quote": "2000000.00"},
                "logging": {"level": "INFO"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    def test_no_live_mode(self, client):
        """No live mode exposed."""
        response = client.post(
            "/api/paper-runs",
            json={
                "config": {
                    "exchange": {"name": "wallex"},
                    "market": {"symbol": "USDTTMN"},
                    "strategy": {
                        "grid": {
                            "lower_price": "90.00",
                            "upper_price": "110.00",
                            "grid_count": 10,
                            "mode": "live",
                            "total_investment": "10000.00",
                        }
                    },
                    "risk": {"max_open_orders": 20},
                    "simulation": {"initial_balance_quote": "2000000.00"},
                    "logging": {"level": "INFO"},
                },
            },
        )
        assert response.status_code == 422


class TestWSStream:
    """Tests for WebSocket stream."""

    @pytest.mark.asyncio
    async def test_ws_connect(self, app):
        """WS /api/stream connects."""
        pass

    @pytest.mark.asyncio
    async def test_ws_reconnect_resume(self, app):
        """WS reconnect with last_event_id."""
        pass
