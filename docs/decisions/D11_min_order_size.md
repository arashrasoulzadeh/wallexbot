# D11: Min Order Size Verification

## Context
Wallex doesn't publish min order size. Need empirical verification.

## Decision
Verify empirically from public market data or support.

## Rationale
- Min order size affects grid_count viability
- With 2M TMN capital, need enough levels for profitable spacing
- If min order is too large, grid_count must be reduced

## Verification Method
1. Check public trades for smallest quantities
2. Check order book depth for smallest levels
3. Contact Wallex support if needed
4. Document in config reference

## Consequences
- Config validation warns if per-grid qty below empirical min
- Default grid_count (20) may need adjustment
- User can override per_grid_qty if known

## Status
**Open** — pending verification at Phase 3.