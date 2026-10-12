"""Historical data store for backtesting."""

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from wallexbot.domain.market import Symbol
from wallexbot.wallex.models import Candle


@dataclass
class HistoricalDataStore:
    """Stores and retrieves historical candle data."""

    data_dir: Path

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_candles(self, symbol: Symbol, candles: list[Candle]) -> None:
        """Save candles to CSV file."""
        file_path = self.data_dir / f"{str(symbol)}_candles.csv"
        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for c in candles:
                writer.writerow(
                    [
                        c.open_time,
                        str(c.open),
                        str(c.high),
                        str(c.low),
                        str(c.close),
                        str(c.volume),
                    ]
                )

    def load_candles(self, symbol: Symbol, resolution: str) -> list[Candle]:
        """Load candles from CSV file."""
        file_path = self.data_dir / f"{str(symbol)}_candles.csv"
        if not file_path.exists():
            return []

        candles = []
        with open(file_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                candles.append(
                    Candle(
                        symbol=symbol,
                        resolution=resolution,
                        open_time=int(row["timestamp"]),
                        open=Decimal(row["open"]),
                        high=Decimal(row["high"]),
                        low=Decimal(row["low"]),
                        close=Decimal(row["close"]),
                        volume=Decimal(row["volume"]),
                    )
                )
        return candles

    def get_candle_path(self, symbol: Symbol) -> Path:
        """Get path for symbol candles."""
        return self.data_dir / f"{str(symbol)}_candles.csv"
