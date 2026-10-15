"""Static grid vs grid that follows the price vs just holding the coin, on the same candles."""

from decimal import Decimal as D
from pathlib import Path

from tests.helpers.wallex_fakes import FakeClient
from wallexbot.analytics.compare import compare_strategies
from wallexbot.config.schema import load_config
from wallexbot.domain.market import Symbol
from wallexbot.setup import GridSetup, find_market
from wallexbot.wallex.models import Candle

EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"  # grid 255000-275000


def candle(i: int, o: int, c: int, resolution: str = "60") -> Candle:
    return Candle(
        symbol=Symbol("USDTTMN"),
        resolution=resolution,
        open_time=1_700_000_000 + i * 3600,
        open=D(o),
        high=D(max(o, c)),
        low=D(min(o, c)),
        close=D(c),
        volume=D(1),
    )


def path() -> list[Candle]:
    """20 hours swinging inside the grid, then the price runs to ~300,000 and swings there."""
    out = []
    for i in range(20):
        up = i % 2 == 0
        out.append(candle(i, 262000 if up else 268000, 268000 if up else 262000))
    for i in range(20, 80):
        up = i % 2 == 0
        out.append(candle(i, 296000 if up else 304000, 304000 if up else 296000))
    return out


def setup() -> GridSetup:
    return GridSetup.from_config(load_config(str(EXAMPLE)), find_market(FakeClient(), "USDTTMN"))


def test_three_rows_in_a_fixed_order():
    rows = compare_strategies(setup(), path(), recenter_after_minutes=120)
    assert [r.label for r in rows] == ["static", "recentering", "buy_and_hold"]


def test_the_moving_grid_trades_more_and_is_marked_as_having_moved():
    static, moving, hold = compare_strategies(setup(), path(), recenter_after_minutes=120)
    assert static.recenters == 0 and moving.recenters >= 1
    assert moving.cycles > static.cycles
    assert hold.cycles == 0 and hold.realized == 0 and hold.recenters == 0


def test_buy_and_hold_follows_the_price_and_has_its_own_drawdown():
    hold = compare_strategies(setup(), path(), recenter_after_minutes=120)[2]
    # first price 262000 (open of the first candle) to the last close 296000
    assert D("12") < hold.return_pct < D("14")
    assert hold.max_drawdown >= 0
