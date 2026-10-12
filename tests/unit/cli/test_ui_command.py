"""`wallexbot ui`: serves the dashboard on this machine only, unless told otherwise."""

import importlib

import pytest

from wallexbot.cli.main import main
from wallexbot.storage.repository import InMemoryRepository, SQLiteRepository

cli = importlib.import_module("wallexbot.cli.main")


@pytest.fixture
def served(monkeypatch):
    calls = []

    def fake_run(app, host, port, **kwargs):
        calls.append({"app": app, "host": host, "port": port})

    monkeypatch.setattr("uvicorn.run", fake_run)
    return calls


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_local_addresses_are_served(served, host):
    assert main(["ui", "--host", host, "--port", "9001"]) == 0
    assert served[0]["host"] == host and served[0]["port"] == 9001


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com"])
def test_other_addresses_are_refused_without_the_flag(served, capsys, host):
    """The dashboard has no login and can start runs, so it must not be reachable by default."""
    assert main(["ui", "--host", host]) == 1
    assert served == []
    out = capsys.readouterr().out
    assert "--allow-remote" in out and "no login" in out.lower()


def test_remote_access_needs_an_explicit_flag_and_warns(served, capsys):
    assert main(["ui", "--host", "0.0.0.0", "--allow-remote"]) == 0
    assert served[0]["host"] == "0.0.0.0"
    assert "anyone who can reach" in capsys.readouterr().out.lower()


def test_runs_are_kept_in_memory_unless_a_database_is_given(served):
    main(["ui"])
    assert isinstance(served[0]["app"].state.repo, InMemoryRepository)


def test_a_database_makes_runs_survive_restarts(served, tmp_path):
    main(["ui", "--db", str(tmp_path / "ui.db")])
    assert isinstance(served[0]["app"].state.repo, SQLiteRepository)
