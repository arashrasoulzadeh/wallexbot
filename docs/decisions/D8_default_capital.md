# D8: Default Paper Capital

## Context
Default capital for paper trading.

## Decision
**2,000,000 TMN** (configurable).

## Rationale
- ~$20 USD equivalent — meaningful but not risky
- Allows 20+ grid levels with 10 TMN min notional
- Fits typical retail trader budget in Iran
- Paper trading only — no real money at risk

## Consequences
- Default config uses 2M TMN
- User can override in config or CLI
- Sufficient for testing grid behavior

## Alternatives Considered
- 1M TMN → Too few grid levels
- 10M TMN → Too large for typical testing