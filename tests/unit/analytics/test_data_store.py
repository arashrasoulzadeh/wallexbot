"""Historical candle store (regression: Symbol is a str, it has no `.value`)."""

from decimal import Decimal as D

from wallexbot.analytics.data_store import HistoricalDataStore
from wallexbot.domain.market import Symbol
from wallexbot.wallex.models import Candle


def make_candles(symbol: Symbol) -> list[Candle]:
    return [
        Candle(
            symbol=symbol,
            resolution="60",
            open_time=1_700_000_000 + i * 3600,
            open=D("264000") + i,
            high=D("264100") + i,
            low=D("263900") + i,
            close=D("264050") + i,
            volume=D("1234.56"),
        )
        for i in range(3)
    ]


def test_save_then_load_round_trips_candles(tmp_path):
    store = HistoricalDataStore(data_dir=tmp_path)
    symbol = Symbol("USDTTMN")
    candles = make_candles(symbol)

    store.save_candles(symbol, candles)
    loaded = store.load_candles(symbol, "60")

    assert loaded == candles
    assert store.get_candle_path(symbol).name == "USDTTMN_candles.csv"


def test_load_missing_symbol_returns_empty_list(tmp_path):
    assert HistoricalDataStore(data_dir=tmp_path).load_candles(Symbol("BTCUSDT"), "60") == []
