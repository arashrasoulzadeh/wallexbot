"""`wallexbot paper` runs the engine on a price feed (faked here: no network)."""

import asyncio
import importlib
import sqlite3
from collections.abc import AsyncGenerator
from decimal import Decimal as D
from pathlib import Path

import pytest

from tests.helpers.wallex_fakes import FakeClient
from wallexbot.cli.main import main
from wallexbot.domain.market import Symbol
from wallexbot.wallex.price_feed import PriceTick

cli = importlib.import_module("wallexbot.cli.main")  # the package re-exports `main`, shadowing it
EXAMPLE_CONFIG = Path(__file__).resolve().parents[3] / "config" / "grid.example.yaml"
SYMBOL = Symbol("USDTTMN")


class ScriptedFeed:
    def __init__(self, prices: list[int]) -> None:
        self.prices = prices
        self.closed = False
        self.loop: object = None

    async def subscribe(self, symbol: Symbol) -> None: ...
    async def unsubscribe(self, symbol: Symbol) -> None: ...

    async def ticks(self) -> AsyncGenerator[PriceTick, None]:
        self.loop = asyncio.get_running_loop()
        for i, p in enumerate(self.prices):
            yield PriceTick(
                symbol=SYMBOL, price=D(p), timestamp=1_700_000_000_000 + i * 60_000, source="test"
            )

    async def close(self) -> None:
        # Real feeds own tasks/queues bound to the loop they ran in: closing from another loop fails.
        assert asyncio.get_running_loop() is self.loop, "feed closed on a different event loop"
        self.closed = True


SWINGING = [264000] + [262500, 265500] * 6


@pytest.fixture
def run_paper(monkeypatch, capsys):
    made = {}

    def _run(prices: list[int], *args: str, config: Path = EXAMPLE_CONFIG) -> tuple[int, str]:
        feed = ScriptedFeed(prices)
        made["feed"] = feed

        def make_feed(kind: str, symbol: Symbol, client: object) -> ScriptedFeed:
            made["kind"] = kind
            return feed

        monkeypatch.setattr(cli, "make_rest_client", lambda: FakeClient())
        monkeypatch.setattr(cli, "make_price_feed", make_feed)
        code = main(["paper", str(config), *args])
        return code, capsys.readouterr().out

    _run.made = made  # type: ignore[attr-defined]
    return _run


def test_paper_run_trades_and_prints_a_summary(run_paper):
    code, out = run_paper(SWINGING)

    assert code == 0
    assert "Paper trading USDTTMN" in out
    assert "paper only" in out.lower()  # says plainly that no real orders exist
    cycles = int(
        next(line for line in out.splitlines() if line.startswith("Completed cycles")).split()[-1]
    )
    assert cycles > 0
    assert "stopped" in out.lower()
    assert run_paper.made["feed"].closed  # and on the loop it ran in


def test_the_websocket_feed_is_the_default_and_polling_can_be_chosen(run_paper):
    run_paper(SWINGING)
    assert run_paper.made["kind"] == "ws"
    run_paper(SWINGING, "--feed", "poll")
    assert run_paper.made["kind"] == "poll"


def test_a_risk_limit_halts_the_run_and_says_why(run_paper, tmp_path):
    config = tmp_path / "tight.yaml"
    text = EXAMPLE_CONFIG.read_text(encoding="utf-8").replace(
        'max_drawdown: "0.05"', 'max_drawdown: "0.0001"'
    )
    config.write_text(text, encoding="utf-8")

    code, out = run_paper([264000, 261500, 261000, 260000], config=config)

    assert code == 0
    assert "halted" in out.lower() and "drawdown" in out.lower()


def test_the_run_can_be_recorded_in_a_sqlite_database(run_paper, tmp_path):
    db = tmp_path / "runs.db"
    code, _ = run_paper(SWINGING, "--db", str(db))

    assert code == 0
    with sqlite3.connect(db) as conn:
        [(status,)] = conn.execute("SELECT status FROM runs").fetchall()
        fills = conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
    assert status == "stopped" and fills > 0


def test_unknown_market_is_an_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_rest_client", lambda: FakeClient(markets=[]))
    code = main(["paper", str(EXAMPLE_CONFIG)])
    assert code == 1 and "not found" in capsys.readouterr().out.lower()


def test_invalid_config_is_an_error(monkeypatch, capsys, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("market:\n  symbol: USDTTMN\n")
    monkeypatch.setattr(cli, "make_rest_client", lambda: FakeClient())
    assert main(["paper", str(bad)]) == 1
    assert "error" in capsys.readouterr().out.lower()


class FakeNotifier:
    chat_id = "42"

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.started = self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send(self, message: str, severity: str = "info") -> None:
        self.sent.append(message)


def test_a_cli_run_tells_telegram_when_the_price_leaves_the_range(run_paper, monkeypatch):
    fake = FakeNotifier()
    monkeypatch.setattr(cli, "notifier_from_env", lambda env: fake)
    code, _ = run_paper([264000, 290000, 291000])
    assert code == 0 and fake.started and fake.stopped
    assert len(fake.sent) == 1 and "USDTTMN" in fake.sent[0] and "out of range" in fake.sent[0]


def test_a_cli_run_without_telegram_just_runs(run_paper, monkeypatch):
    monkeypatch.setattr(cli, "notifier_from_env", lambda env: None)
    code, out = run_paper([264000, 290000])
    assert code == 0 and "Paper trading USDTTMN" in out
