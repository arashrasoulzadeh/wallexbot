"""The Backtest page's two extra tools: three strategies side by side, and fee tiers."""

from fastapi.testclient import TestClient

from tests.helpers.wallex_fakes import FakeClient
from tests.unit.analytics.test_compare import path
from wallexbot.api.app import create_app
from wallexbot.api.manager import RunManager
from wallexbot.storage.repository import InMemoryRepository

WINDOW = {"from_ts": 1_700_000_000, "to_ts": 1_700_300_000, "resolution": "60"}


def make(candles=None, client_cls=FakeClient):
    repo = InMemoryRepository()
    manager = RunManager(repo, client_factory=lambda: client_cls(candles=candles))
    return TestClient(create_app(repo=repo, engine_manager=manager))


def config(c):
    return c.get("/api/config/default").json()


def test_compare_returns_the_three_strategies(monkeypatch):
    with make(path()) as c:
        body = c.post(
            "/api/backtests/compare",
            json={"config": config(c), **WINDOW, "recenter_after_minutes": 120},
        ).json()
    assert [r["label"] for r in body["rows"]] == ["static", "recentering", "buy_and_hold"]
    static, moving, hold = body["rows"]
    assert static["recenters"] == 0 and moving["recenters"] >= 1 and hold["cycles"] == 0
    assert body["candles"] == len(path()) and body["recenter_after_minutes"] == 120


def test_fees_returns_a_row_per_tier_and_the_break_even():
    with make() as c:
        body = c.post(
            "/api/backtests/fees", json={"config": config(c), **WINDOW, "fees": ["0.001", "0.0035"]}
        ).json()
    assert [r["fee"] for r in body["rows"]] == ["0.001", "0.0035"]
    assert all(r["clears_break_even"] for r in body["rows"])
    assert 0.006 < float(body["break_even_fee"]) < 0.0065  # the example grid: 0.63 %


def test_fees_defaults_to_the_standard_tiers():
    with make() as c:
        body = c.post("/api/backtests/fees", json={"config": config(c), **WINDOW}).json()
    assert [r["fee"] for r in body["rows"]] == ["0.0005", "0.001", "0.002", "0.0035"]


def test_bad_requests_are_explained_not_crashed():
    with make() as c:
        cfg = config(c)
        backwards = {"from_ts": 200, "to_ts": 100, "resolution": "60"}
        assert (
            c.post("/api/backtests/compare", json={"config": cfg, **backwards}).status_code == 422
        )
        r = c.post("/api/backtests/fees", json={"config": cfg, **WINDOW, "fees": ["abc"]})
        assert r.status_code == 422 and "fee" in r.json()["detail"].lower()
        r = c.post("/api/backtests/fees", json={"config": cfg, **WINDOW, "fees": ["1.5"]})
        assert r.status_code == 422
        r = c.post(
            "/api/backtests/compare", json={"config": cfg, **WINDOW, "recenter_after_minutes": 0}
        )
        assert r.status_code == 422
        bad = {**cfg, "market": {"symbol": "NOPEUSDT"}}
        assert c.post("/api/backtests/fees", json={"config": bad, **WINDOW}).status_code == 422


def test_no_candles_for_the_period_is_a_422():
    with make(candles=[]) as c:
        r = c.post("/api/backtests/compare", json={"config": config(c), **WINDOW})
    assert r.status_code == 422 and "candle" in r.json()["detail"].lower()
