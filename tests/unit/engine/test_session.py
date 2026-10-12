"""TradingSession: the loop body shared by the backtester and the live paper engine."""

from decimal import Decimal as D

from tests.helpers.clock import FakeClock
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, OrderType, Side, Symbol
from wallexbot.domain.order import OrderRequest
from wallexbot.engine.session import TradingSession
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import GridStrategy, PlaceAction
from wallexbot.strategy.grid.parameters import GridMode, GridParameters

SYMBOL = Symbol("USDTTMN")
MARKET = Market(
    symbol=SYMBOL, base="USDT", quote="TMN", price_precision=2, amount_precision=4, is_spot=True
)


def make(grid_count: int = 9, tmn: str = "2000000", investment: str = "90000"):
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
    params = GridParameters(
        lower_price=D("90"),
        upper_price=D("110"),
        grid_count=grid_count,
        mode=GridMode.ARITHMETIC,
        total_investment=D(investment),
    )
    strategy = GridStrategy(MARKET, params)
    return TradingSession(strategy, exchange), exchange, strategy, clock


def sides(exchange) -> dict[D, str]:
    return {o.price: o.side.value for o in exchange.open_orders()}


def test_start_uses_the_given_price_and_funds_the_sells():
    session, exchange, _, _ = make()
    session.start(D("100"), 1_000)

    assert len(exchange.open_orders()) == 8
    assert exchange.balances()["USDT"].locked > 0  # starting inventory bought (D2)
    assert session.fees_quote > 0


def test_a_price_crash_through_three_levels_rebuilds_the_ladder():
    session, exchange, _, _ = make()
    session.start(D("100"), 1_000)

    fills = session.on_tick(D("94"), 2_000)  # trades through 97.5 and 95

    assert len(fills) == 2
    assert len(exchange.open_orders()) == 8  # every filled buy was answered by a sell
    open_sides = sides(exchange)
    # buy@97.5 -> sell@100, buy@95 -> sell@97.5; 95 is now the empty slot
    assert open_sides[D("100")] == "SELL" and open_sides[D("97.5")] == "SELL"
    assert D("95") not in open_sides
    assert [p for p, side in open_sides.items() if side == "BUY"] == [D("92.5"), D("90")] or sorted(
        p for p, side in open_sides.items() if side == "BUY"
    ) == [D("90"), D("92.5")]


def test_more_than_twenty_orders_are_deferred_by_the_rate_limit_then_placed_later():
    session, exchange, _, clock = make(grid_count=31, investment="310000")

    session.start(D("100"), 1_000)
    assert len(exchange.open_orders()) == 20
    assert session.deferred_count == 10

    clock.advance(10.5)
    session.on_tick(D("100"), 2_000)

    assert len(exchange.open_orders()) == 30
    assert session.deferred_count == 0
    assert session.rejected == 0  # a rate limit is a delay, not a failure


def test_underfunded_orders_are_counted_and_forgotten_by_the_strategy():
    session, exchange, strategy, _ = make(tmn="20000")
    session.start(D("100"), 1_000)

    assert session.rejected > 0
    placed_levels = {o.price for o in exchange.open_orders()}
    tracked = {strategy.state.levels[i].price for i in strategy.state.active_orders}
    assert tracked == placed_levels  # no phantom orders in the strategy's state


def test_stop_cancels_everything_and_clears_deferred_orders():
    session, exchange, strategy, _ = make(grid_count=31, investment="310000")
    session.start(D("100"), 1_000)
    assert session.deferred_count == 10

    cancelled = session.stop()

    assert cancelled == 20
    assert exchange.open_orders() == []
    assert session.deferred_count == 0
    assert strategy.state.active_orders == {}


def test_an_order_that_already_exists_is_adopted_not_duplicated():
    session, exchange, strategy, _ = make()
    actions = strategy.on_start(D("100"), 0)
    first = next(a for a in actions if isinstance(a, PlaceAction))
    exchange.place_order(
        OrderRequest(
            client_id=first.client_id,
            symbol=first.symbol,
            side=first.side,
            type=OrderType.LIMIT,
            price=first.price,
            quantity=first.quantity,
        )
    )
    balance_before = exchange.balances()["TMN" if first.side == Side.BUY else "USDT"]

    session.execute([first])  # the same order again, e.g. a retry after a timeout

    assert session.rejected == 0
    assert len(exchange.open_orders()) == 1
    assert exchange.balances()["TMN" if first.side == Side.BUY else "USDT"] == balance_before


def test_leaving_the_grid_range_is_reported_once():
    session, _, _, _ = make()
    session.start(D("100"), 1_000)
    session.on_tick(D("120"), 2_000)
    session.on_tick(D("121"), 3_000)
    session.on_tick(D("100"), 4_000)
    session.on_tick(D("125"), 5_000)

    exits = [e for e in session.events if "left the grid range" in e]
    assert len(exits) == 2
