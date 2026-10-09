# D3: Out of Range Policy

## Context
What happens when price moves outside the grid bounds?

## Decision
**Pause and alert** — stop placing new orders, notify user, keep existing orders.

## Rationale
- Grid strategy loses money when price trends beyond range
- Pausing prevents accumulating losing positions
- Alert lets user decide: wait, re-center, or stop
- Conservative default matches risk profile

## Consequences
- Grid stops cycling when price exits range
- User must manually resume or re-center
- Existing orders remain active (may fill if price returns)

## Alternatives Considered
- Hold (keep orders, don't place new) → Similar but no alert
- Re-center automatically → Risky, can accumulate losses
- Stop and cancel all → Too aggressive