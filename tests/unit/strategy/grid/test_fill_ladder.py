"""Ladder semantics of grid fills (regression tests for docs/AUDIT.md P0 items 1-4).

Rule under test: a BUY filled at level i is answered by a SELL at level i+1;
a SELL filled at level i is answered by a BUY at level i-1. The rule is local
to the filled level and must work for any number of fills in a row.
"""

from decimal import Decimal as D

import pytest

from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Side, Symbol
from wallexbot.strategy.grid.fill_handling import handle_fill
from wallexbot.strategy.grid.interface import CancelAction, GridStrategy, PlaceAction
from wallexbot.strategy.grid.parameters import GridMode, GridParameters, Level

MARKET = Market(
    symbol=Symbol("USDTTMN"),
    base="USDT",
    quote="TMN",
    price_precision=2,
    amount_precision=4,
    is_spot=True,
)
FEES = FeeSchedule(maker_rate=D("0.001"), taker_rate=D("0.002"))
MIN_OK = MinNotionalRule(min_notional=D("10"), min_quantity=D("0.0001"))


def make_params() -> GridParameters:
    return GridParameters(
        lower_price=D("90"),
        upper_price=D("110"),
        grid_count=9,
        mode=GridMode.ARITHMETIC,
        total_investment=D("90000"),
    )


def started_strategy() -> tuple[GridStrategy, dict[int, PlaceAction]]:
    """Strategy started at price 100: buys on levels 0-3, gap on 4, sells on 5-8."""
    strategy = GridStrategy(MARKET, make_params())
    actions = strategy.on_start(D("100"))
    placed = {a.level_index: a for a in actions if isinstance(a, PlaceAction)}
    assert sorted(placed) == [0, 1, 2, 3, 5, 6, 7, 8]
    return strategy, placed


def fill(strategy: GridStrategy, placed: dict[int, PlaceAction], level: int):
    """Report a full fill of whatever order currently sits on `level`."""
    order = placed[level]
    actions = strategy.on_fill(level, order.quantity, D("0"), "TMN")
    for a in actions:
        if isinstance(a, PlaceAction):
            placed[a.level_index] = a
    return actions


def places(actions):
    return [a for a in actions if isinstance(a, PlaceAction)]


class TestLadderRule:
    def test_buy_fill_places_sell_on_next_level_up_including_gap(self):
        strategy, placed = started_strategy()
        out = fill(strategy, placed, 3)  # buy at 97.5

        [sell] = places(out)
        assert sell.side == Side.SELL
        assert sell.level_index == 4  # the former gap level (price 100)
        assert sell.price == D("100.00")
        assert not [a for a in out if isinstance(a, CancelAction)]

    def test_sell_fill_places_buy_on_next_level_down(self):
        strategy, placed = started_strategy()
        out = fill(strategy, placed, 5)  # sell at 102.5

        [buy] = places(out)
        assert buy.side == Side.BUY
        assert buy.level_index == 4
        assert buy.price == D("100.00")

    def test_price_crash_through_three_levels_rebuilds_a_sell_ladder(self):
        """AUDIT P0-1: previously only the first fill got a counter-order."""
        strategy, placed = started_strategy()
        all_actions = []
        for lvl in (3, 2, 1):
            all_actions += fill(strategy, placed, lvl)

        assert not [a for a in all_actions if isinstance(a, CancelAction)]
        assert [(a.level_index, a.side) for a in places(all_actions)] == [
            (4, Side.SELL),
            (3, Side.SELL),
            (2, Side.SELL),
        ]
        assert sorted(strategy.state.active_orders) == [0, 2, 3, 4, 5, 6, 7, 8]

    def test_price_spike_through_three_levels_rebuilds_a_buy_ladder(self):
        strategy, placed = started_strategy()
        all_actions = []
        for lvl in (5, 6, 7):
            all_actions += fill(strategy, placed, lvl)

        assert [(a.level_index, a.side) for a in places(all_actions)] == [
            (4, Side.BUY),
            (5, Side.BUY),
            (6, Side.BUY),
        ]
        assert sorted(strategy.state.active_orders) == [0, 1, 2, 3, 4, 5, 6, 8]

    def test_one_order_per_level_invariant_after_many_fills(self):
        strategy, placed = started_strategy()
        for lvl in (3, 4, 3, 4, 5, 4, 5, 6):
            fill(strategy, placed, lvl)
        # never more orders than levels, never a negative/duplicate level
        assert len(strategy.state.active_orders) <= len(strategy.state.levels)
        assert len(strategy.state.active_orders) == 8  # always exactly one empty slot


class TestClientIds:
    def test_client_ids_are_unique_across_repeated_cycles(self):
        """AUDIT P0-2: Wallex rejects a repeated client_id."""
        strategy, placed = started_strategy()
        ids = [a.client_id for a in placed.values()]
        # oscillate: buy@3 fills, sell@4 fills, buy@3 fills, sell@4 fills, ...
        for _ in range(3):
            for lvl in (3, 4):
                ids += [a.client_id for a in places(fill(strategy, placed, lvl))]

        assert len(ids) == len(set(ids))
        assert all(c.replace("_", "").isalnum() for c in ids)  # A-Z, a-z, 0-9, _


