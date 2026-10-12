"""Per-coin default grids: every Wallex spot market must get a valid, startable grid."""

import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.config.schema import validate_config
from wallexbot.domain.market import Symbol
from wallexbot.engine.session import TradingSession
from wallexbot.market_defaults import suggest_config
from wallexbot.setup import GridSetup
from wallexbot.wallex.client import WallexRestClient
from wallexbot.wallex.models import Market

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "wallex" / "markets_full.json"


class _Replay:
    """A transport that answers with the recorded markets list."""

    def request(self, method, url, **kwargs):
        import httpx

        return httpx.Response(
            200,
            json=json.loads(FIXTURE.read_text(encoding="utf-8")),
            request=httpx.Request(method, url),
        )


ALL = WallexRestClient(transport=_Replay()).get_markets()
PRICED = [m for m in ALL if m.price is not None]
UNPRICED = [m for m in ALL if m.price is None]
BY_SYMBOL = {str(m.symbol): m for m in ALL}


def test_the_recorded_list_covers_every_wallex_spot_market():
    assert len(ALL) == 373 and len(PRICED) > 300
    assert {m.quote_asset for m in ALL} == {"TMN", "USDT"}


@pytest.mark.parametrize("market", PRICED, ids=lambda m: str(m.symbol))
def test_every_priced_market_gets_a_valid_grid_that_can_actually_start(market: Market):
    out = suggest_config(market)
    cfg = out["config"]
    grid = cfg["strategy"]["grid"]
    sim = cfg["simulation"]
    price, tick = market.price, D(1).scaleb(-market.price_precision)
    step = D(1).scaleb(-market.amount_precision)

    config = validate_config(cfg)  # includes the fee break-even and min-notional rules
    lower, upper, count = D(grid["lower_price"]), D(grid["upper_price"]), grid["grid_count"]
    assert 0 < lower < price < upper and count >= 3
    assert lower % tick == 0 and upper % tick == 0  # prices the exchange accepts
    assert D(sim["min_quantity"]) == step  # quantities in whole steps
    assert D(grid["total_investment"]) / count >= D(sim["min_notional"])
    assert D(sim["initial_balance_quote"]) >= D(grid["total_investment"])
    assert cfg["market"]["symbol"] == str(market.symbol)

    # and the simulator really starts it: funded, no rejected orders
    setup = GridSetup.from_config(config, market)
    exchange = setup.new_exchange()
    exchange.use_clock(FakeClock())
    session = TradingSession(setup.new_strategy(), exchange)
    session.start(price, 1_000)
    assert session.rejected == 0, session.events
    assert len(exchange.open_orders()) + session.deferred_count >= 2
    for order in exchange.open_orders():
        assert order.quantity % step == 0 and order.price % tick == 0
        assert order.price * order.quantity >= D(sim["min_notional"])


@pytest.mark.parametrize("market", UNPRICED[:5], ids=lambda m: str(m.symbol))
def test_a_market_without_a_price_is_refused_with_a_clear_reason(market):
    with pytest.raises(ValueError, match="no price"):
        suggest_config(market)


def test_the_toman_market_gets_toman_sized_defaults():
    cfg = suggest_config(BY_SYMBOL["USDTTMN"])["config"]
    assert D(cfg["simulation"]["initial_balance_quote"]) >= 2_000_000
    assert D(cfg["simulation"]["min_notional"]) == 90000  # Wallex's own hint for TMN markets
    grid = cfg["strategy"]["grid"]
    spacing_pct = (
        (D(grid["upper_price"]) - D(grid["lower_price"]))
        / (grid["grid_count"] - 1)
        / BY_SYMBOL["USDTTMN"].price
        * 100
    )
    assert D("0.3") < spacing_pct < D("0.8")  # aims at about 0.45% between levels


def test_a_usdt_market_gets_usdt_sized_defaults_and_its_own_precision():
    cfg = suggest_config(BY_SYMBOL["PEPEUSDT"])["config"]
    assert D(cfg["simulation"]["min_notional"]) == 2
    assert D(cfg["simulation"]["initial_balance_quote"]) <= 1000  # tens of USDT, not millions
    assert len(cfg["strategy"]["grid"]["lower_price"].split(".")[1]) == 8  # 8 price decimals
    assert D(cfg["simulation"]["min_quantity"]) == 1  # PEPE trades in whole units


def test_a_huge_price_is_handled():
    cfg = suggest_config(BY_SYMBOL["BTCTMN"])["config"]
    assert D(cfg["strategy"]["grid"]["lower_price"]) > 10**9
    assert D(cfg["simulation"]["min_quantity"]) == D("0.00000001")


def test_a_quiet_coin_and_a_wild_coin_get_different_widths():
    calm = BY_SYMBOL["USDTTMN"]
    wild = max(
        (m for m in PRICED if m.high_24h and m.low_24h),
        key=lambda m: (m.high_24h - m.low_24h) / m.price,
    )

    def width(m: Market) -> D:
        grid = suggest_config(m)["config"]["strategy"]["grid"]
        return (D(grid["upper_price"]) - D(grid["lower_price"])) / m.price

    assert width(wild) > width(calm)
    assert width(wild) <= D("0.11")  # never wider than +-5% (plus rounding)


def test_a_coin_with_a_large_minimum_order_gets_enough_capital_and_says_so():
    big = Market(
        symbol=Symbol("XUSDT"),
        base_asset="X",
        quote_asset="USDT",
        price_precision=2,
        amount_precision=2,
        is_spot=True,
        price=D("100"),
        min_notional_hint=D("50"),
    )
    out = suggest_config(big)
    cfg = out["config"]
    assert (
        D(cfg["strategy"]["grid"]["total_investment"]) >= 50 * cfg["strategy"]["grid"]["grid_count"]
    )
    assert any(n["code"] == "capital_raised" for n in out["notes"])
    validate_config(cfg)
