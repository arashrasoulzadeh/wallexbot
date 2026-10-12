"""Turn a validated Config plus real market info into the objects a run needs.

Shared by the CLI (`backtest`, `paper`) and the web API so that every entry point builds a run
the same way.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from wallexbot.config.schema import Config
from wallexbot.domain.balance import Balance
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.domain.market import Market, Symbol
from wallexbot.engine.risk import RiskMonitor
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridParameters
from wallexbot.wallex.models import Market as WallexMarket


class MarketSource(Protocol):
    def get_markets(self) -> list[WallexMarket]: ...


def find_market(client: MarketSource, symbol: str) -> WallexMarket | None:
    """The spot market with this symbol, or None."""
    return next((m for m in client.get_markets() if str(m.symbol) == symbol), None)


@dataclass
class GridSetup:
    """Everything needed to start a backtest or a paper run for one configured grid."""

    symbol: str
    market: Market
    params: GridParameters
    fees: FeeSchedule
    min_rule: MinNotionalRule
    maker: Decimal
    taker: Decimal
    min_notional: Decimal
    risk: RiskMonitor
    initial_quote: Decimal
    initial_base: Decimal

    @classmethod
    def from_config(cls, config: Config, info: WallexMarket) -> "GridSetup":
        """Combine the config with the market's real precisions and assets."""
        symbol = str(config.market.symbol)
        grid = config.strategy["grid"]
        sim = config.simulation
        maker, taker = Decimal(sim.fee_maker), Decimal(sim.fee_taker)
        min_notional = Decimal(sim.min_notional)
        return cls(
            symbol=symbol,
            market=Market(
                symbol=Symbol(symbol),
                base=info.base_asset,
                quote=info.quote_asset,
                price_precision=info.price_precision,
                amount_precision=info.amount_precision,
                is_spot=info.is_spot,
            ),
            params=GridParameters(
                lower_price=Decimal(grid.lower_price),
                upper_price=Decimal(grid.upper_price),
                grid_count=grid.grid_count,
                mode=grid.mode,
                total_investment=Decimal(grid.total_investment),
            ),
            fees=FeeSchedule(maker_rate=maker, taker_rate=taker),
            min_rule=MinNotionalRule(
                min_notional=min_notional, min_quantity=Decimal(sim.min_quantity)
            ),
            maker=maker,
            taker=taker,
            min_notional=min_notional,
            risk=RiskMonitor(
                max_drawdown=Decimal(config.risk.max_drawdown),
                daily_loss_limit=Decimal(config.risk.daily_loss_limit),
            ),
            initial_quote=Decimal(sim.initial_balance_quote),
            initial_base=Decimal(sim.initial_balance_base),
        )

    def new_exchange(self) -> SimulatedExchange:
        """A fresh simulated exchange holding the configured starting balances."""
        return SimulatedExchange(
            market=self.market,
            fee_schedule_config=self.fees,
            min_notional_rule=self.min_rule,
            initial_balances={
                self.market.quote: Balance(free=self.initial_quote, locked=Decimal(0)),
                self.market.base: Balance(free=self.initial_base, locked=Decimal(0)),
            },
        )

    def new_strategy(self) -> GridStrategy:
        """A fresh grid strategy using the configured fees and minimum order size."""
        return GridStrategy(
            self.market, self.params, fee_schedule=self.fees, min_notional_rule=self.min_rule
        )
