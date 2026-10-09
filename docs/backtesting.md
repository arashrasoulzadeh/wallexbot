# Backtesting

## Fill Models

### Conservative (Default)
Order fills only when a trade executes **through** the limit price.
- BUY fills when trade price < limit price
- SELL fills when trade price > limit price

This is more realistic as it accounts for the fact that being at the limit price doesn't guarantee a fill.

### Touch
Order fills when trade price **touches** the limit price.
- BUY fills when trade price ≤ limit price
- SELL fills when trade price ≥ limit price

More optimistic, useful for comparison.

## Intra-Candle Path

Candles are replayed by synthesizing an intra-candle path:
1. Open price
2. High/Low (in pessimistic order for conservative model)
3. Close price

For conservative fill model:
- BUY orders: Low → High (fills on way down)
- SELL orders: High → Low (fills on way up)

This ensures fills only happen when price moves through the limit.

## Known Limitations

1. **No order book depth**: Market orders use simplified model
2. **No partial fill queue**: FIFO within same price
3. **No latency simulation**: Fills are instantaneous
4. **Conservative fees**: Always uses maker/taker rates from config

## Metrics

| Metric | Description |
|--------|-------------|
| Realized PnL | Closed trade profits minus fees |
| Unrealized PnL | Open position mark-to-market |
| Total Return % | (Equity - Initial) / Initial × 100 |
| Completed Cycles | Buy→Sell round trips |
| Avg Profit/Cycle | Realized PnL / Cycles |
| Max Drawdown | Peak-to-trough equity drop |
| Fees Paid | Total fees in quote currency |
| Time in Range % | % of time price within grid |
| vs Buy & Hold | Outperformance vs buy-and-hold |

## Sanity Checks

- Pure sideways market must show profit
- Strong trend must show grid weakness (accumulating losing side)
- Results must be deterministic (same input → same output)