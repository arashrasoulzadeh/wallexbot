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
        c.repo = repo  # type: ignore[attr-defined]
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
    assert not body["errors"][0].startswith("Value error")  # no framework jargon for the user


def test_notification_test_does_not_pretend_to_send(client):
    body = client.post("/api/notify/test", json={"message": "hi"}).json()
    assert "not configured" in body["message"].lower()


# --- crash recovery through the API ------------------------------------------------------

import asyncio  # noqa: E402

from tests.unit.test_recover import crashed_repo  # noqa: E402


@pytest.fixture
def recovery_client():
    disk, run_id = asyncio.run(crashed_repo())
    manager = RunManager(
        disk,
        client_factory=lambda: FakeClient(),
        feed_factory=lambda kind, symbol, c: HoldingFeed([262400, 262600]),
    )
    with TestClient(create_app(repo=disk, engine_manager=manager, stream_interval=0.05)) as c:
        c.run_id = run_id  # type: ignore[attr-defined]
        c.repo = disk  # type: ignore[attr-defined]
        yield c


def test_an_interrupted_run_is_listed_as_recoverable(recovery_client):
    [row] = recovery_client.get("/api/runs").json()
    assert row["id"] == recovery_client.run_id
    assert row["status"] == "running" and row["recoverable"] is True


def test_recovering_continues_the_same_run(recovery_client):
    run_id = recovery_client.run_id
    r = recovery_client.post(f"/api/runs/{run_id}/recover")
    assert r.status_code == 200 and r.json()["id"] == run_id

    run = wait_for(
        lambda: (
            (j := recovery_client.get(f"/api/runs/{run_id}").json())["status"]["ticks_processed"]
            >= 6
            and j
        )
    )
    assert run["status"]["state"] == "running"
    assert run["orders"] and run["grid"]["levels"]
    [row] = recovery_client.get("/api/runs").json()
    assert row["recoverable"] is False  # live in this process now
    assert len(recovery_client.get("/api/runs").json()) == 1  # no second run was created


def test_a_live_run_cannot_be_recovered_twice(recovery_client):
    run_id = recovery_client.run_id
    assert recovery_client.post(f"/api/runs/{run_id}/recover").status_code == 200
    assert recovery_client.post(f"/api/runs/{run_id}/recover").status_code == 409


def test_a_recovered_run_can_be_stopped_like_any_other(recovery_client):
    run_id = recovery_client.run_id
    recovery_client.post(f"/api/runs/{run_id}/recover")
    wait_for(
        lambda: recovery_client.get(f"/api/runs/{run_id}").json()["status"]["state"] == "running"
    )
    assert recovery_client.post(f"/api/runs/{run_id}/stop").json() == {"status": "stopped"}
    assert recovery_client.repo.get_run(run_id)["status"] == "stopped"
    assert recovery_client.post(f"/api/runs/{run_id}/recover").status_code == 409  # finished: no


def test_recovering_something_that_does_not_exist_or_is_finished(recovery_client):
    assert recovery_client.post("/api/runs/nope/recover").status_code == 404
    recovery_client.repo.update_run_status(recovery_client.run_id, "halted", 1)
    r = recovery_client.post(f"/api/runs/{recovery_client.run_id}/recover")
    assert r.status_code == 409 and "halted" in r.json()["detail"]


def test_a_started_run_saves_its_config_so_it_can_be_recovered_later(client):
    from wallexbot.config.schema import validate_config

    run_id = start_run(client)
    stored = client.repo.get_checkpoint(run_id)["app_config"]  # what recovery will read
    assert validate_config(stored).market.symbol == "USDTTMN"


# --- the public price, shown while a run waits for its first live trade ----------------------


def test_the_latest_public_price_is_available_without_a_run(client):
    r = client.get("/api/price/USDTTMN")
    assert r.status_code == 200
    body = r.json()
    assert body == {"symbol": "USDTTMN", "price": "262154", "timestamp": 1_700_000_123_000}


def test_no_recent_trades_is_a_404(repo=None):
    from wallexbot.storage.repository import InMemoryRepository

    empty = FakeClient()
    empty.trades = []
    manager = RunManager(
        InMemoryRepository(),
        client_factory=lambda: empty,
        feed_factory=lambda k, s, c: HoldingFeed([]),
    )
    with TestClient(create_app(repo=InMemoryRepository(), engine_manager=manager)) as c:
        assert c.get("/api/price/USDTTMN").status_code == 404


def test_a_failing_public_api_is_a_502_with_the_reason():
    from wallexbot.storage.repository import InMemoryRepository
    from wallexbot.wallex.client import WallexApiError

    class Broken(FakeClient):
        def get_latest_trades(self, symbol, limit=50):
            raise WallexApiError("HTTP 503 for /v1/trades")

    manager = RunManager(
        InMemoryRepository(),
        client_factory=lambda: Broken(),
        feed_factory=lambda k, s, c: HoldingFeed([]),
    )
    with TestClient(create_app(repo=InMemoryRepository(), engine_manager=manager)) as c:
        r = c.get("/api/price/USDTTMN")
        assert r.status_code == 502 and "503" in r.json()["detail"]


# --- the Market status page: facts, never a buy/sell verdict -----------------------------------

import json  # noqa: E402


def test_market_status_describes_the_price_the_grid_and_the_book(client):
    r = client.post("/api/market-status", json={"config": config_dict()})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["symbol"] == "USDTTMN" and body["price"] == "262154"
    grid = body["grid"]
    assert grid["state"] == "inside" and grid["levels"] == 6 and grid["lower"] == "261000"
    assert grid["next_buy"]["price"] == "261000" and grid["next_sell"]["price"] == "262200"
    assert body["depth"]["best_bid"] == "262100" and body["depth"]["best_ask"] == "262200"
    assert body["depth"]["bid_share_pct"] is not None
    assert body["trend"]["label"] in ("sideways", "up", "down", "unclear")
    assert {w["code"] for w in body["warnings"]} >= {"stale_price"}  # the fake trade is years old


