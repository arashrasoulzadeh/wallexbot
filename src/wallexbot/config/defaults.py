"""Default configuration shown by the UI.

Mirrors config/grid.example.yaml (a test keeps the two in sync). The fee and minimum-order values
are placeholders: the real Wallex fee tier and spot minimum are not public.
"""

import copy
from typing import Any

_DEFAULT: dict[str, Any] = {
    "exchange": {
        "name": "wallex",
        "base_url": "https://api.wallex.ir",
        "ws_url": "wss://api.wallex.ir/ws",
    },
    "market": {"symbol": "USDTTMN"},
    "strategy": {
        "grid": {
            "lower_price": "261000",
            "upper_price": "267000",
            "grid_count": 6,
            "mode": "arithmetic",
            "total_investment": "2000000",
        }
    },
    "risk": {
        "max_open_orders": 20,
        "max_exposure_quote": "2000000",
        "max_exposure_base": "20",
        "max_drawdown": "0.05",
        "daily_loss_limit": "0.02",
    },
    "simulation": {
        "initial_balance_quote": "2000000",
        "initial_balance_base": "0.00",
        "fee_maker": "0.0005",
        "fee_taker": "0.001",
        "min_notional": "90000",
        "min_quantity": "0.01",
        "fill_model": "conservative",
    },
    "logging": {"level": "INFO", "json": True},
}


def default_config() -> dict[str, Any]:
    """A fresh copy of the default config."""
    return copy.deepcopy(_DEFAULT)
