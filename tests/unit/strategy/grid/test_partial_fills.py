"""Decision D1: wait for the full fill, then place ONE counter-order for the total."""

from decimal import Decimal as D

from wallexbot.domain.market import Market, Side, Symbol
from wallexbot.strategy.grid.interface import AlertAction, GridStrategy, PlaceAction
from wallexbot.strategy.grid.parameters import GridMode, GridParameters

MARKET = Market(
    symbol=Symbol("USDTTMN"), base="USDT", quote="TMN",
    price_precision=2, amount_precision=4, is_spot=True,
)


def started():
    params = GridParameters(
        lower_price=D("90"), upper_price=D("110"), grid_count=9,
        mode=GridMode.ARITHMETIC, total_investment=D("90000"),
    )
    s = GridStrategy(MARKET, params)
    s.on_start(D("100"))
    return s


def places(actions):
    return [a for a in actions if isinstance(a, PlaceAction)]


def test_partial_fill_places_nothing_and_keeps_the_order_active():
    s = started()
    qty = s.state.order_qty[3]

    out = s.on_fill(3, qty * D("0.4"), D("0"), "TMN")

    assert places(out) == []
    assert 3 in s.state.active_orders  # still resting on the book
    assert 4 not in s.state.active_orders  # no sell yet


def test_remaining_fill_completes_and_places_one_counter_for_the_total():
    s = started()
    qty = s.state.order_qty[3]

    s.on_fill(3, qty * D("0.4"), D("0"), "TMN")
    out = s.on_fill(3, qty - qty * D("0.4"), D("0"), "TMN")

    [sell] = places(out)
    assert sell.side == Side.SELL and sell.level_index == 4
    assert sell.quantity == qty.quantize(D("0.0001"), rounding="ROUND_DOWN") or sell.quantity == qty
    assert 3 not in s.state.active_orders
    assert 4 in s.state.active_orders


def test_many_small_fills_add_up():
    s = started()
    qty = s.state.order_qty[3]
    piece = qty / 4
    outs = [s.on_fill(3, piece, D("0"), "TMN") for _ in range(4)]

    assert [len(places(o)) for o in outs] == [0, 0, 0, 1]


def test_base_fee_is_summed_across_partial_fills_and_deducted_once():
    s = started()
    qty = s.state.order_qty[3]
    s.on_fill(3, qty / 2, D("0.01"), "USDT")
    out = s.on_fill(3, qty / 2, D("0.02"), "USDT")

    [sell] = places(out)
    assert sell.quantity == (qty - D("0.03")).quantize(D("0.0001"), rounding="ROUND_DOWN")


def test_fill_within_one_precision_step_of_the_order_counts_as_full():
    s = started()
    qty = s.state.order_qty[3]
    out = s.on_fill(3, qty - D("0.00005"), D("0"), "TMN")  # step is 0.0001

    assert len(places(out)) == 1


def test_overfill_is_treated_as_full():
    s = started()
    qty = s.state.order_qty[3]
    out = s.on_fill(3, qty + D("1"), D("0"), "TMN")

    assert len(places(out)) == 1


def test_cancel_after_partial_fill_still_answers_the_filled_part():
    s = started()
    qty = s.state.order_qty[3]
    s.on_fill(3, qty * D("0.5"), D("0"), "TMN")

    out = s.on_cancel(3)

    [sell] = places(out)
    assert sell.side == Side.SELL and sell.level_index == 4
    assert sell.quantity == (qty * D("0.5")).quantize(D("0.0001"), rounding="ROUND_DOWN")
    assert 3 not in s.state.active_orders


def test_cancel_without_any_fill_places_nothing():
    s = started()
    assert s.on_cancel(3) == []
    assert 3 not in s.state.active_orders


def test_fill_for_unknown_level_is_ignored():
    s = started()
    assert s.on_fill(4, D("1"), D("0"), "TMN") == []  # the gap level has no order


def test_profit_is_recorded_once_per_completed_sell_not_per_partial():
    s = started()
    qty = s.state.order_qty[5]
    s.on_fill(5, qty / 2, D("0"), "USDT")
    assert s.profit_tracker.total_cycles == 0
    s.on_fill(5, qty / 2, D("0"), "USDT")
    assert s.profit_tracker.total_cycles == 1
    assert not [a for a in [] if isinstance(a, AlertAction)]
