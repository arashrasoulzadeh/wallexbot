# D12: Risk Profile Default

## Context
Default risk parameters.

## Decision
**Conservative**: max drawdown 5%, daily loss limit 2%, wider spacing, fewer grids.

## Rationale
- Paper trading should be safe by default
- 5% drawdown = 100k TMN on 2M capital — recoverable
- 2% daily loss = 40k TMN — limits single bad day
- Wider spacing = fewer trades, less fee drag, more profit per cycle
- All configurable

## Consequences
- Default config uses conservative values
- User can switch to aggressive profile
- Risk guards enforce limits at runtime

## Alternatives Considered
- Aggressive (10% drawdown, 5% daily) → Too risky for defaults
- Balanced (7.5% / 3%) → Still conservative-leaning