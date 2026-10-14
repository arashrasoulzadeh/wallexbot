"""Adaptive decisions: what the system would do to a running grid (decision only, nothing is applied)."""

from decimal import Decimal as D

import pytest

from wallexbot.domain.market import Symbol
from wallexbot.intelligence.adaptive import (
    AdaptiveAction,
    anomaly_guard,
    dynamic_spacing,
    recenter_grid,
    trend_guard,
)
from wallexbot.strategy.grid.parameters import GridMode, GridParameters
from wallexbot.wallex.models import Candle

PARAMS = GridParameters(
    lower_price=D("90"),
    upper_price=D("110"),
    grid_count=5,
    mode=GridMode.ARITHMETIC,
    total_investment=D("1000000"),
)


def candles(closes, spread="1"):
    out = []
    for i, c in enumerate(closes):
        c = D(str(c))
        out.append(
            Candle(
                symbol=Symbol("USDTTMN"),
                resolution="60",
                open_time=1_700_000_000 + i * 3600,
                open=c,
                high=c + D(spread),
                low=c - D(spread),
                close=c,
                volume=D(10),
            )
        )
    return out


FEW = candles([100] * 5)
FLAT = candles([100] * 40)


@pytest.mark.parametrize(
    "guard",
    [
        lambda c: recenter_grid(c, PARAMS),
        lambda c: dynamic_spacing(c, PARAMS, D("0.001")),
        lambda c: trend_guard(c, PARAMS),
        lambda c: anomaly_guard(c, PARAMS),
    ],
)
def test_every_decision_waits_for_enough_data(guard):
    d = guard(FEW)
    assert d.action is AdaptiveAction.NONE and d.confidence == 0


def test_a_price_inside_the_range_is_left_alone():
    assert recenter_grid(FLAT, PARAMS).action is AdaptiveAction.NONE


def test_a_price_outside_the_range_recenters_keeping_the_width():
    d = recenter_grid(candles([130] * 40), PARAMS)
    assert d.action is AdaptiveAction.RECENTER
    lower, upper = D(d.params["lower_price"]), D(d.params["upper_price"])
    assert upper - lower == 20 and lower < D("130") < upper


def test_spacing_widens_when_the_coin_is_busy_and_narrows_when_it_is_calm():
    busy = dynamic_spacing(candles([100] * 40, spread="20"), PARAMS, D("0.0001"))
    assert busy.action is AdaptiveAction.WIDEN_SPACING and D(busy.params["target_spacing"]) > 5
    calm = dynamic_spacing(candles([100] * 40, spread="0.01"), PARAMS, D("0.0001"))
    assert calm.action in (AdaptiveAction.NARROW_SPACING, AdaptiveAction.NONE)


def test_spacing_within_five_percent_is_not_touched():
    # spacing is 5 here; a fee that makes the minimum spacing exactly 5 changes nothing
    d = dynamic_spacing(
        candles([100] * 40, spread="0.01"), PARAMS, D("0.025"), min_profit_multiple=D("1")
    )
    assert d.action is AdaptiveAction.NONE and "tolerance" in d.reason


def test_spacing_change_is_limited_per_step():
    d = dynamic_spacing(
        candles([100] * 40, spread="500"), PARAMS, D("0.0001"), max_change_pct=D("0.2")
    )
    assert D(d.params["target_spacing"]) == D("6.0")  # 5 * 1.2


def test_a_steady_market_has_no_trend_to_guard_against():
    assert trend_guard(FLAT, PARAMS).action is AdaptiveAction.NONE


def test_a_strong_trend_pauses_new_buys():
    rising = candles([100 + i * 3 for i in range(40)], spread="0.5")
    d = trend_guard(rising, PARAMS)
    assert d.action is AdaptiveAction.PAUSE_BUYS and "trending" in d.params["regime"]


def test_a_price_jump_halts():
    closes = [100] * 39 + [110]
    d = anomaly_guard(candles(closes), PARAMS)
    assert d.action is AdaptiveAction.HALT and "jump" in d.reason.lower()
    assert anomaly_guard(FLAT, PARAMS).action is AdaptiveAction.NONE
