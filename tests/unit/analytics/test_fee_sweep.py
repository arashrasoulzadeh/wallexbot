"""The same grid on the same candles at different fee tiers: what the unknown Wallex fee costs."""

from decimal import Decimal as D
from pathlib import Path

from tests.helpers.wallex_fakes import FakeClient, swinging_candles
from wallexbot.analytics.fee_sweep import break_even_fee, fee_sweep
from wallexbot.config.schema import load_config
from wallexbot.setup import GridSetup, find_market

EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"


def setup() -> GridSetup:
    return GridSetup.from_config(load_config(str(EXAMPLE)), find_market(FakeClient(), "USDTTMN"))


def test_the_break_even_fee_follows_from_the_spacing():
    # 255000-275000 in 5 levels: 5000 apart on a mid of 265000 = 1.887 %; a cycle must beat 2 x fee x 1.5
    assert abs(break_even_fee(setup().params) - D("0.00629")) < D("0.00002")


def test_rows_come_back_in_fee_order_with_money_going_down_as_the_fee_goes_up():
    s = setup()
    rows = fee_sweep(s, swinging_candles(60), [D("0.0035"), D("0.0005"), D("0.002")])
    assert [r.fee for r in rows] == [D("0.0005"), D("0.002"), D("0.0035")]
    assert rows[0].realized > rows[1].realized > rows[2].realized
    assert rows[0].fees_paid < rows[2].fees_paid
    assert (
        len({r.cycles for r in rows}) == 1
    )  # the fee changes the profit, not where the price goes
    assert all(r.cycles >= 1 for r in rows)


def test_each_row_says_whether_the_fee_clears_the_break_even_rule():
    s = setup()
    rows = fee_sweep(s, swinging_candles(60), [D("0.0035"), D("0.01")])
    assert rows[0].clears_break_even is True and rows[1].clears_break_even is False


def test_a_grid_whose_orders_are_too_small_gives_no_rows_instead_of_crashing():
    s = setup()
    tiny = GridSetup(**{**s.__dict__, "min_notional": D("99999999")})
    from wallexbot.domain.fees import MinNotionalRule

    tiny.min_rule = MinNotionalRule(min_notional=D("99999999"), min_quantity=D("0.01"))
    assert fee_sweep(tiny, swinging_candles(20), [D("0.001")]) == []
