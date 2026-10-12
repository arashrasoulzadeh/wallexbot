"""Rate-limit signalling and client-id lookup on the simulated exchange."""

from decimal import Decimal as D

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, OrderType, Side, Symbol
from wallexbot.domain.order import OrderRequest
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.sim.rate_limiter import RateLimitExceeded

MARKET = Market(
    symbol=Symbol("USDTTMN"),
    base="USDT",
    quote="TMN",
    price_precision=2,
    amount_precision=4,
    is_spot=True,
)


def make(clock: FakeClock) -> SimulatedExchange:
    return SimulatedExchange(
        market=MARKET,
        fee_schedule_config=FeeSchedule(maker_rate=D("0.001"), taker_rate=D("0.002")),
        min_notional_rule=MinNotionalRule(min_notional=D("10"), min_quantity=D("0.0001")),
        initial_balances={
            "TMN": Balance(free=D("1000000"), locked=D(0)),
            "USDT": Balance(free=D(0), locked=D(0)),
        },
        clock=clock,
    )


def buy(cid: str, price: str = "95") -> OrderRequest:
    return OrderRequest(
        client_id=cid,
        symbol=MARKET.symbol,
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=D(price),
        quantity=D("1"),
    )


def test_the_21st_request_in_ten_seconds_raises_a_rate_limit_error_that_clears_with_time():
    clock = FakeClock()
    ex = make(clock)
    for i in range(20):
        ex.place_order(buy(f"c{i}"))

    with pytest.raises(RateLimitExceeded):
        ex.place_order(buy("c20"))
    assert isinstance(RateLimitExceeded("x"), RuntimeError)  # still a RuntimeError for old callers

    clock.advance(10.5)
    ex.place_order(buy("c20"))  # window slid, accepted


def test_a_rejected_request_does_not_burn_a_client_id():
    clock = FakeClock()
    ex = make(clock)
    for i in range(20):
        ex.place_order(buy(f"c{i}"))
    with pytest.raises(RateLimitExceeded):
        ex.place_order(buy("retry_me"))

    clock.advance(11)
    ex.place_order(buy("retry_me"))  # same client_id works: it was never registered


def test_orders_can_be_found_by_client_id():
    ex = make(FakeClock())
    placed = ex.place_order(buy("abc"))
    assert ex.get_order_by_client_id("abc") is placed
    assert ex.get_order_by_client_id("nope") is None
