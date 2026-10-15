"""Stop-loss and take-profit must sit outside the grid, or they would fire the moment the run starts."""

from pathlib import Path

import pytest

from wallexbot.config.schema import load_config, validate_config

EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"  # grid 255000-275000


def raw(**grid):
    cfg = load_config(str(EXAMPLE)).model_dump(mode="json", by_alias=True)
    cfg["strategy"]["grid"].update(grid)
    return cfg


def test_levels_outside_the_grid_are_accepted():
    config = validate_config(raw(stop_loss_price="240000", take_profit_price="290000"))
    grid = config.strategy["grid"]
    assert grid.stop_loss_price == "240000" and grid.take_profit_price == "290000"


def test_they_are_optional_and_can_be_set_alone():
    validate_config(raw(stop_loss_price="240000"))
    validate_config(raw(take_profit_price="290000"))
    validate_config(raw())


@pytest.mark.parametrize("level", ["255000", "260000", "300000"])  # at, inside and above the grid
def test_a_stop_loss_must_be_below_the_grid(level):
    with pytest.raises(ValueError, match="stop_loss_price must be below"):
        validate_config(raw(stop_loss_price=level))


@pytest.mark.parametrize("level", ["275000", "270000", "100000"])
def test_a_take_profit_must_be_above_the_grid(level):
    with pytest.raises(ValueError, match="take_profit_price must be above"):
        validate_config(raw(take_profit_price=level))


@pytest.mark.parametrize("field", ["stop_loss_price", "take_profit_price"])
def test_levels_must_be_positive_numbers(field):
    with pytest.raises(ValueError, match="must be a positive number"):
        validate_config(raw(**{field: "0"}))
    with pytest.raises(ValueError, match="must be a positive number"):
        validate_config(raw(**{field: "abc"}))
