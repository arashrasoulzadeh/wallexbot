"""Market status: neutral facts about the price, the grid and the order book (no buy/sell verdict)."""

from decimal import Decimal as D

from wallexbot.analytics.market_status import (
    build_market_status,
    change_over,
    depth_summary,
    grid_position,
    price_trend,
)
from wallexbot.domain.market import Symbol
from wallexbot.strategy.grid.parameters import GridMode, GridParameters
from wallexbot.wallex.models import Candle, Depth, OrderBookLevel

SYMBOL = Symbol("USDTTMN")
PARAMS = GridParameters(
    lower_price=D("261000"),
    upper_price=D("267000"),
    grid_count=6,
    mode=GridMode.ARITHMETIC,
    total_investment=D("2000000"),
)  # levels: 261000 262200 263400 264600 265800 267000


def candle(
    minute: int,
    close: str,
    high: str | None = None,
    low: str | None = None,
    open_: str | None = None,
) -> Candle:
    c = D(close)
    return Candle(
        symbol=SYMBOL,
        resolution="1",
        open_time=1_700_000_000 + minute * 60,
        open=D(open_) if open_ else c,
        high=D(high) if high else c,
        low=D(low) if low else c,
        close=c,
        volume=D(1),
    )


def series(closes: list[str]) -> list[Candle]:
    return [candle(i, c) for i, c in enumerate(closes)]


class TestGridPosition:
    def test_inside_the_range_with_the_neighbouring_levels(self):
        g = grid_position(D("264000"), PARAMS, price_precision=0)
        assert g["state"] == "inside" and g["levels"] == 6
        assert g["position_pct"] == D(50)  # (264000-261000)/6000
        assert g["next_buy"]["price"] == D("263400") and g["next_buy"]["distance"] == D(600)
        assert g["next_buy"]["distance_pct"] == D(600) / D(264000) * 100
        assert g["next_sell"]["price"] == D("264600") and g["next_sell"]["distance"] == D(600)
        assert g["spacing"] == D(1200)

    def test_standing_exactly_on_a_level_looks_for_the_next_ones_either_side(self):
        g = grid_position(D("263400"), PARAMS, price_precision=0)
        assert g["next_buy"]["price"] == D("262200") and g["next_sell"]["price"] == D("264600")

    def test_below_the_grid_there_is_no_buy_level_left_below(self):
        g = grid_position(D("260000"), PARAMS, price_precision=0)
        assert g["state"] == "below" and g["next_buy"] is None
        assert g["next_sell"]["price"] == D("261000") and g["position_pct"] == D(0)

    def test_above_the_grid_there_is_no_sell_level_left_above(self):
        g = grid_position(D("268000"), PARAMS, price_precision=0)
        assert g["state"] == "above" and g["next_sell"] is None
        assert g["next_buy"]["price"] == D("267000") and g["position_pct"] == D(100)


class TestChanges:
    def test_change_over_the_window_uses_the_oldest_candle_inside_it(self):
        candles = series([str(100 + i) for i in range(121)])  # 100 ... 220, one per minute
        # last hour: from minute 60 (close 160, open 160) to 220
        assert change_over(candles, 3600) == (D(220) - D(160)) / D(160) * 100

    def test_not_enough_history_gives_none_instead_of_a_misleading_number(self):
        assert change_over(series(["100", "101", "102"]), 3600) is None
        assert change_over([], 3600) is None