def test_market_status_never_contains_a_recommendation(client):
    text = json.dumps(
        client.post("/api/market-status", json={"config": config_dict()}).json()
    ).lower()
    for word in ("recommend", "signal", "should_buy", "should_sell", "advice"):
        assert word not in text


def test_market_status_needs_a_valid_config_and_a_known_market(client):
    bad = config_dict()
    bad["strategy"]["grid"]["grid_count"] = 60
    bad["strategy"]["grid"]["total_investment"] = "9000000"
    assert client.post("/api/market-status", json={"config": bad}).status_code == 422
    unknown = config_dict()
    unknown["market"]["symbol"] = "NOPEUSDT"
    r = client.post("/api/market-status", json={"config": unknown})
    assert r.status_code == 422 and "NOPEUSDT" in str(r.json())


def test_market_status_reports_an_unreachable_wallex_as_502():
    from wallexbot.storage.repository import InMemoryRepository
    from wallexbot.wallex.client import WallexApiError

    class Down(FakeClient):
        def get_depth(self, symbol):
            raise WallexApiError("HTTP 503 for /v1/depth")

    repo = InMemoryRepository()
    manager = RunManager(
        repo, client_factory=lambda: Down(), feed_factory=lambda k, s, c: HoldingFeed([])
    )
    with TestClient(create_app(repo=repo, engine_manager=manager)) as c:
        r = c.post("/api/market-status", json={"config": config_dict()})
        assert r.status_code == 502 and "503" in r.json()["detail"]


# --- every Wallex coin: the market list, per-coin defaults, and runs started from them -----------

from decimal import Decimal as _D  # noqa: E402

from tests.helpers.wallex_fakes import real_markets  # noqa: E402
from wallexbot.wallex.price_feed import PriceTick  # noqa: E402


class _PriceFeed:
    """Three prices around a coin's own price, then idle."""

    def __init__(self, price, symbol):
        self.prices, self.symbol, self.closed = (
            [price, price * _D("0.995"), price * _D("1.004")],
            symbol,
            asyncio.Event(),
        )

    async def subscribe(self, symbol): ...
    async def unsubscribe(self, symbol): ...

    async def ticks(self):
        for i, p in enumerate(self.prices):
            yield PriceTick(
                symbol=self.symbol, price=p, timestamp=1_700_000_000_000 + i * 60_000, source="test"
            )
        await self.closed.wait()

    async def close(self):
        self.closed.set()


@pytest.fixture
def coins_client():
    markets = real_markets()
    by = {str(m.symbol): m for m in markets}
    repo = InMemoryRepository()
    manager = RunManager(
        repo,
        client_factory=lambda: FakeClient(markets=markets),
        feed_factory=lambda kind, symbol, c: _PriceFeed(by[str(symbol)].price, symbol),
    )
    with TestClient(create_app(repo=repo, engine_manager=manager, stream_interval=0.05)) as c:
        c.by = by  # type: ignore[attr-defined]
        yield c


def test_the_market_list_has_every_coin_biggest_first(coins_client):
    rows = coins_client.get("/api/markets").json()
    assert len(rows) == 373
    assert {r["quote"] for r in rows} == {"TMN", "USDT"}
    volumes = [_D(r["quote_volume_24h"]) for r in rows if r["quote_volume_24h"] is not None]
    assert volumes == sorted(volumes, reverse=True)
    first = rows[0]
    assert {
        "symbol",
        "base",
        "quote",
        "price",
        "change_24h_pct",
        "quote_volume_24h",
        "min_notional_hint",
        "price_precision",
        "amount_precision",
        "tradable",
    } <= set(first)
    assert any(not r["tradable"] for r in rows) and any(r["tradable"] for r in rows)
    json.dumps(rows)


def test_defaults_for_a_coin_come_with_a_validation_verdict(coins_client):
    body = coins_client.get("/api/markets/PEPEUSDT/defaults").json()
    assert body["symbol"] == "PEPEUSDT" and body["valid"] is True and body["errors"] == []
    assert body["config"]["market"]["symbol"] == "PEPEUSDT"
    assert coins_client.post("/api/config/validate", json=body["config"]).json()["valid"] is True


def test_defaults_for_unknown_or_inactive_markets_are_refused(coins_client):
    assert coins_client.get("/api/markets/NOPEUSDT/defaults").status_code == 404
    inactive = next(s for s, m in coins_client.by.items() if m.price is None)
    r = coins_client.get(f"/api/markets/{inactive}/defaults")
    assert r.status_code == 422 and "no price" in r.json()["detail"]


@pytest.mark.parametrize("symbol", ["USDTTMN", "PEPEUSDT", "BTCTMN"])
def test_a_paper_run_starts_and_trades_from_a_coins_defaults(coins_client, symbol):
    config = coins_client.get(f"/api/markets/{symbol}/defaults").json()["config"]
    run_id = coins_client.post("/api/paper-runs", json={"config": config}).json()["id"]
    run = wait_for(
        lambda: (
            (j := coins_client.get(f"/api/runs/{run_id}").json())["status"]["ticks_processed"] == 3
            and j
        )
    )
    assert run["market"] == symbol and run["status"]["state"] == "running"
    assert run["orders"] and run["status"]["rejected_orders"] == 0
    assert run["status"]["fills"] >= 1  # the -0.5% / +0.4% swings cross at least one level
    coins_client.post(f"/api/runs/{run_id}/stop")
