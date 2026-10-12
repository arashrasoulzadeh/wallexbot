"""The web API driving real paper runs and backtests (fake Wallex client and price feed)."""

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.helpers.wallex_fakes import FakeClient
from tests.unit.api.test_manager import HoldingFeed
from wallexbot.api.app import create_app
from wallexbot.api.manager import RunManager
from wallexbot.storage.repository import InMemoryRepository

EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"


def config_dict() -> dict:
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def client():
    repo = InMemoryRepository()
    manager = RunManager(
        repo,
        client_factory=lambda: FakeClient(),
        feed_factory=lambda kind, symbol, c: HoldingFeed([264000, 262500, 265500]),
    )
    with TestClient(create_app(repo=repo, engine_manager=manager, stream_interval=0.05)) as c:
        yield c


def wait_for(fn, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("condition not reached in time")


def start_run(client) -> str:
    r = client.post("/api/paper-runs", json={"config": config_dict()})
    assert r.status_code == 200, r.text
    run_id = r.json()["id"]
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json()["status"]["ticks_processed"] == 3)
    return run_id


def test_a_started_paper_run_shows_up_with_live_data(client):
    run_id = start_run(client)

    run = client.get(f"/api/runs/{run_id}").json()
    assert run["id"] == run_id and run["status"]["state"] == "running"
    assert run["status"]["fills"] >= 1

    listed = client.get("/api/runs").json()
    [row] = [r for r in listed if r["id"] == run_id]
    assert row["status"] == "running" and row["market"] == "USDTTMN" and row["mode"] == "paper"

    orders = client.get(f"/api/runs/{run_id}/orders").json()
    assert orders and {"level", "side", "price", "quantity"} <= set(orders[0])
    assert client.get(f"/api/runs/{run_id}/fills").json()[0]["side"] in ("BUY", "SELL")
    pnl = client.get(f"/api/runs/{run_id}/pnl").json()
    assert set(pnl) >= {"realized", "unrealized", "total", "fees"}
    grid = client.get(f"/api/runs/{run_id}/grid").json()
    assert len(grid["levels"]) == 6 and grid["lower"] == "261000"


def test_pause_resume_stop_through_the_api(client):
    run_id = start_run(client)

    assert client.post(f"/api/runs/{run_id}/pause").json() == {"status": "paused"}
    assert client.get(f"/api/runs/{run_id}").json()["status"]["state"] == "paused"
    assert client.post(f"/api/runs/{run_id}/pause").status_code == 409  # already paused
    assert client.post(f"/api/runs/{run_id}/resume").json() == {"status": "running"}
    assert client.post(f"/api/runs/{run_id}/stop").json() == {"status": "stopped"}

    final = client.get(f"/api/runs/{run_id}").json()
    assert final["status"]["state"] == "stopped"
    assert client.get(f"/api/runs/{run_id}/orders").json() == []
    assert client.post(f"/api/runs/{run_id}/stop").status_code == 409


def test_kill_switch_through_the_api(client):
    run_id = start_run(client)
    assert client.post(f"/api/runs/{run_id}/kill").json() == {"status": "killed"}
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"]["state"] == "halted" and "kill" in run["status"]["halt_reason"].lower()
    assert client.get(f"/api/runs/{run_id}/orders").json() == []


def test_unknown_runs_are_404(client):
    for path in ("/api/runs/nope", "/api/runs/nope/orders", "/api/runs/nope/pnl"):
        assert client.get(path).status_code == 404
    for action in ("pause", "resume", "stop", "kill"):
        assert client.post(f"/api/runs/nope/{action}").status_code == 404


def test_an_unknown_market_is_a_422_with_the_reason(client):
    cfg = config_dict()
    cfg["market"]["symbol"] = "NOPEUSDT"
    r = client.post("/api/paper-runs", json={"config": cfg})
    assert r.status_code == 422 and "NOPEUSDT" in str(r.json())


def test_a_backtest_can_be_started_and_polled(client):
    r = client.post(
        "/api/backtests",
        json={"config": config_dict(), "from_ts": 1_700_000_000, "to_ts": 1_700_200_000},
    )
    assert r.status_code == 200
    bt_id = r.json()["id"]

    result = wait_for(
        lambda: (j := client.get(f"/api/backtests/{bt_id}").json())["status"] != "running" and j
    )
    assert result["status"] == "done"
    assert result["metrics"]["completed_cycles"] > 0
    assert client.get("/api/backtests/nope").status_code == 404


def test_the_stream_pushes_live_snapshots(client):
    run_id = start_run(client)
    with client.websocket_connect(f"/api/stream?run_id={run_id}") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot"
        assert first["run"]["status"]["ticks_processed"] == 3
        assert first["run"]["orders"] and first["run"]["balances"]
        second = ws.receive_json()  # keeps coming
        assert second["type"] == "snapshot"


def test_the_stream_refuses_unknown_runs(client):
    with client.websocket_connect("/api/stream?run_id=nope") as ws:
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        assert info.value.code == 4404


def test_the_stream_ends_after_the_final_snapshot_of_a_finished_run(client):
    run_id = start_run(client)
    client.post(f"/api/runs/{run_id}/stop")
    with client.websocket_connect(f"/api/stream?run_id={run_id}") as ws:
        msg = ws.receive_json()
        assert msg["run"]["status"]["state"] == "stopped" and msg["final"] is True
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_the_default_config_is_valid_and_for_the_example_market(client):
    cfg = client.get("/api/config/default").json()
    assert cfg["market"]["symbol"] == "USDTTMN"
    assert client.post("/api/config/validate", json=cfg).json()["valid"] is True
    assert "api_key" not in str(cfg).lower()


def test_validation_explains_why_a_grid_is_rejected(client):
    cfg = client.get("/api/config/default").json()
    cfg["strategy"]["grid"]["grid_count"] = 60
    cfg["strategy"]["grid"]["total_investment"] = "9000000"
    body = client.post("/api/config/validate", json=cfg).json()
    assert body["valid"] is False and "break-even" in body["errors"][0]


def test_notification_test_does_not_pretend_to_send(client):
    body = client.post("/api/notify/test", json={"message": "hi"}).json()
    assert "not configured" in body["message"].lower()
