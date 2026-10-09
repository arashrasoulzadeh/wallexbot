# D13: Retention

## Context
Data retention policy for history database.

## Decision
- **90 days** of 1m candles
- **14 days** raw ticks then roll up to 1s/1m bars
- **Forever**: fills, orders, PnL, events

## Rationale
- 90 days candles = sufficient for backtesting/analysis
- 14 days raw ticks = enough for intraday analysis
- Rolls up to save space (1m bars instead of ticks)
- Fills/orders/PnL/events = audit trail, never delete

## Consequences
- Background job rolls up ticks daily
- DB size stays bounded
- Full replay always possible from fills/orders

## Alternatives Considered
- Keep all raw ticks → Unbounded growth
- Delete old fills → Breaks audit/reconciliation