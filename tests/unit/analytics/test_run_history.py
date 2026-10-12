"""History analytics: pure functions over a run's snapshots and fills (hand-computed numbers)."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal as D

from wallexbot.analytics.run_history import (
    Point,
    daily_breakdown,
    downsample,
    fills_csv,
    filter_range,
    local_day,
    max_drawdown_pct,
    parse_snapshots,
    run_summary,
    snapshots_csv,
)


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp() * 1000)


def row(ts, equity, price="100", realized="0", fees="0", orders=6, fills=0, cycles=0):
    return {
        "ts": ts,
        "price": price,
        "equity": str(equity),
        "realized": str(realized),
        "fees": str(fees),
        "open_orders": orders,
        "fills": fills,
        "cycles": cycles,
    }


def fill(ts, side, price="100", qty="1", fee="0.1", fee_asset="TMN"):
    return {
        "timestamp": ts,
        "side": side,
        "price": price,
        "quantity": qty,
        "fee": fee,
        "fee_asset": fee_asset,
        "order_id": "o",
        "level_index": 1,
    }


def test_snapshots_are_parsed_into_exact_decimals():
    [p] = parse_snapshots([row(1000, "1998356.2414", price="261745")])
    assert p.equity == D("1998356.2414") and p.price == D("261745") and p.ts == 1000


def test_a_snapshot_without_a_price_is_allowed():
    [p] = parse_snapshots([{**row(1, 5), "price": None}])
    assert p.price is None


def test_downsampling_keeps_the_ends_and_the_order_and_respects_the_limit():
    points = parse_snapshots([row(i * 1000, 1000 + i) for i in range(1000)])
    small = downsample(points, 50)
    assert len(small) <= 50 and small[0] == points[0] and small[-1] == points[-1]
    assert [p.ts for p in small] == sorted(p.ts for p in small)
    assert downsample(points[:10], 50) == points[:10]
    assert downsample(points, 2) == [points[0], points[-1]]
    assert downsample([], 10) == []


def test_range_filter_is_inclusive():
    points = parse_snapshots([row(t, 1) for t in (1000, 2000, 3000, 4000)])
    assert [p.ts for p in filter_range(points, 2000, 3000)] == [2000, 3000]
    assert [p.ts for p in filter_range(points, None, 1500)] == [1000]
    assert [p.ts for p in filter_range(points, 3500, None)] == [4000]


def test_max_drawdown_is_the_largest_fall_from_a_running_peak():
    points = parse_snapshots([row(i, e) for i, e in enumerate([100, 110, 99, 105, 90, 120])])
    assert max_drawdown_pct(points) == D(20) / D(110) * 100  # 110 -> 90
    assert max_drawdown_pct(parse_snapshots([row(0, 100), row(1, 101)])) == 0
    assert max_drawdown_pct([]) == 0


def test_days_change_at_midnight_in_tehran_not_utc():
    # Tehran is UTC+03:30 all year (no daylight saving since 2022)
    assert local_day(ms("2026-10-10T20:29:59"), "Asia/Tehran") == "2026-10-10"
    assert local_day(ms("2026-10-10T20:30:00"), "Asia/Tehran") == "2026-10-11"
    assert local_day(ms("2026-10-10T20:30:00"), "UTC") == "2026-10-10"


def test_the_daily_breakdown_measures_each_day_from_where_the_previous_one_ended():
    # Tehran midnight between day 1 and day 2 is 20:30Z
    points = parse_snapshots(
        [
            row(ms("2026-10-10T10:00:00"), 1000, realized=0, fees=2, fills=0, cycles=0),  # day 1
            row(ms("2026-10-10T15:00:00"), 1010, realized=8, fees=4, fills=3, cycles=1),  # day 1
            row(ms("2026-10-10T21:00:00"), 1005, realized=12, fees=6, fills=5, cycles=2),  # day 2
            row(ms("2026-10-11T12:00:00"), 1030, realized=25, fees=9, fills=9, cycles=4),  # day 2
        ]
    )
    fills = [
        fill(ms("2026-10-10T11:00:00"), "BUY", "100", "2"),
        fill(ms("2026-10-10T14:00:00"), "SELL", "101", "1"),
        fill(ms("2026-10-10T22:00:00"), "BUY", "99", "3"),
    ]

    days = daily_breakdown(points, fills, "Asia/Tehran")

    assert [d["date"] for d in days] == ["2026-10-10", "2026-10-11"]
    first, second = days
    assert first["equity_change"] == D(10) and first["realized_change"] == D(8)
    assert (
        first["cycles"] == 1 and first["fills"] == 2 and (first["buys"], first["sells"]) == (1, 1)
    )
    assert first["volume"] == D("2") * 100 + D("1") * 101
    # day 2 starts from day 1's last value (1010, realized 8, fees 4, cycles 1)
    assert second["equity_change"] == D(20) and second["realized_change"] == D(17)
    assert second["fees"] == D(5) and second["cycles"] == 3 and second["fills"] == 1


def test_a_single_day_run_has_one_row_and_an_empty_run_has_none():
    points = parse_snapshots(
        [row(ms("2026-10-10T10:00:00"), 100), row(ms("2026-10-10T11:00:00"), 103)]
    )
    assert len(daily_breakdown(points, [], "UTC")) == 1
    assert daily_breakdown([], [], "UTC") == []


def test_the_summary_collects_the_headline_numbers():
    points = parse_snapshots(
        [
            row(1_000_000, 1000, price="100", realized=0, fees=2, fills=0, cycles=0),
            row(2_000_000, 1100, price="104", realized=30, fees=6, fills=4, cycles=2),
            row(3_000_000, 990, price="102", realized=40, fees=7, fills=6, cycles=3),
        ]
    )
    fills = [fill(1, "BUY", "100", "2"), fill(2, "SELL", "104", "1"), fill(3, "BUY", "99", "1")]
    run = {
        "id": "r1",
        "status": "stopped",
        "market": "USDTTMN",
        "started_at": 900_000,
        "stopped_at": 3_100_000,
    }

    s = run_summary(run, points, fills)

    assert s["return_pct"] == D(-1)  # 1000 -> 990 is -1%
    assert s["max_drawdown_pct"] == D(110) / D(1100) * 100  # 1100 -> 990
    assert s["realized"] == D(40) and s["fees"] == D(7) and s["cycles"] == 3
    assert (s["fills"], s["buys"], s["sells"]) == (3, 2, 1)
    assert (
        s["first_price"] == D(100) and s["last_price"] == D(102) and s["price_change_pct"] == D(2)
    )
    assert s["duration_ms"] == 2_000_000 and s["status"] == "stopped" and s["market"] == "USDTTMN"


def test_a_replayed_run_lasts_as_long_as_its_data_not_as_long_as_the_replay_took():
    points = parse_snapshots([row(1_000_000_000, 100), row(1_000_000_000 + 3 * 86_400_000, 101)])
    run = {"id": "r", "status": "stopped", "market": "X", "started_at": 5_000, "stopped_at": 9_000}
    s = run_summary(run, points, [])
    assert s["duration_ms"] == 3 * 86_400_000 and s["ended_at"] == 1_000_000_000 + 3 * 86_400_000


def test_the_summary_of_a_run_with_no_history_is_zeros_not_an_error():
    s = run_summary({"id": "r", "status": "running", "market": "X", "started_at": 5}, [], [])
    assert s["return_pct"] == 0 and s["fills"] == 0 and s["max_drawdown_pct"] == 0


def test_csv_export_has_a_header_and_escapes_awkward_values():
    text = fills_csv([{**fill(1_700_000_000_000, "BUY"), "fee_asset": 'US"DT,x'}])
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == [
        "time_utc",
        "timestamp_ms",
        "side",
        "price",
        "quantity",
        "fee",
        "fee_asset",
        "level",
    ]
    assert rows[1][1] == "1700000000000" and rows[1][2] == "BUY" and rows[1][6] == 'US"DT,x'
    assert rows[1][0] == "2023-11-14T22:13:20Z"

    points = parse_snapshots([row(1_700_000_000_000, 5)])
    assert list(csv.reader(io.StringIO(snapshots_csv(points))))[0][:3] == [
        "time_utc",
        "timestamp_ms",
        "price",
    ]


START = Point(
    ts=0, price=D(100), equity=D(1000), realized=D(0), fees=D(0), open_orders=0, fills=0, cycles=0
)


def test_a_start_point_makes_the_summary_count_the_entry_fee_and_everything_after_it():
    # the first snapshot (equity 998, fees 2) is already AFTER the entry fee was paid
    points = parse_snapshots(
        [row(1000, 998, realized=0, fees=2), row(2000, 1010, realized=15, fees=7, cycles=2)]
    )
    run = {"id": "r", "status": "stopped", "market": "X", "started_at": 0}

    s = run_summary(run, points, [], start=START)

    assert s["return_pct"] == D(1)  # 1000 -> 1010, not 998 -> 1010
    assert s["fees"] == D(7) and s["realized"] == D(15) and s["cycles"] == 2


def test_a_range_summary_counts_only_what_happened_inside_the_range():
    before = Point(
        ts=500,
        price=D(100),
        equity=D(1000),
        realized=D(10),
        fees=D(4),
        open_orders=0,
        fills=3,
        cycles=1,
    )
    points = parse_snapshots([row(1000, 1020, price="102", realized=30, fees=9, cycles=3)])
    s = run_summary(
        {"id": "r", "status": "x", "market": "X", "started_at": 0}, points, [], start=before
    )
    assert s["realized"] == D(20) and s["fees"] == D(5) and s["cycles"] == 2
    assert s["return_pct"] == D(2) and s["price_change_pct"] == D(2)


def test_the_first_day_is_measured_from_the_start_point_too():
    points = parse_snapshots(
        [
            row(ms("2026-10-10T10:00:00"), 998, realized=0, fees=2),
            row(ms("2026-10-10T15:00:00"), 1010, realized=8, fees=6, cycles=1),
        ]
    )
    [day] = daily_breakdown(points, [], "UTC", start=START)
    assert day["equity_change"] == D(10)  # 1000 -> 1010: includes the entry fee
    assert day["fees"] == D(6) and day["realized_change"] == D(8) and day["cycles"] == 1
