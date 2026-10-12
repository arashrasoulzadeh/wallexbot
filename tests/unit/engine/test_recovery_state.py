"""Saving and restoring the state of a trading session.

The property that matters: a session that is saved, thrown away and restored at ANY point finishes
exactly like one that was never interrupted.
"""

import json
import random
from decimal import Decimal as D

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Side, Symbol
from wallexbot.engine.risk import RiskMonitor
from wallexbot.engine.session import TradingSession
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridMode, GridParameters

SYMBOL = Symbol("USDTTMN")
MARKET = Market(
    symbol=SYMBOL, base="USDT", quote="TMN", price_precision=2, amount_precision=4, is_spot=True
)


def build(grid_count: int = 9, investment: str = "90000") -> tuple[TradingSession, FakeClock]:
    clock = FakeClock()
    exchange = SimulatedExchange(
        market=MARKET,
        fee_schedule_config=FeeSchedule(maker_rate=D("0.001"), taker_rate=D("0.002")),
        min_notional_rule=MinNotionalRule(min_notional=D("10"), min_quantity=D("0.0001")),
        initial_balances={
            "TMN": Balance(free=D("2000000"), locked=D(0)),
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
    return TradingSession(GridStrategy(MARKET, params), exchange), clock


def walk(n: int, seed: int) -> list[D]:
    rng = random.Random(seed)
    price, out = D("100"), []
    for _ in range(n):
        price = min(max(price + D(rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])) / 2, D("86")), D("114"))
        out.append(price)
    return out


def fingerprint(session: TradingSession) -> dict:
    ex, st = session.exchange, session.strategy
    state = st.state
    return {
        "balances": {a: (str(b.free), str(b.locked)) for a, b in sorted(ex.balances().items())},
        "open": sorted(
            (o.id, o.client_id, o.side.value, str(o.price), str(o.quantity), str(o.filled_quantity))
            for o in ex.open_orders()
        ),
        "active": dict(sorted(state.active_orders.items())) if state else None,
        "sides": dict(sorted(state.order_sides.items())) if state else None,
        "qty": {k: str(v) for k, v in sorted(state.order_qty.items())} if state else None,
        "cycles": st.profit_tracker.total_cycles,
        "profit": str(st.profit_tracker.total_profit),
        "fill_count": session.fill_count,
        "fees": str(session.fees_quote),
        "rejected": session.rejected,
        "deferred": session.deferred_count,
        "events": list(session.events),
    }


def run(session: TradingSession, clock: FakeClock, prices: list[D], first: bool) -> None:
    for i, price in enumerate(prices):
        clock.advance(1)
        ts = int(clock.now() * 1000)
        if first and i == 0:
            session.start(price, ts)
        else:
            session.on_tick(price, ts)


def crash_and_restore(
    session: TradingSession, clock_now: float
) -> tuple[TradingSession, FakeClock]:
    """Save to JSON text, throw everything away, rebuild from scratch and restore."""
    saved = json.loads(json.dumps(session.export_state()))
    fresh, clock = build(
        grid_count=session.strategy.params.grid_count,
        investment=str(session.strategy.params.total_investment),
    )
    clock.set_time(clock_now)
    fresh.import_state(saved)
    return fresh, clock


@pytest.mark.parametrize("crash_at", range(1, 40))
def test_a_session_restored_after_a_crash_at_any_point_finishes_identically(crash_at):
    prices = walk(40, seed=11)

    reference, ref_clock = build()
    run(reference, ref_clock, prices, first=True)

    original, clock = build()
    run(original, clock, prices[:crash_at], first=True)
    restored, new_clock = crash_and_restore(original, clock.now())
    assert fingerprint(restored) == fingerprint(original)  # identical at the moment of the crash
    run(restored, new_clock, prices[crash_at:], first=False)

    assert fingerprint(restored) == fingerprint(reference)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_equivalence_holds_on_other_random_paths(seed):
    prices = walk(60, seed=seed)
    reference, ref_clock = build()
    run(reference, ref_clock, prices, first=True)

    original, clock = build()
    cut = 20 + seed * 5
    run(original, clock, prices[:cut], first=True)
    restored, new_clock = crash_and_restore(original, clock.now())
    run(restored, new_clock, prices[cut:], first=False)
    assert fingerprint(restored) == fingerprint(reference)


