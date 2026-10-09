# D1: Partial Fills Policy

## Context
When a grid order is partially filled, how should the counter-order be placed?

## Decision
**Wait for full fill**, then place the counter-order for the full quantity.

## Rationale
- Simpler state management: no partial counter-orders to track
- Avoids dust positions and fragmented orders
- Matches typical grid bot behavior
- Reduces order count (stays within 20/10s rate limit)

## Consequences
- Slower grid cycling in low-liquidity markets
- May miss counter-trade opportunities during partial fills
- Simpler fill handling logic

## Alternatives Considered
- Place counter-order for filled quantity immediately → More complex, more orders
- Configurable policy → Added complexity without clear benefit