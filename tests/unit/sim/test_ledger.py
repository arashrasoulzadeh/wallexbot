"""Simulator accounting rules (Wallex conventions, see docs/wallex-api.md):

- funds are locked once when an order is placed and settle exactly when it fills;
- a resting LIMIT order fills at ITS OWN price, never at a better trade price;
- the fee is charged in the asset RECEIVED (BUY pays in base, SELL pays in quote).
"""

import random
from decimal import Decimal as D

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, OrderType, Side, Symbol
from wallexbot.domain.order import OrderRequest
from wallexbot.sim.exchange import SimulatedExchange

MARKET = Market(
    symbol=Symbol("USDTTMN"),
    base="USDT",
    quote="TMN",
    price_precision=2,
    amount_precision=4,
    is_spot=True,
)


def make_exchange(
    tmn: str = "10000", usdt: str = "0", clock: FakeClock | None = None
) -> SimulatedExchange:
    return SimulatedExchange(
        clock=clock or FakeClock(),
        market=MARKET,
        fee_schedule_config=FeeSchedule(maker_rate=D("0.001"), taker_rate=D("0.002")),
        min_notional_rule=MinNotionalRule(min_notional=D("10"), min_quantity=D("0.0001")),
        initial_balances={
            "TMN": Balance(free=D(tmn), locked=D(0)),
            "USDT": Balance(free=D(usdt), locked=D(0)),
        },
    )


def limit(side: Side, price: str, qty: str, cid: str) -> OrderRequest:
    return OrderRequest(
        client_id=cid,
        symbol=MARKET.symbol,
        side=side,
        type=OrderType.LIMIT,
        price=D(price),
        quantity=D(qty),
    )


def bal(ex: SimulatedExchange, asset: str) -> tuple[D, D]:
    b = ex.balances()[asset]
    return b.free, b.locked


class TestBuy:
    def test_buy_locks_only_the_notional_no_fee(self):
        ex = make_exchange()
        ex.place_order(limit(Side.BUY, "95", "10", "b1"))
        assert bal(ex, "TMN") == (D("9050"), D("950"))

    def test_buy_fill_settles_at_limit_price_and_charges_fee_in_base(self):
        ex = make_exchange()
        ex.place_order(limit(Side.BUY, "95", "10", "b1"))

        [fill] = ex.process_trade(D("94"), D("100"), 1)

        assert fill.price == D("95")  # own limit price, not the better trade price 94
        assert fill.fee == D("0.01") and fill.fee_asset == "USDT"
        assert bal(ex, "TMN") == (D("9050"), D("0"))  # 950 spent, nothing left locked
        assert bal(ex, "USDT") == (D("9.99"), D("0"))  # 10 received minus 0.01 fee


class TestSell:
    def test_sell_locks_exactly_the_quantity(self):
        ex = make_exchange(tmn="0", usdt="10")
        ex.place_order(limit(Side.SELL, "100", "10", "s1"))
        assert bal(ex, "USDT") == (D("0"), D("10"))

    def test_sell_fill_credits_quote_minus_fee_in_quote(self):
        ex = make_exchange(tmn="0", usdt="10")
        ex.place_order(limit(Side.SELL, "100", "10", "s1"))

        [fill] = ex.process_trade(D("101"), D("100"), 1)

        assert fill.price == D("100")
        assert fill.fee == D("1.00") and fill.fee_asset == "TMN"
        assert bal(ex, "USDT") == (D("0"), D("0"))
        assert bal(ex, "TMN") == (D("999"), D("0"))  # 1000 proceeds minus 1.00 fee


class TestRoundTrip:
    def test_buy_then_sell_everything_received_ends_with_known_balance(self):
        ex = make_exchange()
        ex.place_order(limit(Side.BUY, "95", "10", "b1"))
        ex.process_trade(D("94"), D("100"), 1)  # +9.99 USDT, -950 TMN
        ex.place_order(limit(Side.SELL, "100", "9.99", "s1"))  # sells exactly what we hold
        ex.process_trade(D("101"), D("100"), 2)

        # 10000 - 950 + 9.99*100 (=999) - 0.999 fee = 10048.001
        assert bal(ex, "TMN") == (D("10048.001"), D("0"))
        assert bal(ex, "USDT") == (D("0"), D("0"))


