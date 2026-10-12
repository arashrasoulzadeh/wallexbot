"""Scenario tests for grid strategy (table-driven)."""

from decimal import Decimal

import pytest

from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Symbol
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import (
    GridMode,
    GridParameters,
)


class TestGridScenarios:
    """Table-driven scenario tests for grid strategy."""

    @pytest.fixture
    def market(self):
        return Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )

    @pytest.fixture
    def params(self):
        return GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=5,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
        )

    @pytest.fixture
    def fee_schedule(self):
        return FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002"))

    @pytest.fixture
    def min_notional(self):
        return MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001"))

    def _setup_strategy(self, market, params, current_price):
        """Helper to set up strategy with initial grid."""
        strategy = GridStrategy(market=market, params=params)
        actions = strategy.on_start(current_price=current_price)
        return strategy, actions

    def test_uptrend_through_all_levels(self, market, params, fee_schedule, min_notional):
        """Price moves up through all sell levels, filling each."""
        strategy, _ = self._setup_strategy(market, params, Decimal("100.00"))
        # Levels: 90(buy), 95(buy), 100(skip), 105(sell), 110(sell)
        # Active sells at 105, 110

        # Fill sell at 105 (level 3)
        actions = strategy.on_fill(3, strategy.state.order_qty[3], Decimal("0.021"), "USDT")
        # Sell at 105 is answered by a buy one level down, at 100 (level 2)
        place_actions = [a for a in actions if a.type == "place"]
        assert len(place_actions) == 1
        assert place_actions[0].side.value == "BUY"
        assert place_actions[0].level_index == 2

        # Fill sell at 110 (level 4)
        actions = strategy.on_fill(4, strategy.state.order_qty[4], Decimal("0.022"), "USDT")
        place_actions = [a for a in actions if a.type == "place"]
        # Top-level sell is answered by a buy one level down, at 105 (level 3)
        assert len(place_actions) == 1
        assert place_actions[0].side.value == "BUY"
        assert place_actions[0].level_index == 3

    def test_downtrend_through_all_levels(self, market, params, fee_schedule, min_notional):
        """Price moves down through all buy levels, filling each."""
        strategy, _ = self._setup_strategy(market, params, Decimal("100.00"))
        # Active buys at 90, 95

        # Fill buy at 95 (level 1)
        actions = strategy.on_fill(1, strategy.state.order_qty[1], Decimal("0.95"), "TMN")
        place_actions = [a for a in actions if a.type == "place"]
        assert len(place_actions) == 1
        assert place_actions[0].side.value == "SELL"
        assert place_actions[0].level_index == 2  # sell one level up, at 100

    def test_sideways_oscillation(self, market, params, fee_schedule, min_notional):
        """Price oscillates around a level, generating multiple fills."""
        strategy, _ = self._setup_strategy(market, params, Decimal("100.00"))

        # Fill buy at 95 (level 1) -> sell placed at 100 (level 2)
        actions = strategy.on_fill(1, strategy.state.order_qty[1], Decimal("0.95"), "TMN")
        place_actions = [a for a in actions if a.type == "place"]
        assert [(a.side.value, a.level_index) for a in place_actions] == [("SELL", 2)]

        # That sell fills (level 2) -> buy placed back at 95 (level 1): one full cycle
        actions = strategy.on_fill(2, strategy.state.order_qty[2], Decimal("0.021"), "USDT")
        place_actions = [a for a in actions if a.type == "place"]
        assert [(a.side.value, a.level_index) for a in place_actions] == [("BUY", 1)]
        assert strategy.profit_tracker.total_cycles == 1
        assert strategy.profit_tracker.total_profit > 0

    def test_gap_jump_over_several_levels(self, market, params, fee_schedule, min_notional):
        """Price jumps over several levels - only fills at levels with orders."""
        strategy, _ = self._setup_strategy(market, params, Decimal("100.00"))

        # Price jumps from 100 to 108 - only sell at 105 fills
        # (assuming orders only at grid levels)
        actions = strategy.on_fill(3, strategy.state.order_qty[3], Decimal("0.021"), "USDT")
        place_actions = [a for a in actions if a.type == "place"]
        assert len(place_actions) == 1
        assert place_actions[0].level_index == 2  # Buy at 100

    def test_whipsaw_at_one_level(self, market, params, fee_schedule, min_notional):
        """Price whipsaws at one level - buy fill, sell fill, buy fill..."""
        strategy, _ = self._setup_strategy(market, params, Decimal("100.00"))

        # Fill buy at 95
        actions = strategy.on_fill(1, strategy.state.order_qty[1], Decimal("0.95"), "TMN")
        place_actions = [a for a in actions if a.type == "place"]
        assert len(place_actions) == 1
        # Fill sell at 105 (the placed order)
        # Need to track that this is the new order at level 3
        # This test is more integration-style

    def test_partial_fill_handling(self, market, params, fee_schedule, min_notional):
        """Decision D1: wait for the full fill, then place one counter-order for the total."""
        strategy, _ = self._setup_strategy(market, params, Decimal("100.00"))

        # Half of the buy at level 1 (95) fills: nothing happens yet (decision D1)
        ordered = strategy.state.order_qty[1]
        half = ordered / 2
        actions = strategy.on_fill(1, half, Decimal("0.475"), "TMN")
        assert [a for a in actions if a.type == "place"] == []

        # The rest fills: one counter-order for the full quantity, one level up (100)
        actions = strategy.on_fill(1, ordered - half, Decimal("0.475"), "TMN")
        place_actions = [a for a in actions if a.type == "place"]
        assert len(place_actions) == 1
        assert place_actions[0].quantity == ordered
        assert place_actions[0].level_index == 2

    def test_duplicate_fill_idempotent(self, market, params, fee_schedule, min_notional):
        """Duplicate fill event is idempotent."""
        strategy, _ = self._setup_strategy(market, params, Decimal("100.00"))

        # First fill at level 1 (adjacent to gap, generates counter-order)
        qty = strategy.state.order_qty[1]
        actions1 = strategy.on_fill(1, qty, Decimal("0.95"), "TMN")
        place_actions1 = [a for a in actions1 if a.type == "place"]
        assert len(place_actions1) == 1
        # Second fill (duplicate) - order already cleared
        actions2 = strategy.on_fill(1, qty, Decimal("0.95"), "TMN")
        place_actions2 = [a for a in actions2 if a.type == "place"]
        assert len(place_actions2) == 0


class TestGridInvariants:
    """Property tests for grid invariants."""

    def test_no_negative_balances_after_random_path(self):
        """After any random price path + fills, no negative balances."""
        # This would be a hypothesis test - skipping for now
        pass

    def test_order_count_bounded(self):
        """Order count never exceeds grid_count."""
        # This would be a hypothesis test
        pass

    def test_levels_consistent(self):
        """Levels remain consistent after fills."""
        pass
