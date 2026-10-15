"""The backtester must actually trade: place the grid, fill orders, answer fills, and report PnL
that agrees with the simulator's ledger."""

from decimal import Decimal as D

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.analytics.backtest import Backtester
from wallexbot.analytics.replay import candles_to_ticks, resolution_seconds
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Symbol
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridMode, GridParameters
from wallexbot.wallex.models import Candle
from wallexbot.wallex.price_feed import PriceFeedReplay, PriceTick

SYMBOL = Symbol("USDTTMN")
MARKET = Market(
    symbol=SYMBOL, base="USDT", quote="TMN", price_precision=2, amount_precision=4, is_spot=True
)


def make_backtester(
    prices: list[str],
    tmn: str = "2000000",
    investment: str = "90000",
    recenter_after_minutes: int | None = None,
):
    params = GridParameters(
        lower_price=D("90"),
        upper_price=D("110"),
        grid_count=9,
        mode=GridMode.ARITHMETIC,
        total_investment=D(investment),
    )
    clock = FakeClock()
    exchange = SimulatedExchange(
        market=MARKET,
        fee_schedule_config=FeeSchedule(maker_rate=D("0.001"), taker_rate=D("0.002")),
        min_notional_rule=MinNotionalRule(min_notional=D("10"), min_quantity=D("0.0001")),
        initial_balances={
            "TMN": Balance(free=D(tmn), locked=D(0)),
            "USDT": Balance(free=D(0), locked=D(0)),
        },
        clock=clock,
    )
    strategy = GridStrategy(MARKET, params)
    ticks = [
        PriceTick(symbol=SYMBOL, price=D(p), timestamp=1_000_000 + i * 60_000, source="replay")
        for i, p in enumerate(prices)
    ]
    return Backtester(
        strategy=strategy,
        exchange=exchange,
        price_feed=PriceFeedReplay(ticks),
        recenter_after_minutes=recenter_after_minutes,
    ), exchange


def test_the_initial_grid_is_placed_and_funded():
    bt, exchange = make_backtester(["100"])

    result = bt.run()

    orders = exchange.open_orders()
    assert len(orders) == 8  # 4 buys below 100, 4 sells above
    assert sorted(o.side.value for o in orders) == ["BUY"] * 4 + ["SELL"] * 4
    usdt = exchange.balances()["USDT"]
    assert usdt.free == D(0) or usdt.free < D("0.01")  # every purchased coin is locked for sells
    assert usdt.locked > 0  # inventory was bought at market (decision D2)
    assert result.metrics.fees_paid > 0  # the taker fee on that purchase counts
    assert result.metrics.total_return_pct < 0  # only the entry fee has been paid so far


def test_one_buy_then_one_sell_is_a_profitable_cycle_that_matches_the_ledger():
    bt, exchange = make_backtester(["100", "97", "100.5"])  # buy@97.5 fills, then sell@100

    result = bt.run()

    assert result.metrics.completed_cycles == 1
    buy = next(f for f in result.fills if exchange.get_order(f.order_id).side.value == "BUY")
    sell = next(
        f
        for f in result.fills
        if exchange.get_order(f.order_id).side.value == "SELL" and f.price == D("100")
    )
    assert (buy.price, sell.price) == (D("97.5"), D("100"))
    # independent profit from the ledger: proceeds - cost, valuing the unsold dust at 100
    dust = (buy.quantity - buy.fee) - sell.quantity
    ledger_profit = sell.quantity * sell.price - sell.fee - buy.quantity * buy.price + dust * D(100)
    assert abs(result.metrics.realized_pnl - ledger_profit) < D("1")
    assert result.metrics.realized_pnl > 0
    assert result.metrics.avg_profit_per_cycle == result.metrics.realized_pnl


def test_crash_through_the_whole_grid_holds_inventory_and_shows_drawdown():
    bt, exchange = make_backtester(["100", "98", "94", "90.5", "85"])

    result = bt.run()

    m = result.metrics
    assert m.completed_cycles == 0
    assert m.unrealized_pnl < 0 and m.total_return_pct < 0
    assert m.max_drawdown > 0
    assert exchange.balances()["USDT"].total > 0  # holding the coins it bought on the way down
    assert m.buy_and_hold_return == D("-15")


