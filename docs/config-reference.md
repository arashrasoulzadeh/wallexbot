# Configuration Reference

All configuration is in YAML format. See `config/grid.example.yaml` for a complete example.

## exchange

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| name | string | "wallex" | Exchange name |
| base_url | string | "https://api.wallex.ir" | REST API base URL |
| ws_url | string | "wss://api.wallex.ir/ws" | WebSocket URL |

## market

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| symbol | string | Yes | Trading pair (e.g., USDTTMN) |

## strategy.grid

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| lower_price | string | Yes | - | Grid lower bound |
| upper_price | string | Yes | - | Grid upper bound |
| grid_count | integer | Yes | - | Number of levels (≥2) |
| mode | string | No | "arithmetic" | "arithmetic" or "geometric" |
| total_investment | string | Yes | - | Quote currency to invest |
| per_grid_qty | string | No | - | Fixed base quantity per level instead of splitting `total_investment` evenly (the minimum-order check is then up to the exchange) |
| stop_loss_price | string | No | - | Must be below `lower_price`. When the price falls to this, the run logs a pause event and sends an alert. It does not sell anything |
| take_profit_price | string | No | - | Must be above `upper_price`. Same, when the price rises to this |
| recenter_after_minutes | integer ≥ 1 | No | off | Paper only: once the price has stayed outside the range this long, rebuild the grid (same width, or same ratio for geometric) around the price, at most once an hour. See paper-trading.md |

## risk

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| max_open_orders | integer | 20 | Max concurrent orders |
| max_exposure_quote | string | "1000000" | Max quote exposure |
| max_exposure_base | string | "10000" | Max base exposure |
| max_drawdown | string | "0.05" | Max drawdown (5%) |
| daily_loss_limit | string | "0.02" | Daily loss limit (2%) |

## simulation

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| initial_balance_quote | string | "2000000.00" | Initial quote balance |
| initial_balance_base | string | "0.00" | Initial base balance |
| fee_maker | string | "0.001" | Maker fee rate |
| fee_taker | string | "0.002" | Taker fee rate |
| min_notional | string | "10.00" | Minimum notional |
| min_quantity | string | "0.0001" | Minimum quantity |
| fill_model | string | "conservative" | "conservative" or "touch" |

## logging

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| level | string | "INFO" | Log level |
| json | boolean | true | JSON output |
| file | string | null | Log file path |

## Derived Values

After validation, the following derived values are computed:

- `spacing`: Price spacing between levels
- `levels_count`: Number of grid levels
- `per_grid_investment`: Investment per level
- `min_profit_per_cycle_after_fees`: Minimum profit per cycle after fees

## Environment Overrides

Precedence: CLI args > Environment variables > Config file

| Env Var | Config Path |
|---------|-------------|
| WALLEXBOT_EXCHANGE_BASE_URL | exchange.base_url |
| WALLEXBOT_MARKET_SYMBOL | market.symbol |
| WALLEXBOT_STRATEGY_GRID_LOWER_PRICE | strategy.grid.lower_price |
| WALLEXBOT_STRATEGY_GRID_UPPER_PRICE | strategy.grid.upper_price |
| WALLEXBOT_STRATEGY_GRID_GRID_COUNT | strategy.grid.grid_count |
| WALLEXBOT_STRATEGY_GRID_MODE | strategy.grid.mode |
| WALLEXBOT_STRATEGY_GRID_TOTAL_INVESTMENT | strategy.grid.total_investment |
| WALLEXBOT_RISK_MAX_OPEN_ORDERS | risk.max_open_orders |
| WALLEXBOT_SIMULATION_INITIAL_BALANCE_QUOTE | simulation.initial_balance_quote |
| WALLEXBOT_LOGGING_LEVEL | logging.level |

## Forbidden Keys

The following keys are rejected anywhere in config:
- `api_key`, `secret`, `apikey`, `api_secret`, `private_key`, `password`