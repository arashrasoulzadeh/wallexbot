"""`wallexbot review`: the recent runs in one table, with honest caveats."""

import asyncio

from tests.unit.engine.test_engine import ScriptedFeed, make_engine
from wallexbot.cli.main import main
from wallexbot.storage.repository import SQLiteRepository

PATH = ["100", "97", "100.5", "95", "99", "102", "98", "101"]


def make_db(tmp_path, runs=2):
    path = str(tmp_path / "runs.db")
    repo = SQLiteRepository(path)

    async def go():
        for _ in range(runs):
            engine, _, _ = make_engine(
                ScriptedFeed(PATH), repository=repo, cancel_on_shutdown=False
            )
            await engine.run()

    asyncio.run(go())
    repo.close()
    return path


def test_review_lists_runs_totals_and_says_the_evidence_is_thin(tmp_path, capsys):
    db = make_db(tmp_path)
    assert main(["review", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "USDTTMN" in out and "Total" in out
    assert "beat simply holding" in out
    assert "too short" in out.lower() and "cycles" in out.lower()  # the two caveats


def test_review_of_an_empty_period_says_so(tmp_path, capsys):
    db = make_db(tmp_path, runs=0)
    assert main(["review", "--db", db, "--days", "3"]) == 0
    assert "No runs" in capsys.readouterr().out


def test_review_needs_an_existing_database(tmp_path, capsys):
    assert main(["review", "--db", str(tmp_path / "missing.db")]) == 1
    assert "not found" in capsys.readouterr().out.lower()
