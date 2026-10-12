"""Analytics API endpoints."""


from fastapi import APIRouter, Query

from wallexbot.analytics.history import HistoryRepository

router = APIRouter(prefix="/api/history", tags=["history"])

# Global history repository (initialized on startup)
_history_repo: HistoryRepository | None = None


def get_history_repo() -> HistoryRepository:
    global _history_repo
    if _history_repo is None:
        _history_repo = HistoryRepository("wallexbot_history.db")
    return _history_repo


@router.get("/prices")
async def get_prices(
    market: str = Query(...),
    from_ts: int = Query(...),
    to_ts: int = Query(...),
    run_id: str | None = Query(None),
    limit: int = Query(1000),
):
    repo = get_history_repo()
    ticks = repo.get_price_ticks(market, from_ts, to_ts)
    return ticks[:limit]


@router.get("/trades")
async def get_trades(
    market: str = Query(...),
    from_ts: int = Query(...),
    to_ts: int = Query(...),
    limit: int = Query(1000),
):
    _repo = get_history_repo()  # TODO: stub endpoint, not yet backed by the history store
    # Implementation would query market_trades table
    return []


@router.get("/candles")
async def get_candles(
    market: str = Query(...),
    resolution: str = Query("60"),
    from_ts: int = Query(...),
    to_ts: int = Query(...),
):
    repo = get_history_repo()
    candles = repo.get_candles(market, resolution, from_ts, to_ts)
    return candles


@router.get("/orders")
async def get_orders(
    run_id: str = Query(...),
    from_ts: int | None = Query(None),
    to_ts: int | None = Query(None),
):
    _repo = get_history_repo()  # TODO: stub endpoint, not yet backed by the history store
    # Implementation would query orders table
    return []


@router.get("/fills")
async def get_fills(
    run_id: str = Query(...),
    from_ts: int | None = Query(None),
    to_ts: int | None = Query(None),
):
    _repo = get_history_repo()  # TODO: stub endpoint, not yet backed by the history store
    # Implementation would query fills table
    return []


@router.get("/cycles")
async def get_cycles(
    run_id: str = Query(...),
):
    _repo = get_history_repo()  # TODO: stub endpoint, not yet backed by the history store
    # Implementation would query grid_cycles table
    return []


@router.get("/balances")
async def get_balances(
    run_id: str = Query(...),
    from_ts: int | None = Query(None),
    to_ts: int | None = Query(None),
):
    _repo = get_history_repo()  # TODO: stub endpoint, not yet backed by the history store
    # Implementation would query balance_snapshots table
    return []


@router.get("/pnl")
async def get_pnl(
    run_id: str = Query(...),
    resolution: str = Query("1h"),
):
    repo = get_history_repo()
    pnl = repo.get_pnl_timeseries(run_id, resolution)
    return pnl


@router.get("/events")
async def get_events(
    run_id: str = Query(...),
    from_ts: int | None = Query(None),
    to_ts: int | None = Query(None),
):
    _repo = get_history_repo()  # TODO: stub endpoint, not yet backed by the history store
    # Implementation would query run_events table
    return []


@router.get("/breakdown")
async def get_breakdown(run_id: str = Query(...)):
    repo = get_history_repo()
    return repo.get_profit_breakdown(run_id)


@router.get("/drawdown")
async def get_drawdown(run_id: str = Query(...)):
    repo = get_history_repo()
    return repo.get_drawdown_series(run_id)


@router.get("/stats")
async def get_stats(run_id: str = Query(...)):
    repo = get_history_repo()
    return repo.get_trade_stats(run_id)


@router.get("/reconstruct")
async def reconstruct_state(
    run_id: str = Query(...),
    ts: int = Query(...),
):
    repo = get_history_repo()
    return repo.reconstruct_state_at(run_id, ts)