class TestPartialAndCancel:
    def test_partial_fill_then_cancel_releases_exactly_the_remainder(self):
        ex = make_exchange()
        order = ex.place_order(limit(Side.BUY, "95", "10", "b1"))

        [fill] = ex.process_trade(D("94"), D("4"), 1)  # only 4 of 10 trade
        assert fill.quantity == D("4")
        assert bal(ex, "TMN") == (D("9050"), D("570"))  # 380 spent, 6 * 95 still locked

        ex.cancel_order(order.id)

        assert bal(ex, "TMN") == (D("9620"), D("0"))
        assert bal(ex, "USDT") == (D("3.996"), D("0"))

    def test_cancel_unfilled_buy_and_sell_release_everything(self):
        ex = make_exchange(usdt="5")
        b = ex.place_order(limit(Side.BUY, "95", "10", "b1"))
        s = ex.place_order(limit(Side.SELL, "100", "5", "s1"))
        ex.cancel_order(b.id)
        ex.cancel_order(s.id)
        assert bal(ex, "TMN") == (D("10000"), D("0"))
        assert bal(ex, "USDT") == (D("5"), D("0"))

    def test_selling_more_than_held_is_rejected(self):
        ex = make_exchange(tmn="0", usdt="5")
        with pytest.raises(ValueError, match="Insufficient"):
            ex.place_order(limit(Side.SELL, "100", "6", "s1"))


class TestStopAndMarket:
    def test_triggered_stop_limit_does_not_lock_funds_twice(self):
        ex = make_exchange(tmn="0", usdt="10")
        ex.place_order(
            OrderRequest(
                client_id="st1",
                symbol=MARKET.symbol,
                side=Side.SELL,
                type=OrderType.STOP_LIMIT,
                price=D("98"),
                quantity=D("10"),
                stop_price=D("99"),
            )
        )
        locked_before = bal(ex, "USDT")

        ex.process_trade(D("99"), D("1"), 1)  # trade at the stop price triggers it

        assert bal(ex, "USDT") == locked_before

    def test_market_orders_are_rejected_until_they_are_simulated(self):
        ex = make_exchange()
        with pytest.raises(ValueError, match="market orders"):
            ex.place_order(
                OrderRequest(
                    client_id="m1",
                    symbol=MARKET.symbol,
                    side=Side.BUY,
                    type=OrderType.MARKET,
                    price=None,
                    quantity=D("1"),
                )
            )


def test_random_activity_always_agrees_with_the_fills():
    """Whatever happens, balances change exactly by what the fills say (no leaks, no negatives)."""
    rng = random.Random(1234)
    clock = FakeClock()
    ex = make_exchange(tmn="100000", usdt="500", clock=clock)
    start = {a: ex.balances()[a].free + ex.balances()[a].locked for a in ("TMN", "USDT")}
    expected = dict(start)
    live: list[str] = []

    for step in range(300):
        clock.advance(1)  # stay under the 20 orders / 10 s limit
        action = rng.choice(["buy", "sell", "cancel", "trade", "trade"])
        try:
            if action in ("buy", "sell"):
                side = Side.BUY if action == "buy" else Side.SELL
                price = D(rng.randrange(90, 111))
                qty = D(rng.randrange(1, 20))
                o = ex.place_order(limit(side, str(price), str(qty), f"c{step}"))
                live.append(o.id)
            elif action == "cancel" and live:
                ex.cancel_order(live.pop(rng.randrange(len(live))))
            else:
                for f in ex.process_trade(D(rng.randrange(85, 116)), D(rng.randrange(1, 40)), step):
                    side = ex.get_order(f.order_id).side
                    if side == Side.BUY:
                        expected["TMN"] -= f.price * f.quantity
                        expected["USDT"] += f.quantity - f.fee
                    else:
                        expected["USDT"] -= f.quantity
                        expected["TMN"] += f.price * f.quantity - f.fee
        except ValueError:
            pass  # insufficient funds / inactive order: legitimate rejections

        for asset in ("TMN", "USDT"):
            b = ex.balances()[asset]
            assert b.free >= 0 and b.locked >= 0
            assert b.free + b.locked == expected[asset], f"step {step}: {asset} ledger drifted"
