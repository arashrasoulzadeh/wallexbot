"""The analysis commands: suggest, optimize, regime (fake client, no network)."""

import time
from unittest.mock import patch

import pytest

from tests.helpers.wallex_fakes import FakeClient, swinging_candles
from wallexbot.cli.main import main


@pytest.fixture
def fake():
    client = FakeClient(candles=swinging_candles(60))
    with patch("wallexbot.wallex.client.WallexRestClient", return_value=client):
        yield client


def test_suggest_prints_a_range_a_spacing_and_a_decision(fake, capsys):
    assert main(["suggest", "--market", "USDTTMN", "--capital", "2000000"]) == 0
    out = capsys.readouterr().out
    assert "Range Suggestion" in out and "Spacing Suggestion" in out and "Run Decision" in out


def test_suggest_asks_for_recent_candles_not_timestamp_zero(fake):
    main(["suggest", "--market", "USDTTMN", "--capital", "2000000"])
    symbol, resolution, start, end = fake.requests[-1]
    assert abs(end - time.time()) < 60 and 13 * 86400 < end - start < 15 * 86400


def test_regime_names_the_market_state(fake, capsys):
    assert main(["regime", "--market", "USDTTMN", "--period", "20"]) == 0
    out = capsys.readouterr().out
    assert "Market Regime:" in out and "ATR" in out and "ADX" in out


def test_regime_asks_for_recent_candles_too(fake):
    main(["regime", "--market", "USDTTMN"])
    _, _, start, end = fake.requests[-1]
    assert end - start > 86400


def test_optimize_lists_the_best_parameter_sets(fake, capsys):
    assert (
        main(
            [
                "optimize",
                "--market",
                "USDTTMN",
                "--from",
                "1700000000",
                "--to",
                "1700200000",
                "--iterations",
                "3",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Top 5 Results" in out and "Score:" in out


@pytest.mark.parametrize(
    "argv",
    [
        ["suggest", "--market", "USDTTMN"],
        ["regime", "--market", "USDTTMN"],
        ["optimize", "--market", "USDTTMN", "--from", "1", "--to", "2"],
    ],
)
def test_no_candles_is_reported_not_crashed(argv, capsys):
    client = FakeClient(candles=[])
    with patch("wallexbot.wallex.client.WallexRestClient", return_value=client):
        assert main(argv) == 1
    assert "No candle data" in capsys.readouterr().out


def test_fees_command_shows_each_tier_and_the_break_even(monkeypatch, capsys):
    import importlib
    from pathlib import Path

    cli = importlib.import_module("wallexbot.cli.main")
    monkeypatch.setattr(cli, "make_rest_client", lambda: FakeClient(candles=swinging_candles(60)))
    example = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"
    code = main(["fees", str(example), "--from", "1700000000", "--to", "1700300000"])
    out = capsys.readouterr().out
    assert code == 0
    assert "0.05%" in out and "0.35%" in out  # the default tiers
    assert "Break-even fee" in out and "0.63%" in out


def test_fees_command_takes_its_own_list_and_rejects_nonsense(monkeypatch, capsys):
    import importlib
    from pathlib import Path

    cli = importlib.import_module("wallexbot.cli.main")
    monkeypatch.setattr(cli, "make_rest_client", lambda: FakeClient(candles=swinging_candles(60)))
    example = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"
    base = ["fees", str(example), "--from", "1700000000", "--to", "1700300000"]
    assert main([*base, "--fees", "0.001,0.0025"]) == 0
    out = capsys.readouterr().out
    assert "0.25%" in out and "0.35%" not in out
    assert main([*base, "--fees", "abc"]) == 1
    assert "Error" in capsys.readouterr().out
