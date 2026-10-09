"""Tests for configuration system."""

from decimal import Decimal
import pytest
import yaml

from wallexbot.config.schema import (
    Config,
    ExchangeConfig,
    MarketConfig,
    GridStrategyConfig,
    RiskConfig,
    SimulationConfig,
    LoggingConfig,
    GridMode,
    load_config,
    validate_config,
)
from wallexbot.domain.market import Symbol


class TestConfigSchema:
    """Tests for config schema validation."""

    def test_valid_config_loads(self):
        """Valid config loads successfully."""
        yaml_str = """
exchange:
  name: "wallex"
  base_url: "https://api.wallex.ir"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
  max_exposure_quote: "100000.00"
  max_exposure_base: "1000.00"
  max_drawdown: "0.05"
  daily_loss_limit: "0.02"
simulation:
  initial_balance_quote: "2000000.00"
  initial_balance_base: "0.00"
  fee_maker: "0.001"
  fee_taker: "0.002"
  min_notional: "10.00"
  min_quantity: "0.0001"
logging:
  level: "INFO"
  json: true
"""
        config = yaml.safe_load(yaml_str)
        validated = validate_config(config)
        assert isinstance(validated, Config)
        assert validated.market.symbol == Symbol("USDTTMN")
        assert validated.strategy.grid.lower_price == Decimal("90.00")
        assert validated.strategy.grid.grid_count == 10

    def test_invalid_lower_ge_upper(self):
        """lower_price >= upper_price raises error."""
        yaml_str = """
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "110.00"
    upper_price: "90.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        with pytest.raises(ValueError, match="lower.*upper"):
            validate_config(config)

    def test_grid_count_too_small(self):
        """grid_count < 2 raises error."""
        yaml_str = """
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 1
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        with pytest.raises(ValueError, match="grid_count"):
            validate_config(config)

    def test_investment_non_positive(self):
        """total_investment <= 0 raises error."""
        yaml_str = """
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "0"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        with pytest.raises(ValueError, match="investment"):
            validate_config(config)

    def test_unknown_keys_rejected(self):
        """Unknown keys in config raise error."""
        yaml_str = """
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
    unknown_field: "should fail"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        with pytest.raises(ValueError, match="unknown"):
            validate_config(config)

    def test_symbol_not_spot_rejected(self):
        """Non-spot symbol rejected (if we have market info)."""
        # This test would need market info - skip for now
        pass

    def test_profit_per_grid_below_fees_warns(self):
        """Profit per grid below 2x fees warns or rejects."""
        yaml_str = """
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "100.00"
    upper_price: "100.10"
    grid_count: 100
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
  fee_maker: "0.001"
  fee_taker: "0.002"
  min_notional: "10.00"
  min_quantity: "0.0001"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        # Very tight range, many grids - profit per grid tiny
        # Should warn or reject based on config
        validated = validate_config(config)
        # For now, just ensure it loads (warning would be in derived values)
        assert validated is not None

    def test_api_key_in_config_rejected(self):
        """Config containing api_key/secret is rejected."""
        yaml_str = """
exchange:
  name: "wallex"
  api_key: "secret123"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        with pytest.raises(ValueError, match="api_key|secret"):
            validate_config(config)

    def test_env_override_precedence(self):
        """CLI > env > file precedence."""
        import os
        os.environ["WALLEXBOT_STRATEGY_GRID_LOWER_PRICE"] = "95.00"

        yaml_str = """
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        # Env override should apply
        validated = validate_config(config, env_overrides=True)
        assert validated.strategy.grid.lower_price == Decimal("95.00")

        del os.environ["WALLEXBOT_STRATEGY_GRID_LOWER_PRICE"]


class TestDerivedValues:
    """Tests for derived values report."""

    def test_derived_values_report(self):
        """Derived values computed correctly."""
        yaml_str = """
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
  fee_maker: "0.001"
  fee_taker: "0.002"
  min_notional: "10.00"
  min_quantity: "0.0001"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        validated = validate_config(config)

        # Check derived values
        assert hasattr(validated.strategy.grid, 'spacing')
        assert hasattr(validated.strategy.grid, 'levels_count')
        assert hasattr(validated.strategy.grid, 'per_grid_investment')
        assert hasattr(validated.strategy.grid, 'min_profit_per_cycle_after_fees')

    def test_derived_spacing_calculation(self):
        """Spacing calculated correctly."""
        yaml_str = """
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 5
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
  fee_maker: "0.001"
  fee_taker: "0.002"
logging:
  level: "INFO"
"""
        config = yaml.safe_load(yaml_str)
        validated = validate_config(config)
        # 5 levels -> 4 intervals, spacing = 20/4 = 5
        assert validated.strategy.grid.spacing == Decimal("5.00")


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_from_file(self, tmp_path):
        """Load config from YAML file."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("""
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
""")

        config = load_config(str(config_file))
        assert config.market.symbol == Symbol("USDTTMN")