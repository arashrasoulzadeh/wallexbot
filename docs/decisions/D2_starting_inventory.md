# D2: Starting Inventory

## Context
Grid requires base asset for initial sell orders. How to acquire it?

## Decision
**Simulated market buy** of the base needed for sell levels at start.

## Rationale
- Ensures grid can start immediately with full sell ladder
- Simulates realistic user behavior (buy base first, then grid)
- No manual intervention needed
- Paper trading only — no real funds at risk

## Consequences
- Initial quote balance reduced by simulated buy cost
- Simulated fill at current market price (with slippage model)
- Fees applied to simulated buy

## Alternatives Considered
- Start with only buy orders, add sells after first buy fills → Slower start, asymmetric grid
- Require user to hold base asset → Manual step, not fully automated
- Configurable option → Added complexity