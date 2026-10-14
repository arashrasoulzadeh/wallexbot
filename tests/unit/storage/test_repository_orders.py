"""Order and grid-state storage behaves the same in memory and in SQLite."""

import pytest

from wallexbot.storage.repository import InMemoryRepository, SQLiteRepository


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        return InMemoryRepository()
    return SQLiteRepository(str(tmp_path / "o.db"))


def order(client_id, status="NEW", **extra):
    return {
        "id": f"id-{client_id}",
        "client_id": client_id,
        "symbol": "USDTTMN",
        "side": "BUY",
        "type": "LIMIT",
        "price": "100",
        "quantity": "1",
        "status": status,
        "created_at": 1,
        "updated_at": 1,
        **extra,
    }


def test_an_order_is_found_by_id_and_by_client_id(repo):
    run = repo.create_run("r", {})
    repo.save_order(run, order("c1"))
    assert repo.get_order(run, "id-c1")["client_id"] == "c1"
    assert repo.get_order_by_client_id(run, "c1")["id"] == "id-c1"
    assert repo.get_order(run, "nope") is None
    assert repo.get_order_by_client_id(run, "nope") is None


def test_orders_of_another_run_are_not_visible(repo):
    a, b = repo.create_run("a", {}), repo.create_run("b", {})
    repo.save_order(a, order("c1"))
    assert repo.get_order(b, "id-c1") is None
    assert repo.get_order_by_client_id(b, "c1") is None
    assert repo.get_open_orders(b) == []


def test_updating_an_order_changes_its_status_and_open_list(repo):
    run = repo.create_run("r", {})
    repo.save_order(run, order("c1"))
    repo.save_order(run, order("c2", status="PARTIALLY_FILLED"))
    repo.save_order(run, order("c3", status="FILLED"))
    assert {o["client_id"] for o in repo.get_open_orders(run)} == {"c1", "c2"}
    repo.update_order("id-c1", {"status": "CANCELED", "updated_at": 5})
    assert repo.get_order(run, "id-c1")["status"] == "CANCELED"
    assert {o["client_id"] for o in repo.get_open_orders(run)} == {"c2"}


def test_fills_come_back_with_the_side_of_their_order_and_can_be_filtered(repo):
    run = repo.create_run("r", {})
    repo.save_order(run, order("c1"))
    repo.save_order(run, order("c2", side="SELL"))
    for i, oid in enumerate(("id-c1", "id-c2")):
        repo.save_fill(
            run,
            {
                "order_id": oid,
                "price": "100",
                "quantity": "1",
                "fee": "0.1",
                "fee_asset": "TMN",
                "is_maker": True,
                "timestamp": 10 + i,
            },
        )
    assert [f["side"] for f in repo.get_fills(run)] == ["BUY", "SELL"]
    only = repo.get_fills(run, order_id="id-c2")
    assert len(only) == 1 and only[0]["side"] == "SELL"


def test_grid_state_round_trips_and_is_empty_for_unknown_runs(repo):
    run = repo.create_run("r", {})
    assert repo.get_grid_state(run) is None
    repo.save_grid_state(run, {"levels": [{"index": 0, "price": "99"}]})
    state = repo.get_grid_state(run)
    assert state["levels"] == [{"index": 0, "price": "99"}] and state["updated_at"] > 0
    repo.save_grid_state(run, {"levels": []})
    assert repo.get_grid_state(run)["levels"] == []


def test_runs_started_together_with_the_same_config_get_different_ids(repo):
    ids = {repo.create_run("r", {"market": "USDTTMN"}) for _ in range(50)}
    assert len(ids) == 50
