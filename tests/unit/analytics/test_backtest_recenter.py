"""A backtest can use re-centering too, so its value can be judged before it is switched on."""

from decimal import Decimal as D

from tests.unit.analytics.test_backtester_trades import make_backtester

# 20 hours swinging inside the 90-110 grid, then the price moves to ~150 and swings there
INSIDE = ["96", "104"] * 10
MOVED = ["146", "154"] * 30
PATH = INSIDE + MOVED


def run(recenter_after_minutes=None, prices=PATH):
    bt, exchange = make_backtester(prices, recenter_after_minutes=recenter_after_minutes)
    return bt, bt.run(), exchange


def test_without_it_the_grid_sits_idle_after_the_price_leaves():
    _, result, _ = run()
    assert result.metrics.recenters == 0
    assert result.metrics.time_in_range < D("40")  # most of the path is outside 90-110


def test_with_it_the_grid_follows_the_price_and_keeps_trading():
    _, static, _ = run()
    bt, moving, _ = run(recenter_after_minutes=5)
    assert moving.metrics.recenters >= 1
    assert moving.metrics.completed_cycles > static.metrics.completed_cycles
    assert moving.metrics.time_in_range > static.metrics.time_in_range
    params = bt.session.strategy.params
    assert params.lower_price < D("150") < params.upper_price  # now around where the price lives
    assert any("re-centered" in e for e in moving.events)


def test_the_wait_is_in_simulated_time_not_in_ticks():
    _, result, _ = run(recenter_after_minutes=10_000)  # longer than the whole path
    assert result.metrics.recenters == 0


def test_a_path_that_never_leaves_never_moves():
    _, result, _ = run(recenter_after_minutes=1, prices=INSIDE)
    assert result.metrics.recenters == 0
