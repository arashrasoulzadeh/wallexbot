"""Telegram rejects HTML it cannot parse, which would silently lose the alert."""

from unittest.mock import AsyncMock, Mock

from tests.helpers.clock import FakeClock
from wallexbot.alerts.telegram import TelegramNotifier


async def test_angle_brackets_and_ampersands_in_a_message_are_escaped():
    transport = AsyncMock()
    transport.post.return_value = Mock(status_code=200)
    n = TelegramNotifier(bot_token="t", chat_id="1", transport=transport, clock=FakeClock())
    await n._do_send(transport, "failed: TypeError: <class 'X'> & drawdown 5% > limit")
    body = transport.post.call_args.kwargs["json"]
    assert (
        body["text"]
        == "failed: TypeError: &lt;class &#x27;X&#x27;&gt; &amp; drawdown 5% &gt; limit"
    )
    assert body["parse_mode"] == "HTML"
