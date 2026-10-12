"""The History API: past runs, their curves, daily results, trades and CSV downloads."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal as D
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from wallexbot.api.app import create_app
from wallexbot.api.manager import RunManager
from wallexbot.storage.repository import InMemoryRepository


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp() * 1000)


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def client(repo):
    manager = Mock(spec=RunManager)
    manager.snapshot.return_value = None
    manager.recoverable.return_value = []
    with TestClient(create_app(repo=repo, engine_manager=manager)) as c:
        yield c


def seed(repo, name="paper-USDTTMN", started="2026-10-10T10:00:00", status="stopped") -> str:
    run_id = repo.create_run(name, {"market": "USDTTMN", "mode": "paper"})
    repo._runs[run_id]["started_at"] = ms(started)
    repo._runs[run_id]["status"] = status
    repo._runs[run_id]["stopped_at"] = ms("2026-10-11T12:00:00")
    shots = [
        ("2026-10-10T10:00:00", 1000, 100, 0, 2, 0, 0),
        ("2026-10-10T15:00:00", 1010, 101, 8, 4, 3, 1),  # Tehran day 1
        ("2026-10-10T21:00:00", 1005, 99, 12, 6, 5, 2),  # Tehran day 2 (after 20:30Z)
        ("2026-10-11T12:00:00", 1030, 103, 25, 9, 9, 4),
    ]
    for t, eq, price, realized, fees, fills, cycles in shots:
        repo.save_snapshot(
            run_id,
            {
                "ts": ms(t),
                "price": str(price),
                "equity": str(eq),
                "realized": str(realized),
                "fees": str(fees),
                "open_orders": 6,
                "fills": fills,
                "cycles": cycles,
            },
        )
    for i, (t, side, price) in enumerate(
        [
            ("2026-10-10T11:00:00", "BUY", "100"),
            ("2026-10-10T14:00:00", "SELL", "101"),
            ("2026-10-10T22:00:00", "BUY", "99"),
        ]
    ):
        repo.save_order(
            run_id,
            {
                "id": f"{run_id}:o{i}",
                "client_id": f"c{i}",
                "symbol": "USDTTMN",
                "side": side,
                "type": "LIMIT",
                "price": price,
                "quantity": "2",
                "status": "FILLED",
                "filled_quantity": "2",
                "fee": "0",
                "fee_asset": "TMN",
                "is_maker": True,
                "level_index": i,
                "created_at": 1,
                "updated_at": 1,
            },
        )
        repo.save_fill(
            run_id,
            {
                "order_id": f"{run_id}:o{i}",
                "trade_id": f"t{i}",
                "price": price,
                "quantity": "2",
                "fee": "0.1",
                "fee_asset": "TMN",
                "is_maker": True,
                "timestamp": ms(t),
                "level_index": i,
            },
        )
    repo.save_event(run_id, {"type": "engine", "message": "engine started"})
    return run_id


def test_the_run_list_summarises_every_past_run_newest_first(client, repo):
    older = seed(repo, started="2026-10-01T10:00:00")
    newer = seed(repo, started="2026-10-10T10:00:00")

    rows = client.get("/api/history/runs").json()

    assert [r["id"] for r in rows] == [newer, older]
    top = rows[0]
    assert top["market"] == "USDTTMN" and top["status"] == "stopped"
    assert D(top["return_pct"]) == D(3) and top["cycles"] == 4 and top["fills"] == 3
    assert D(top["max_drawdown_pct"]) > 0


def test_a_run_has_summary_series_daily_trades_and_events(client, repo):
    run_id = seed(repo)
    body = client.get(f"/api/history/runs/{run_id}").json()

    assert body["summary"]["id"] == run_id and D(body["summary"]["realized"]) == 25
    assert [p["equity"] for p in body["series"]] == ["1000", "1010", "1005", "1030"]
    assert set(body["series"][0]) >= {"ts", "price", "equity", "realized"}
    assert [d["date"] for d in body["daily"]] == ["2026-10-10", "2026-10-11"]  # Tehran days
    assert D(body["daily"][0]["equity_change"]) == 10 and D(body["daily"][1]["equity_change"]) == 20
    assert [f["side"] for f in body["fills"]] == ["BUY", "SELL", "BUY"][::-1]  # newest first
    assert body["events"][0]["message"] == "engine started"
    assert body["tz"] == "Asia/Tehran"


def test_the_time_zone_decides_where_a_day_ends(client, repo):
    run_id = seed(repo)
    utc = client.get(f"/api/history/runs/{run_id}?tz=UTC").json()
    assert [d["date"] for d in utc["daily"]] == ["2026-10-10", "2026-10-11"]
    assert utc["daily"][0]["fills"] == 3  # all three fills happened on Oct 10 in UTC
    tehran = client.get(f"/api/history/runs/{run_id}?tz=Asia/Tehran").json()
    assert (
        tehran["daily"][0]["fills"] == 2 and tehran["daily"][1]["fills"] == 1
    )  # the 22:00Z one is day 2


def test_the_time_range_limits_everything_at_once(client, repo):
    run_id = seed(repo)
    since, until = ms("2026-10-10T12:00:00"), ms("2026-10-10T23:00:00")
    body = client.get(f"/api/history/runs/{run_id}?since={since}&until={until}").json()

    assert [p["equity"] for p in body["series"]] == ["1010", "1005"]
    assert [f["price"] for f in body["fills"]] == ["99", "101"]
    assert sum(d["fills"] for d in body["daily"]) == 2


def test_trades_can_be_filtered_by_side_and_limited(client, repo):
    run_id = seed(repo)
    buys = client.get(f"/api/history/runs/{run_id}?side=BUY").json()["fills"]
    assert {f["side"] for f in buys} == {"BUY"} and len(buys) == 2
    assert len(client.get(f"/api/history/runs/{run_id}?fills_limit=1").json()["fills"]) == 1


def test_long_histories_are_thinned_for_the_charts(client, repo):
    run_id = repo.create_run("r", {"market": "USDTTMN"})
    for i in range(2000):
        repo.save_snapshot(
            run_id,
            {
                "ts": 1_000_000 + i * 1000,
                "price": "1",
                "equity": str(1000 + i),
                "realized": "0",
                "fees": "0",
                "open_orders": 0,
                "fills": 0,
                "cycles": 0,
            },
        )
    body = client.get(f"/api/history/runs/{run_id}?max_points=100").json()
    assert len(body["series"]) <= 100
    assert body["series"][0]["equity"] == "1000" and body["series"][-1]["equity"] == "2999"
    assert (
        body["summary"]["max_drawdown_pct"] == "0"
    )  # summary uses ALL points, not the thinned ones


def test_bad_parameters_and_unknown_runs(client, repo):
    run_id = seed(repo)
    assert client.get("/api/history/runs/nope").status_code == 404
    assert client.get(f"/api/history/runs/{run_id}?max_points=0").status_code == 422
    assert client.get(f"/api/history/runs/{run_id}?tz=Mars/Base").status_code == 422
    assert client.get(f"/api/history/runs/{run_id}?side=HOLD").status_code == 422
    assert client.get("/api/history/runs/nope/fills.csv").status_code == 404


def test_trades_download_as_csv(client, repo):
    run_id = seed(repo)
    r = client.get(f"/api/history/runs/{run_id}/fills.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert (
        "attachment" in r.headers["content-disposition"]
        and ".csv" in r.headers["content-disposition"]
    )
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:3] == ["time_utc", "timestamp_ms", "side"] and len(rows) == 4
    assert [row[2] for row in rows[1:]] == ["BUY", "SELL", "BUY"]  # oldest first in a file


def test_the_price_and_equity_history_downloads_as_csv(client, repo):
    run_id = seed(repo)
    rows = list(
        csv.reader(io.StringIO(client.get(f"/api/history/runs/{run_id}/snapshots.csv").text))
    )
    assert rows[0][:4] == ["time_utc", "timestamp_ms", "price", "equity"] and len(rows) == 5
    since = ms("2026-10-10T20:00:00")
    ranged = list(
        csv.reader(
            io.StringIO(client.get(f"/api/history/runs/{run_id}/snapshots.csv?since={since}").text)
        )
    )
    assert len(ranged) == 3


# --- a real engine run shows up in History -------------------------------------------------

import time  # noqa: E402

from tests.helpers.wallex_fakes import FakeClient  # noqa: E402
from tests.unit.api.test_api_live import config_dict  # noqa: E402
from tests.unit.api.test_manager import HoldingFeed  # noqa: E402


def test_a_real_paper_run_appears_in_history_and_matches_its_own_status():
    repo = InMemoryRepository()
    manager = RunManager(
        repo,
        client_factory=lambda: FakeClient(),
        feed_factory=lambda k, s, c: HoldingFeed([264000, 262500, 265500, 262000]),
    )
    with TestClient(create_app(repo=repo, engine_manager=manager, stream_interval=0.05)) as c:
        run_id = c.post("/api/paper-runs", json={"config": config_dict()}).json()["id"]
        deadline = time.time() + 3
        while (
            time.time() < deadline
            and c.get(f"/api/runs/{run_id}").json()["status"]["ticks_processed"] < 4
        ):
            time.sleep(0.02)
        c.post(f"/api/runs/{run_id}/stop")

        live = c.get(f"/api/runs/{run_id}").json()["status"]
        history = c.get(f"/api/history/runs/{run_id}").json()

    s = history["summary"]
    assert history["series"] and history["fills"]
    assert s["cycles"] == live["completed_cycles"] and s["fills"] == live["fills"]
    assert D(s["fees"]) == D(live["fees_paid"]) and D(s["realized"]) == D(live["realized_pnl"])
    assert s["status"] == "stopped"
    last_equity = D(history["series"][-1]["equity"])
    assert last_equity == D(live["equity"])
