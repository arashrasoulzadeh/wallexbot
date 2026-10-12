"""Week overview of a coin from hourly candles: how far and how fast it moved."""

from decimal import Decimal as D

from tests.helpers.wallex_fakes import swinging_candles
from wallexbot.analytics.week_stats import week_stats


def test_no_candles_means_no_overview():
    assert week_stats([], D("100")) is None


def test_week_range_and_hourly_movement():
    stats = week_stats(swinging_candles(40), D("264000"))
    assert stats is not None
    assert stats["hours"] == 40
    assert stats["high"] == D("265500") and stats["low"] == D("262500")
    # (265500 - 262500) / 262500 = 1.142857 %
    assert abs(stats["range_pct"] - D("1.1429")) < D("0.001")
    # every hourly bar spans 262500..265500 -> about 1.13 % of its open
    assert D("1.1") < stats["avg_hour_range_pct"] < D("1.15")
    assert stats["max_hour_range_pct"] >= stats["avg_hour_range_pct"]
    assert D("49") < stats["position_pct"] < D("51")  # 264000 is halfway up the week's range


def test_position_is_clamped_when_price_is_outside_the_week():
    assert week_stats(swinging_candles(4), D("999999"))["position_pct"] == D("100")
    assert week_stats(swinging_candles(4), D("1"))["position_pct"] == D("0")
