"""Strategy plugin registry."""

from typing: Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel

from wallexbot.strategy.grid.interface import GridStrategy, Action
from wallexbot.strategy.grid.parameters import GridParameters
from wallexbot.domain.market import Market
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule


class StrategyPlugin(ABC):
    """Base class for strategy plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name."""
        pass

    @property
    @abstractmethod
    def params_model(self) -> type[BaseModel]:
        """Pydantic model for strategy parameters."""
        pass

    @abstractmethod
    def create_strategy(self, market: Market, params: GridParameters) -> GridStrategy:
        """Create strategy instance."""
        pass


class StrategyRegistry:
    """Registry for strategy plugins."""

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyPlugin] = {}

    def register(self, name: str):
        """Decorator to register a strategy."""
        def decorator(cls):
            plugin = cls()
            self._strategies[name] = plugin
            return cls
        return decorator

    def get(self, name: str) -> Optional[StrategyPlugin]:
        """Get strategy plugin by name."""
        return self._strategies.get(name)

    def get_params_model(self, name: str) -> Optional[type[BaseModel]]:
        """Get params model for strategy."""
        plugin = self._strategies.get(name)
        if plugin:
            return plugin.params_model
        return None

    def list_strategies(self) -> list[str]:
        """List registered strategy names."""
        return list(self._strategies.keys())

    def create_strategy(self, name: str, market: Market, params: GridParameters) -> Optional[GridStrategy]:
        """Create strategy instance."""
        plugin = self._strategies.get(name)
        if plugin:
            return plugin.create_strategy(market, params)
        return None

    def run_contract_tests(self, name: str) -> list[str]:
        """Run contract tests for a strategy."""
        errors = []
        plugin = self._strategies.get(name)
        if not plugin:
            return [f"Strategy {name} not found"]

        # Test required methods exist
        required_methods = ["on_start", "on_price", "on_fill", "on_stop"]
        for method in required_methods:
            if not hasattr(plugin, method):
                errors.append(f"Missing required method: {method}")

        # Test strategy instantiation
        try:
            market = Market(
                symbol="USDTTMN",
                base="USDT",
                quote="TMN",
                price_precision=2,
                amount_precision=4,
                is_spot=True,
            )
            params = GridParameters(
                lower_price=90,
                upper_price=110,
                grid_count=10,
                mode="arithmetic",
                total_investment=10000,
            )
            strategy = plugin.create_strategy(market, params)

            # Test method signatures
            actions = strategy.on_start(current_price=100, timestamp=0)
            assert isinstance(actions, list)

            actions = strategy.on_price(current_price=100, timestamp=0)
            assert isinstance(actions, list)

            actions = strategy.on_fill(level_index=0, fill_qty=1, fill_fee=0.01, fill_fee_asset="TMN", timestamp=0)
            assert isinstance(actions, list)

            actions = strategy.on_stop(timestamp=0)
            assert isinstance(actions, list)

        except Exception as e:
            errors.append(f"Contract test failed: {e}")

        return errors


# Global registry
registry = StrategyRegistry()


# Register built-in grid strategy
@registry.register("grid")
class GridStrategyPlugin(StrategyPlugin):
    @property
    def name(self) -> str:
        return "grid"

    @property
    def params_model(self) -> type[BaseModel]:
        from wallexbot.config.schema import GridStrategyConfig
        return GridStrategyConfig

    def create_strategy(self, market: Market, params: GridParameters) -> GridStrategy:
        return GridStrategy(market=market, params=params)