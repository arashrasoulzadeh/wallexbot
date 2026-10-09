# D5: First Market

## Context
Which market to target first?

## Decision
**USDTTMN** (USDT/TMN) — Tether vs Iranian Toman.

## Rationale
- Highest volume on Wallex spot
- Toman quoted (integer prices, 2 decimals)
- USDT is stablecoin (low base volatility)
- Good for grid: ranging behavior, sufficient volatility
- 2 decimal price precision, 4 decimal amount precision

## Consequences
- All defaults tuned for USDTTMN
- Min notional: 10 TMN
- Min quantity: 0.0001 USDT
- Default capital: 2,000,000 TMN

## Alternatives Considered
- BTCTMN → Higher volatility, larger price moves
- ETHUSDT → USDT quoted, different dynamics