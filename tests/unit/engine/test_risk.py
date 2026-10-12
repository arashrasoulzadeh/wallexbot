"""Risk monitor: max drawdown from the peak and daily loss limit trip the kill switch."""

from datetime import UTC, datetime
from decimal import Decimal as D

from wallexbot.engine.risk import RiskMonitor


def ms(day: int, hour: int = 12) -> int:
    return int(datetime(2026, 10, day, hour, tzinfo=UTC).timestamp() * 1000)


def test_no_breach_while_inside_the_limits():
    monitor = RiskMonitor(max_drawdown=D("0.05"), daily_loss_limit=D("0.10"))
    assert monitor.update(D("1000"), ms(1)) is None
    assert monitor.update(D("1100"), ms(1)) is None  # new peak
    assert monitor.update(D("1060"), ms(1)) is None  # -3.6% from peak


def test_drawdown_from_the_peak_trips_the_monitor():
    monitor = RiskMonitor(max_drawdown=D("0.05"), daily_loss_limit=None)
    monitor.update(D("1000"), ms(1))
    monitor.update(D("1200"), ms(2))  # peak
    reason = monitor.update(D("1130"), ms(3))  # -5.83% from 1200
    assert reason is not None and "drawdown" in reason.lower()
    assert "5.83" in reason


def test_exactly_at_the_limit_is_not_a_breach():
    monitor = RiskMonitor(max_drawdown=D("0.05"), daily_loss_limit=None)
    monitor.update(D("1000"), ms(1))
    assert monitor.update(D("950"), ms(1)) is None


def test_daily_loss_is_measured_from_the_first_equity_of_the_utc_day():
    monitor = RiskMonitor(max_drawdown=None, daily_loss_limit=D("0.02"))
    monitor.update(D("1000"), ms(1, 1))
    assert monitor.update(D("985"), ms(1, 23)) is None  # -1.5%
    reason = monitor.update(D("975"), ms(1, 23))  # -2.5%
    assert reason is not None and "daily loss" in reason.lower()


def test_a_new_day_resets_the_daily_baseline_but_not_the_peak():
    monitor = RiskMonitor(max_drawdown=D("0.10"), daily_loss_limit=D("0.02"))
    monitor.update(D("1000"), ms(1))
    assert monitor.update(D("990"), ms(2, 0)) is None  # day 2 baseline = 990
    assert monitor.update(D("975"), ms(2, 6)) is None  # -1.5% on the day, -2.5% from peak
    assert monitor.update(D("965"), ms(2, 7)) is not None  # -2.5% on the day


def test_disabled_limits_never_trip():
    monitor = RiskMonitor(max_drawdown=None, daily_loss_limit=None)
    monitor.update(D("1000"), ms(1))
    assert monitor.update(D("1"), ms(1)) is None


def test_zero_equity_is_handled():
    monitor = RiskMonitor(max_drawdown=D("0.05"), daily_loss_limit=D("0.02"))
    assert monitor.update(D("0"), ms(1)) is None  # nothing to measure against yet
