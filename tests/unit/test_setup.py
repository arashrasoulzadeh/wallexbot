"""GridSetup: a validated Config plus real market info becomes the objects a run needs."""

from decimal import Decimal as D
from pathlib import Path

from tests.helpers.wallex_fakes import FakeClient
from wallexbot.config.schema import load_config
from wallexbot.setup import GridSetup, find_market

EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "grid.example.yaml"


def make_setup() -> GridSetup:
    config = load_config(str(EXAMPLE))
    info = find_market(FakeClient(), "USDTTMN")
    assert info is not None
    return GridSetup.from_config(config, info)


def test_find_market_by_symbol():
    assert find_market(FakeClient(), "USDTTMN") is not None
    assert find_market(FakeClient(), "NOPE") is None


def test_precisions_come_from_the_real_market_not_from_the_config():
    setup = make_setup()
    assert (setup.market.price_precision, setup.market.amount_precision) == (0, 2)
    assert (setup.market.base, setup.market.quote) == ("USDT", "TMN")


def test_values_from_the_config_end_up_in_the_right_places():
    setup = make_setup()
    assert setup.params.grid_count == 5 and setup.params.lower_price == D("255000")
    assert (setup.maker, setup.taker) == (D("0.0035"), D("0.0035"))
    assert setup.risk.max_drawdown == D("0.05") and setup.risk.daily_loss_limit == D("0.02")


def test_a_fresh_exchange_and_strategy_each_time():
    setup = make_setup()
    a, b = setup.new_exchange(), setup.new_exchange()
    assert a is not b
    assert a.balances()["TMN"].free == D("2000000") and a.balances()["USDT"].free == 0
    assert setup.new_strategy() is not setup.new_strategy()