def test_sideways_market_earns_money_over_many_cycles():
    prices = ["100"] + ["97", "100.5"] * 25
    bt, _ = make_backtester(prices)

    m = bt.run().metrics

    assert m.completed_cycles >= 24
    assert m.realized_pnl > 0 and m.total_return_pct > 0
    assert m.outperformance == m.total_return_pct - m.buy_and_hold_return


def test_equity_curve_has_one_point_per_tick_and_drawdown_is_running_peak_to_trough():
    bt, _ = make_backtester(["100", "98", "94", "99"])
    m = bt.run().metrics
    assert len(m.equity_curve) == 4
    peak = D(0)
    worst = D(0)
    for e in m.equity_curve:
        peak = max(peak, e)
        worst = max(worst, (peak - e) / peak * 100)
    assert m.max_drawdown == worst


def test_time_in_range_counts_only_ticks_inside_the_grid():
    bt, _ = make_backtester(["100", "100", "120", "120"])
    assert bt.run().metrics.time_in_range == D(1) / D(3) * 100


def test_leaving_the_range_is_reported_as_an_event():
    bt, _ = make_backtester(["100", "120"])
    result = bt.run()
    assert any("range" in e.lower() for e in result.events)


def test_the_same_data_gives_the_same_result():
    prices = ["100", "97", "100.5", "95", "101"]
    a = make_backtester(prices)[0].run().metrics
    b = make_backtester(prices)[0].run().metrics
    assert a == b


def test_orders_that_cannot_be_funded_are_counted_not_fatal():
    bt, exchange = make_backtester(["100", "97", "100.5"], tmn="20000")  # far too little capital

    result = bt.run()

    assert result.metrics.rejected_orders > 0
    assert result.metrics.completed_cycles >= 0  # ran to the end without raising


class TestCandleReplay:
    def candle(self, o, h, low, c, t=1_700_000_000, res="60"):
        return Candle(
            symbol=SYMBOL,
            resolution=res,
            open_time=t,
            open=D(o),
            high=D(h),
            low=D(low),
            close=D(c),
            volume=D(1),
        )

    def test_resolution_seconds(self):
        assert [resolution_seconds(r) for r in ("1", "15", "60", "240", "1D")] == [
            60,
            900,
            3600,
            14400,
            86400,
        ]

    def test_bullish_candle_visits_low_before_high(self):
        ticks = candles_to_ticks([self.candle("100", "105", "95", "103")])
        assert [t.price for t in ticks] == [D(100), D(95), D(105), D(103)]

    def test_bearish_candle_visits_high_before_low(self):
        ticks = candles_to_ticks([self.candle("100", "105", "95", "97")])
        assert [t.price for t in ticks] == [D(100), D(105), D(95), D(97)]

    def test_timestamps_are_ms_increasing_and_stay_inside_the_candle(self):
        ticks = candles_to_ticks(
            [self.candle("1", "2", "1", "2", t=1000), self.candle("2", "3", "2", "3", t=4600)]
        )
        stamps = [t.timestamp for t in ticks]
        assert stamps == sorted(stamps) and len(set(stamps)) == 8
        assert 1_000_000 <= stamps[0] and stamps[3] < 4_600_000 <= stamps[4]
        assert all(t.symbol == SYMBOL and t.source == "replay" for t in ticks)


def test_instant_buy_gives_coins_minus_taker_fee_and_costs_the_notional():
    _, exchange = make_backtester(["100"])
    before = exchange.balances()["TMN"].free

    fill = exchange.instant_buy(D("100"), D("10"))

    assert fill.fee == D("0.02") and fill.fee_asset == "USDT"  # 10 * 0.002 taker, in base
    assert exchange.balances()["USDT"].free == D("9.98")
    assert exchange.balances()["TMN"].free == before - D("1000")
    with pytest.raises(ValueError, match="Insufficient"):
        exchange.instant_buy(D("100"), D("1000000"))
