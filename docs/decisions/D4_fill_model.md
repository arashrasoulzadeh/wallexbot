# D4: Fill Model

## Context
How to determine if a limit order fills in backtesting/simulation?

## Decision
**Conservative (trade-through)** as default. **Touch** available as config option for comparison.

## Conservative Model
- BUY fills when trade price < limit price
- SELL fills when trade price > limit price
- Requires price to move through the level

## Touch Model
- BUY fills when trade price ≤ limit price
- SELL fills when trade price ≥ limit price
- Fills on price touch

## Rationale
- Conservative is more realistic for live trading
- Touch provides optimistic bound for comparison
- Configurable for sensitivity analysis

## Consequences
- Conservative: fewer fills, more realistic PnL
- Touch: more fills, optimistic PnL
- Both use same intra-candle path synthesis

## Alternatives Considered
- Volume-weighted fill model → Too complex for v1
- Order book depth simulation → Requires more data