class TestTrend:
    def test_a_price_that_goes_nowhere_is_sideways(self):
        closes = [str(100 + (3 if (i // 15) % 2 == 0 else -3)) for i in range(15 * 40)]
        t = price_trend(series(closes))
        assert t["label"] == "sideways" and t["efficiency"] < D("0.15")

    def test_a_steady_climb_is_up_and_a_steady_fall_is_down(self):
        up = price_trend(series([str(100 + i * 0.05) for i in range(15 * 40)]))
        down = price_trend(series([str(200 - i * 0.05) for i in range(15 * 40)]))
        assert up["label"] == "up" and up["efficiency"] > D("0.9")
        assert down["label"] == "down"

    def test_too_little_data_is_unclear(self):
        assert price_trend(series(["100", "101"]))["label"] == "unclear"


class TestDepth:
    def test_spread_and_balance(self):
        depth = Depth(
            symbol=SYMBOL,
            timestamp=1,
            bids=[
                OrderBookLevel(price=D("264000"), quantity=D(30)),
                OrderBookLevel(price=D("263900"), quantity=D(10)),
            ],
            asks=[
                OrderBookLevel(price=D("264100"), quantity=D(20)),
                OrderBookLevel(price=D("264200"), quantity=D(20)),
            ],
        )
        s = depth_summary(depth)
        assert s["best_bid"] == D(264000) and s["best_ask"] == D(264100) and s["spread"] == D(100)
        assert s["spread_pct"] == D(100) / D(264050) * 100  # against the mid price
        assert (s["bid_volume"], s["ask_volume"]) == (D(40), D(40)) and s["bid_share_pct"] == D(50)

    def test_an_empty_side_is_handled(self):
        s = depth_summary(Depth(symbol=SYMBOL, timestamp=1, bids=[], asks=[]))
        assert s["best_bid"] is None and s["spread"] is None and s["bid_share_pct"] is None


def status(closes, price=None, now_ms=None, depth=None, trade_ts=None, params=PARAMS):
    candles = series(closes)
    trade_ts = trade_ts or 1_700_000_000_000 + (len(closes) - 1) * 60_000
    return build_market_status(
        symbol="USDTTMN",
        price=D(price or closes[-1]),
        trade_ts=trade_ts,
        candles=candles,
        depth=depth,
        params=params,
        price_precision=0,
        maker_fee=D("0.0005"),
        now_ms=now_ms or trade_ts + 30_000,
    )


class TestWarnings:
    codes = staticmethod(lambda s: {w["code"] for w in s["warnings"]})

    def test_a_calm_market_inside_the_range_raises_no_warning(self):
        closes = [str(264000 + (700 if (i // 15) % 2 == 0 else -700)) for i in range(90)]
        assert self.codes(status(closes)) == set()

    def test_price_outside_the_grid_is_flagged(self):
        s = status(["264000"] * 80 + ["268000"] * 10, price="268000")
        assert "outside_range" in self.codes(s)
        assert (
            next(w for w in s["warnings"] if w["code"] == "outside_range")["params"]["side"]
            == "above"
        )

    def test_a_quiet_hour_that_never_reached_the_next_level_is_flagged(self):
        # the last hour moved ~0.04%, the spacing is ~0.45%: the grid would barely trade
        closes = ["264000"] * 30 + [str(264000 + (50 if i % 2 else -50)) for i in range(60)]
        assert "moves_smaller_than_spacing" in self.codes(status(closes))

    def test_a_day_wider_than_the_whole_grid_is_flagged(self):
        closes = [str(255000 + i * 150) for i in range(90)]  # 255000 -> 268350: wider than the grid
        s = status(closes, price="264000")
        assert "range_wider_than_grid" in self.codes(s)

    def test_a_strong_trend_is_flagged(self):
        s = status([str(262000 + i * 5) for i in range(600)], price="264000")
        assert "strong_trend" in self.codes(s)

    def test_stale_data_is_flagged(self):
        trade = 1_700_000_000_000 + 89 * 60_000
        s = status(["264000"] * 90, now_ms=trade + 20 * 60_000, trade_ts=trade)
        assert "stale_price" in self.codes(s)


def test_the_result_contains_no_verdict_or_recommendation():
    import json

    text = json.dumps(status(["264000"] * 90), default=str).lower()
    for word in ("recommend", "signal", "should_buy", "should_sell", '"buy"', '"sell"', "advice"):
        assert word not in text


def test_everything_is_json_ready_with_exact_decimals_as_strings():
    import json

    from wallexbot.analytics.market_status import jsonable

    out = jsonable(status([str(263000 + i * 10) for i in range(90)]))
    json.dumps(out)
    assert out["price"] == "263890" and isinstance(out["grid"]["spacing"], str)
