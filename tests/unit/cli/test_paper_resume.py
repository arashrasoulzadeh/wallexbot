"""`wallexbot paper --resume`: continue a run that a crash left unfinished."""

import asyncio
import importlib
import shutil
from pathlib import Path

import pytest

from tests.helpers.wallex_fakes import FakeClient
from tests.unit.test_recover import Feed, app_config
from wallexbot.cli.main import main
from wallexbot.config.schema import validate_config
from wallexbot.engine import BotEngine, EngineConfig
from wallexbot.setup import GridSetup, find_market
from wallexbot.storage.repository import SQLiteRepository

cli = importlib.import_module("wallexbot.cli.main")
T0 = 1_700_000_000_000
PRICES = [264000, 262500, 265500, 262000]


def make_crashed_db(path: Path, runs: int = 1) -> list[str]:
    """Run a paper engine on a SQLite file and 'crash' it: the file is copied while the run is
    still marked running, which is all a killed process leaves behind."""
    ids = []

    async def one(db_file: Path, crashed_copy: Path) -> str:
        repo = SQLiteRepository(str(db_file))
        setup = GridSetup.from_config(
            validate_config(app_config()), find_market(FakeClient(), "USDTTMN")
        )
        hold = asyncio.Event()
        engine = BotEngine(
            EngineConfig(
                strategy=setup.new_strategy(),
                exchange=setup.new_exchange(),
                price_feed=Feed(PRICES, T0, hold),
                risk=setup.risk,
                repository=repo,
                app_config=app_config(),
                cancel_on_shutdown=False,
            )
        )
        task = engine.start()
        for _ in range(500):
            await asyncio.sleep(0)
            if engine.status().ticks_processed == len(PRICES):
                break
        shutil.copy2(db_file, crashed_copy)  # the "crashed" file
        await engine.stop()
        await asyncio.gather(task, return_exceptions=True)
        return engine.run_id

    scratch = path.parent / "scratch.db"
    ids.append(asyncio.run(one(scratch, path)))
    for _ in range(runs - 1):  # more crashed runs in the same file
        extra = path.parent / "extra.db"
        extra_id = asyncio.run(one(extra, path.parent / "extra_crashed.db"))
        import sqlite3

        with sqlite3.connect(path) as dst, sqlite3.connect(path.parent / "extra_crashed.db") as src:
            for table in ("runs", "checkpoints"):
                rows = src.execute(f"SELECT * FROM {table}").fetchall()
                for row in rows:
                    marks = ",".join("?" * len(row))
                    dst.execute(f"INSERT OR IGNORE INTO {table} VALUES ({marks})", row)
        ids.append(extra_id)
    return ids


@pytest.fixture
def resume(monkeypatch, capsys):
    def _run(*args: str, prices=(262400, 262600)) -> tuple[int, str]:
        monkeypatch.setattr(cli, "make_rest_client", lambda: FakeClient())
        monkeypatch.setattr(
            cli, "make_price_feed", lambda kind, sym, c: Feed(list(prices), T0 + 10**9)
        )
        code = main(["paper", *args])
        return code, capsys.readouterr().out

    return _run


def test_the_latest_interrupted_run_is_resumed(tmp_path, resume):
    db = tmp_path / "runs.db"
    [run_id] = make_crashed_db(db)

    code, out = resume("--resume", "--db", str(db))

    assert code == 0
    assert f"Recovering run {run_id}" in out
    assert "Paper trading USDTTMN" in out and "stopped" in out.lower()
    repo = SQLiteRepository(str(db))
    assert repo.get_run(run_id)["status"] == "stopped"  # it ended cleanly this time
    assert any("recovered" in e["message"] for e in repo.get_events(run_id))
    assert len(repo.list_runs()) == 1  # the same run, not a new one


def test_a_run_can_be_named(tmp_path, resume):
    db = tmp_path / "runs.db"
    [run_id] = make_crashed_db(db)
    code, out = resume("--resume", run_id, "--db", str(db))
    assert code == 0 and f"Recovering run {run_id}" in out


def test_resume_needs_a_database(resume):
    code, out = resume("--resume")
    assert code == 1 and "--db" in out


def test_nothing_to_recover(tmp_path, resume):
    SQLiteRepository(str(tmp_path / "empty.db")).close()
    code, out = resume("--resume", "--db", str(tmp_path / "empty.db"))
    assert code == 1 and "nothing to recover" in out.lower()


def test_several_interrupted_runs_need_a_choice(tmp_path, resume):
    db = tmp_path / "runs.db"
    ids = make_crashed_db(db, runs=2)
    code, out = resume("--resume", "--db", str(db))
    assert code == 1 and "--resume RUN_ID" in out
    assert all(i in out for i in ids)


def test_a_finished_run_cannot_be_resumed(tmp_path, resume):
    db = tmp_path / "runs.db"
    [run_id] = make_crashed_db(db)
    repo = SQLiteRepository(str(db))
    repo.update_run_status(run_id, "stopped", 1)
    repo.close()
    code, out = resume("--resume", run_id, "--db", str(db))
    assert code == 1 and "stopped" in out


def test_a_config_file_is_required_without_resume(resume):
    code, out = resume()
    assert code == 1 and "config" in out.lower()
