"""Checkpoints: the saved state a crashed run is recovered from."""

import sqlite3

import pytest

from wallexbot.storage.repository import InMemoryRepository, SQLiteRepository

STATE = {"version": 1, "price": "264000.50", "orders": [{"id": "ord_1", "side": "BUY"}], "n": 7}


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        return InMemoryRepository()
    return SQLiteRepository(str(tmp_path / "runs.db"))


def make_run(repo) -> str:
    return repo.create_run("paper-USDTTMN", {"market": "USDTTMN", "mode": "paper"})


def test_a_checkpoint_round_trips(repo):
    run_id = make_run(repo)
    repo.save_checkpoint(run_id, STATE)
    assert repo.get_checkpoint(run_id) == STATE


def test_saving_again_replaces_the_previous_checkpoint(repo):
    run_id = make_run(repo)
    repo.save_checkpoint(run_id, STATE)
    repo.save_checkpoint(run_id, {**STATE, "n": 8})
    assert repo.get_checkpoint(run_id)["n"] == 8


def test_a_run_without_a_checkpoint_returns_none(repo):
    assert repo.get_checkpoint(make_run(repo)) is None
    assert repo.get_checkpoint("nope") is None


def test_checkpoints_are_kept_per_run(repo):
    a, b = make_run(repo), repo.create_run("other", {"market": "BTCUSDT"})
    repo.save_checkpoint(a, {"who": "a"})
    repo.save_checkpoint(b, {"who": "b"})
    assert repo.get_checkpoint(a) == {"who": "a"} and repo.get_checkpoint(b) == {"who": "b"}


def test_a_checkpoint_survives_reopening_the_database(tmp_path):
    path = str(tmp_path / "runs.db")
    first = SQLiteRepository(path)
    run_id = make_run(first)
    first.save_checkpoint(run_id, STATE)
    first.close()

    assert SQLiteRepository(path).get_checkpoint(run_id) == STATE


def test_a_database_created_before_checkpoints_is_upgraded(tmp_path):
    path = str(tmp_path / "old.db")
    repo = SQLiteRepository(path)
    run_id = make_run(repo)
    repo.close()
    with sqlite3.connect(path) as conn:  # make it look like a database from before this feature
        conn.execute("DROP TABLE checkpoints")
        conn.execute(
            "DELETE FROM schema_migrations WHERE version = (SELECT MAX(version) FROM schema_migrations)"
        )

    upgraded = SQLiteRepository(path)
    upgraded.save_checkpoint(run_id, STATE)
    assert upgraded.get_checkpoint(run_id) == STATE
    assert upgraded.get_run(run_id) is not None  # nothing else was lost
