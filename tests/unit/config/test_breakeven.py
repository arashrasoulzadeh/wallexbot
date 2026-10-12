"""Config rules from decisions D11/D16/D17 (see docs/AUDIT.md P1)."""

import copy
from decimal import Decimal as D
from pathlib import Path

import pytest

from wallexbot.config.schema import load_config, validate_config

EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"

BASE = {
    "exchange": {"name": "wallex", "base_url": "https://api.wallex.ir", "ws_url": "wss://api.wallex.ir/ws"},
    "market": {"symbol": "USDTTMN"},
    "strategy": {
        "grid": {
            "lower_price": "262000",
            "upper_price": "266000",
            "grid_count": 6,
            "mode": "arithmetic",
            "total_investment": "2000000",
        }
    },
    "risk": {},
    "simulation": {
        "initial_balance_quote": "2000000",
        "fee_maker": "0.0005",
        "fee_taker": "0.001",
        "min_notional": "90000",
        "min_quantity": "0.01",
    },
    "logging": {},
}


def cfg(**sim_or_grid):
    data = copy.deepcopy(BASE)
    data["simulation"].update(sim_or_grid.get("sim", {}))
    data["strategy"]["grid"].update(sim_or_grid.get("grid", {}))
    return data


def test_valid_usdttmn_config_passes():
    config = validate_config(cfg())
    assert config.market.symbol == "USDTTMN"


def test_spacing_below_fee_breakeven_is_rejected():
    # 262000..266000 with 40 levels => spacing ~103 TMN = 0.039%, round trip maker fee 0.1%
    with pytest.raises(ValueError, match="break-even"):
        validate_config(cfg(grid={"grid_count": 40, "total_investment": "4000000"}))


def test_higher_fees_make_a_previously_valid_grid_invalid():
    validate_config(cfg())
    with pytest.raises(ValueError, match="break-even"):
        validate_config(cfg(sim={"fee_maker": "0.003"}))


def test_per_level_investment_below_min_notional_is_rejected():
    # 2,000,000 / 30 levels = 66,666 TMN per level < 90,000 minimum
    with pytest.raises(ValueError, match="min_notional"):
        validate_config(cfg(grid={"grid_count": 30, "lower_price": "250000", "upper_price": "280000"}))


def test_min_profit_per_cycle_is_spacing_minus_round_trip_fee_on_price():
    config = validate_config(cfg())
    grid = config.strategy["grid"]
    # spacing = 4000 / 5 = 800; mid = 264000; fee on price = 264000 * 2 * 0.0005 = 264
    assert grid.spacing == D("800")
    assert grid.min_profit_per_cycle_after_fees == D("536")


def test_example_config_is_valid_and_targets_usdttmn():
    config = load_config(str(EXAMPLE))
    grid = config.strategy["grid"]
    assert config.market.symbol == "USDTTMN"
    assert D(grid.lower_price) > D("100000")  # Toman prices, not the old 90..110 placeholder
    assert D(config.simulation.min_notional) >= D("90000")
    assert D(config.simulation.initial_balance_quote) == D("2000000")
    assert D(config.risk.max_drawdown) == D("0.05")
    assert D(config.risk.daily_loss_limit) == D("0.02")