def test_orders_waiting_for_the_rate_limit_survive_a_crash():
    # long enough (15 s) for the 10 s rate-limit window to clear in BOTH runs; the window itself is
    # deliberately not saved, because after a real restart it has long expired
    prices = [D("100")] * 15
    reference, ref_clock = build(grid_count=31, investment="310000")
    run(reference, ref_clock, prices, first=True)

    original, clock = build(grid_count=31, investment="310000")
    run(original, clock, prices[:1], first=True)
    assert original.deferred_count == 10
    restored, new_clock = crash_and_restore(original, clock.now())
    assert restored.deferred_count == 10
    run(restored, new_clock, prices[1:], first=False)

    assert fingerprint(restored) == fingerprint(reference)
    assert restored.deferred_count == 0 and len(restored.exchange.open_orders()) == 30


def test_a_partial_fill_in_progress_survives_a_crash():
    session, clock = build()
    run(session, clock, [D("100")], first=True)
    state = session.strategy.state
    level = max(i for i, side in state.order_sides.items() if side == "buy")
    session.strategy.on_fill(level, state.order_qty[level] / 2, D("0"), "TMN")  # half filled

    restored, _ = crash_and_restore(session, clock.now())

    assert restored.strategy.state.filled_qty == session.strategy.state.filled_qty
    # the other half arrives after the restart: one counter-order for the full quantity
    actions = restored.strategy.on_fill(level, state.order_qty[level] / 2, D("0"), "TMN")
    assert [a.side for a in actions if hasattr(a, "side")] == [Side.SELL]


def test_the_saved_state_is_plain_json_and_small():
    session, clock = build()
    run(session, clock, walk(300, seed=9), first=True)
    text = json.dumps(session.export_state())
    assert len(text) < 60_000  # bounded: history is capped, not the whole run


def test_finished_orders_do_not_pile_up_in_the_matching_engine():
    session, clock = build()
    run(session, clock, [D("100")] + [D("97"), D("100.5")] * 40, first=True)
    assert len(session.exchange._matching_engine._orders) == len(session.exchange.open_orders())
    assert len(session.exchange._orders) < 200  # retained finished orders are capped


def test_a_state_from_a_different_grid_is_refused():
    session, clock = build()
    run(session, clock, [D("100")], first=True)
    saved = json.loads(json.dumps(session.export_state()))
    other, _ = build(grid_count=5, investment="50000")
    with pytest.raises(ValueError, match="grid"):
        other.import_state(saved)


def test_an_unknown_state_version_is_refused():
    session, clock = build()
    run(session, clock, [D("100")], first=True)
    saved = session.export_state()
    saved["version"] = 99
    fresh, _ = build()
    with pytest.raises(ValueError, match="version"):
        fresh.import_state(saved)


def test_risk_monitor_state_round_trips():
    monitor = RiskMonitor(max_drawdown=D("0.05"), daily_loss_limit=D("0.02"))
    monitor.update(D("1000"), 1_700_000_000_000)
    monitor.update(D("1100"), 1_700_000_060_000)
    restored = RiskMonitor(max_drawdown=D("0.05"), daily_loss_limit=D("0.02"))
    restored.import_state(json.loads(json.dumps(monitor.export_state())))

    # the peak (1100) was remembered: 1040 is a 5.45% drawdown from it
    assert restored.update(D("1040"), 1_700_000_120_000) is not None
    assert RiskMonitor(D("0.05"), D("0.02")).update(D("1040"), 1_700_000_120_000) is None
