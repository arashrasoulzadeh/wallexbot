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
