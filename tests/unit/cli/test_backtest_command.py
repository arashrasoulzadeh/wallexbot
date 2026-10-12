"""`wallexbot backtest` runs a real backtest on candles (the Wallex client is faked: no network)."""

import importlib
from pathlib import Path

import pytest

from tests.helpers.wallex_fakes import FakeClient
from wallexbot.cli.main import main

cli = importlib.import_module("wallexbot.cli.main")  # the package re-exports `main`, shadowing it

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "wallex"
EXAMPLE_CONFIG = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"


@pytest.fixture
def run_cli(monkeypatch, capsys):
    def _run(client: FakeClient, *args: str) -> tuple[int, str]:
        monkeypatch.setattr(cli, "make_rest_client", lambda: client)
        code = main(
            ["backtest", str(EXAMPLE_CONFIG), "--from", "2023-11-14", "--to", "2023-11-16", *args]
        )
        return code, capsys.readouterr().out

    return _run


def test_backtest_trades_and_prints_a_summary(run_cli):
    client = FakeClient()
    code, out = run_cli(client)

    assert code == 0
    assert "Backtest USDTTMN" in out
    assert "Completed cycles" in out and "Total return" in out and "Max drawdown" in out
    cycles = int(
        next(line for line in out.splitlines() if line.startswith("Completed cycles")).split()[-1]
    )
    assert cycles > 0  # it really traded
    assert client.requests[0][0:2] == ("USDTTMN", "60")


def test_backtest_writes_a_markdown_report(run_cli, tmp_path):
    report = tmp_path / "report.md"
    code, _ = run_cli(FakeClient(), "--output", str(report))

    assert code == 0
    text = report.read_text(encoding="utf-8")
    assert text.startswith("# Backtest USDTTMN")
    assert "| Completed cycles |" in text and "| Total return |" in text
    assert "Fee assumptions" in text  # placeholders are called out, not hidden


def test_unknown_market_is_an_error(run_cli):
    code, out = run_cli(FakeClient(markets=[]))
    assert code == 1 and "USDTTMN" in out and "not found" in out.lower()


def test_no_candles_is_an_error(run_cli):
    code, out = run_cli(FakeClient(candles=[]))
    assert code == 1 and "no candle data" in out.lower()


def test_invalid_config_is_an_error(monkeypatch, capsys, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("market:\n  symbol: USDTTMN\n")
    monkeypatch.setattr(cli, "make_rest_client", lambda: FakeClient())
    code = main(["backtest", str(bad), "--from", "2023-11-14", "--to", "2023-11-16"])
    assert code == 1 and "error" in capsys.readouterr().out.lower()


def test_from_must_be_before_to(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_rest_client", lambda: FakeClient())
    code = main(["backtest", str(EXAMPLE_CONFIG), "--from", "2023-11-16", "--to", "2023-11-14"])
    assert code == 1 and "before" in capsys.readouterr().out.lower()
