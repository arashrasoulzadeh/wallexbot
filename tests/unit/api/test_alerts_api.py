"""Settings and Telegram alerts through the API (a fake notifier; nothing leaves the machine)."""

import asyncio

from fastapi.testclient import TestClient

from wallexbot.api.app import create_app
from wallexbot.api.manager import RunManager
from wallexbot.storage.repository import InMemoryRepository


class FakeNotifier:
    chat_id = "42"

    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.started = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False

    async def send(self, message, severity="info"):
        self.sent.append((message, severity))


def make(notifier):
    repo = InMemoryRepository()
    return TestClient(create_app(repo=repo, engine_manager=RunManager(repo, notifier=notifier)))


def test_settings_say_whether_telegram_is_set_up_and_never_show_secrets():
    with make(None) as c:
        body = c.get("/api/settings").json()
    assert body["telegram"] == {"configured": False}
    assert body["alerts"] == ["halted", "failed", "out_of_range"]
    with make(FakeNotifier()) as c:
        text = c.get("/api/settings").text
    assert '"configured":true' in text.replace(" ", "")
    assert "token" not in text.lower().replace("telegram_token", "")


def test_the_test_button_sends_a_message_when_telegram_is_set_up():
    fake = FakeNotifier()
    with make(fake) as c:
        body = c.post("/api/notify/test", json={}).json()
    assert body["sent"] is True and len(fake.sent) == 1
    assert "test" in fake.sent[0][0].lower()


async def test_an_engine_alert_reaches_telegram_with_the_market_name():
    fake = FakeNotifier()
    manager = RunManager(InMemoryRepository(), notifier=fake)
    manager.alert_hook("USDTTMN")("halted", "max drawdown 5.1% reached")
    await asyncio.sleep(0.05)
    assert fake.started
    message, severity = fake.sent[0]
    assert "USDTTMN" in message and "max drawdown" in message and severity == "warning"
    await manager.shutdown()
    assert not fake.started


async def test_alerts_do_nothing_without_telegram():
    manager = RunManager(InMemoryRepository(), notifier=None)
    manager.alert_hook("USDTTMN")("halted", "x")  # must not raise
