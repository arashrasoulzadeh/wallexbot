"""Configuration schema using Pydantic v2."""

from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wallexbot.domain.market import Symbol
from wallexbot.strategy.grid.parameters import GridMode


class ExchangeConfig(BaseModel):
    """Exchange configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = "wallex"
    base_url: str = "https://api.wallex.ir"
    ws_url: str = "wss://api.wallex.ir/ws"

    @field_validator("name")
    @classmethod
    def no_api_key(cls, v: str) -> str:
        """Ensure no API key in exchange config."""
        return v

    @model_validator(mode="after")
    def check_no_secrets(self) -> "ExchangeConfig":
        """Reject any field that looks like a secret."""
        # This is a second line of defense - actual check is in validate_config
        return self


class MarketConfig(BaseModel):
    """Market configuration."""

    model_config = ConfigDict(extra="forbid")

    symbol: str

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        return str(Symbol(v))


class GridStrategyConfig(BaseModel):
    """Grid strategy configuration."""

    model_config = ConfigDict(extra="forbid")

    lower_price: str
    upper_price: str
    grid_count: int = Field(ge=2)
    mode: GridMode = GridMode.ARITHMETIC
    total_investment: str
    per_grid_qty: str | None = None
    stop_loss_price: str | None = None
    take_profit_price: str | None = None

    # Derived values (computed after validation)
    spacing: Decimal | None = Field(default=None, exclude=True)
    levels_count: int | None = Field(default=None, exclude=True)
    per_grid_investment: Decimal | None = Field(default=None, exclude=True)
    min_profit_per_cycle_after_fees: Decimal | None = Field(default=None, exclude=True)
    round_trip_fee_rate: Decimal | None = Field(default=None, exclude=True)
    spacing_pct: Decimal | None = Field(default=None, exclude=True)

    @field_validator(
        "lower_price",
        "upper_price",
        "total_investment",
        "per_grid_qty",
        "stop_loss_price",
        "take_profit_price",
        mode="before",
    )
    @classmethod
    def parse_decimal(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return str(v)

    @model_validator(mode="after")
    def validate_prices(self) -> "GridStrategyConfig":
        lower = Decimal(self.lower_price)
        upper = Decimal(self.upper_price)
        investment = Decimal(self.total_investment)

        if lower >= upper:
            raise ValueError("lower_price must be less than upper_price")
        if investment <= 0:
            raise ValueError("total_investment must be positive")
        if self.per_grid_qty is not None and Decimal(self.per_grid_qty) <= 0:
            raise ValueError("per_grid_qty must be positive")

        return self

    def compute_derived(self, fee_maker: Decimal, fee_taker: Decimal) -> None:
        """Compute derived values."""
        lower = Decimal(self.lower_price)
        upper = Decimal(self.upper_price)
        count = self.grid_count

        # Spacing
        if self.mode == GridMode.ARITHMETIC:
            self.spacing = (upper - lower) / (count - 1)
        else:
            # Geometric: ratio = (upper/lower)^(1/(count-1))
            # Approximate spacing at middle
            ratio = (upper / lower) ** (Decimal("1") / (count - 1))
            mid = lower * (ratio ** (count // 2))
            self.spacing = mid * (ratio - 1)

        self.levels_count = count
        self.per_grid_investment = Decimal(self.total_investment) / count

        # Round-trip cost: a maker fee on the buy and on the sell, both charged on price.
        # Net profit per cycle (per unit of base) = spacing - mid_price * 2 * maker_fee.
        mid_price = (lower + upper) / 2
        self.round_trip_fee_rate = 2 * fee_maker
        self.min_profit_per_cycle_after_fees = self.spacing - mid_price * self.round_trip_fee_rate
        self.spacing_pct = self.spacing / mid_price


class RiskConfig(BaseModel):
    """Risk management configuration."""

    model_config = ConfigDict(extra="forbid")

    max_open_orders: int = Field(default=20, ge=1)
    max_exposure_quote: str = Field(default="1000000")
    max_exposure_base: str = Field(default="10000")
    max_drawdown: str = Field(default="0.05")
    daily_loss_limit: str = Field(default="0.02")

    @field_validator(
        "max_exposure_quote", "max_exposure_base", "max_drawdown", "daily_loss_limit", mode="before"
    )
    @classmethod
    def parse_decimal(cls, v: str) -> str:
        return str(v)


class SimulationConfig(BaseModel):
    """Simulation configuration."""

    model_config = ConfigDict(extra="forbid")

    initial_balance_quote: str
    initial_balance_base: str = "0"
    fee_maker: str = "0.001"
    fee_taker: str = "0.002"
    min_notional: str = "10.00"
    min_quantity: str = "0.0001"
    fill_model: str = "conservative"  # "conservative" or "touch"

    @field_validator(
        "initial_balance_quote",
        "initial_balance_base",
        "fee_maker",
        "fee_taker",
        "min_notional",
        "min_quantity",
        mode="before",
    )
    @classmethod
    def parse_decimal(cls, v: str) -> str:
        return str(v)

    @field_validator("fill_model")
    @classmethod
    def validate_fill_model(cls, v: str) -> str:
        if v not in ("conservative", "touch"):
            raise ValueError("fill_model must be 'conservative' or 'touch'")
        return v


class LoggingConfig(BaseModel):
    """Logging configuration."""

    model_config = ConfigDict(extra="forbid")

    level: str = "INFO"
    json: bool = True
    file: str | None = None


class Config(BaseModel):
    """Root configuration."""

    model_config = ConfigDict(extra="forbid")

    exchange: ExchangeConfig
    market: MarketConfig
    strategy: dict[str, GridStrategyConfig]  # e.g., {"grid": ...}
    risk: RiskConfig
    simulation: SimulationConfig
    logging: LoggingConfig

    @model_validator(mode="after")
    def compute_all_derived(self) -> "Config":
        """Compute all derived values after validation."""
        # Get grid config
        grid_config = self.strategy.get("grid")
        if grid_config:
            maker = Decimal(self.simulation.fee_maker)
            grid_config.compute_derived(
                fee_maker=maker,
                fee_taker=Decimal(self.simulation.fee_taker),
            )
            self._check_grid_is_tradable(grid_config, maker)
        return self

    # Spacing must beat the round-trip fee by this factor (safety margin for slippage, rounding).
    BREAKEVEN_MARGIN: ClassVar[Decimal] = Decimal("1.5")

    def _check_grid_is_tradable(self, grid: "GridStrategyConfig", maker: Decimal) -> None:
        """Reject grids that cannot profit after fees or whose orders are too small (D11, D16)."""
        assert grid.spacing_pct is not None and grid.round_trip_fee_rate is not None
        required = grid.round_trip_fee_rate * self.BREAKEVEN_MARGIN
        if grid.spacing_pct < required:
            raise ValueError(
                f"grid spacing {grid.spacing_pct:.4%} is below break-even "
                f"{required:.4%} (round-trip maker fee {grid.round_trip_fee_rate:.4%} "
                f"x {self.BREAKEVEN_MARGIN} margin): use fewer levels, a wider range, or check fee_maker"
            )
        if grid.per_grid_qty is None:
            min_notional = Decimal(self.simulation.min_notional)
            per_level = Decimal(grid.total_investment) / grid.grid_count
            if per_level < min_notional:
                raise ValueError(
                    f"investment per level {per_level:.2f} is below min_notional "
                    f"{min_notional}: use fewer levels or more capital"
                )


def validate_config(data: dict[str, Any], env_overrides: bool = False) -> Config:
    """
    Validate configuration dictionary.

    Args:
        data: Parsed YAML config
        env_overrides: Whether to apply environment variable overrides

    Returns:
        Validated Config object

    Raises:
        ValueError: If config is invalid
    """
    # Apply env overrides if requested
    if env_overrides:
        data = _apply_env_overrides(data)

    # Check for forbidden keys (api_key, secret, etc.)
    _check_forbidden_keys(data)

    return Config.model_validate(data)


def _apply_env_overrides(data: dict[str, Any]) -> dict:
    """Apply environment variable overrides to config."""
    import os

    # Map of env var to config path
    env_mapping = {
        "WALLEXBOT_EXCHANGE_BASE_URL": ("exchange", "base_url"),
        "WALLEXBOT_EXCHANGE_WS_URL": ("exchange", "ws_url"),
        "WALLEXBOT_MARKET_SYMBOL": ("market", "symbol"),
        "WALLEXBOT_STRATEGY_GRID_LOWER_PRICE": ("strategy", "grid", "lower_price"),
        "WALLEXBOT_STRATEGY_GRID_UPPER_PRICE": ("strategy", "grid", "upper_price"),
        "WALLEXBOT_STRATEGY_GRID_GRID_COUNT": ("strategy", "grid", "grid_count"),
        "WALLEXBOT_STRATEGY_GRID_MODE": ("strategy", "grid", "mode"),
        "WALLEXBOT_STRATEGY_GRID_TOTAL_INVESTMENT": ("strategy", "grid", "total_investment"),
        "WALLEXBOT_RISK_MAX_OPEN_ORDERS": ("risk", "max_open_orders"),
        "WALLEXBOT_SIMULATION_INITIAL_BALANCE_QUOTE": ("simulation", "initial_balance_quote"),
        "WALLEXBOT_LOGGING_LEVEL": ("logging", "level"),
    }

    result = data.copy()
    for env_var, path in env_mapping.items():
        value = os.environ.get(env_var)
        if value is not None:
            _set_nested(result, path, value)

    return result


def _set_nested(d: dict[str, Any], path: tuple[Any, ...], value: Any) -> None:
    """Set nested dictionary value."""
    current = d
    for key in path[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[path[-1]] = value


def _check_forbidden_keys(data: dict[str, Any], prefix: str = "") -> None:
    """Recursively check for forbidden keys (api_key, secret, etc.)."""
    forbidden = {"api_key", "secret", "apikey", "api_secret", "private_key", "password"}

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if key.lower() in forbidden:
            raise ValueError(
                f"Forbidden key in config: {full_key} (no API keys allowed in this version)"
            )
        if isinstance(value, dict):
            _check_forbidden_keys(value, full_key)


def load_config(path: str | Path) -> Config:
    """Load configuration from YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return validate_config(data)