class TestCounterQuantityAndFees:
    LEVELS = [
        Level(index=0, price=D("95"), side="buy"),
        Level(index=1, price=D("100"), side=""),
        Level(index=2, price=D("105"), side="sell"),
    ]

    def call(self, **kw):
        base = {
            "fill_level": 0,
            "fill_qty": D("10"),
            "fill_fee": D("0"),
            "levels": self.LEVELS,
            "active_orders": {0: "o0", 2: "o2"},
            "market": MARKET,
            "fee_schedule": FEES,
            "min_notional_rule": MIN_OK,
            "params": make_params(),
        }
        base.update(kw)
        return handle_fill(**base)

    def test_fee_charged_in_base_asset_is_deducted_from_counter_sell(self):
        """AUDIT P0-4: we cannot sell coins that were taken as fee."""
        result = self.call(fill_fee=D("0.01"), fill_fee_asset="USDT", fill_side="buy")
        [sell] = result.actions
        assert sell.quantity == D("9.99")

    def test_fee_charged_in_quote_asset_keeps_full_quantity(self):
        result = self.call(fill_fee=D("0.95"), fill_fee_asset="TMN", fill_side="buy")
        [sell] = result.actions
        assert sell.quantity == D("10")

    def test_too_small_counter_order_is_reported_not_raised(self):
        big_min = MinNotionalRule(min_notional=D("100000"), min_quantity=D("0.0001"))
        result = self.call(min_notional_rule=big_min, fill_side="buy")
        assert result.actions == []
        assert "min" in result.warning.lower()


class TestProfit:
    LEVELS = [
        Level(index=0, price=D("97.5"), side="buy"),
        Level(index=1, price=D("100"), side=""),
        Level(index=2, price=D("102.5"), side="sell"),
    ]

    def test_sell_fill_realizes_spacing_profit_net_of_round_trip_maker_fees(self):
        """AUDIT P0-3: profit was hard-coded to 0."""
        result = handle_fill(
            fill_level=1,
            fill_qty=D("10"),
            fill_fee=D("0"),
            levels=self.LEVELS,
            active_orders={0: "o0", 1: "o1"},
            market=MARKET,
            fee_schedule=FEES,
            min_notional_rule=MIN_OK,
            params=make_params(),
            fill_side="sell",
        )
        # (100 - 97.5) * 10 = 25 gross; fees = (97.5 + 100) * 10 * 0.001 = 1.975
        assert result.profit == D("23.025")

    def test_buy_fill_realizes_no_profit(self):
        result = handle_fill(
            fill_level=0,
            fill_qty=D("10"),
            fill_fee=D("0"),
            levels=self.LEVELS,
            active_orders={0: "o0", 2: "o2"},
            market=MARKET,
            fee_schedule=FEES,
            min_notional_rule=MIN_OK,
            params=make_params(),
            fill_side="buy",
        )
        assert result.profit == D("0")


class TestEdgesAndSafety:
    LEVELS = [
        Level(index=0, price=D("95"), side="buy"),
        Level(index=1, price=D("100"), side="sell"),
    ]

    def call(self, fill_level, fill_side, active):
        return handle_fill(
            fill_level=fill_level,
            fill_qty=D("10"),
            fill_fee=D("0"),
            levels=self.LEVELS,
            active_orders=active,
            market=MARKET,
            fee_schedule=FEES,
            min_notional_rule=MIN_OK,
            params=make_params(),
            fill_side=fill_side,
        )

    def test_top_level_buy_fill_has_no_level_above(self):
        r = self.call(1, "buy", {1: "o1"})
        assert r.actions == [] and r.cycle_completed

    def test_bottom_level_sell_fill_has_no_level_below(self):
        r = self.call(0, "sell", {0: "o0"})
        assert r.actions == [] and r.cycle_completed

    def test_occupied_target_level_never_gets_a_second_order(self):
        r = self.call(0, "buy", {0: "o0", 1: "o1"})
        assert r.actions == []
        assert "occupied" in r.warning.lower()

    def test_duplicate_or_unknown_fill_is_ignored(self):
        r = self.call(0, "buy", {})
        assert r.actions == [] and not r.cycle_completed and r.profit == D("0")


@pytest.mark.parametrize("bad_level", [-1, 5])
def test_fill_on_nonexistent_level_is_ignored(bad_level):
    r = handle_fill(
        fill_level=bad_level,
        fill_qty=D("1"),
        fill_fee=D("0"),
        levels=TestEdgesAndSafety.LEVELS,
        active_orders={},
        market=MARKET,
        fee_schedule=FEES,
        min_notional_rule=MIN_OK,
        params=make_params(),
    )
    assert r.actions == []
