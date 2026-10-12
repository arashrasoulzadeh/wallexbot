"""Telegram is configured only through environment variables, never through a file or the UI."""

from wallexbot.alerts.setup import notifier_from_env


def test_no_variables_means_no_notifier():
    assert notifier_from_env({}) is None
    assert notifier_from_env({"WALLEXBOT_TELEGRAM_TOKEN": "t"}) is None  # chat id missing
    assert notifier_from_env({"WALLEXBOT_TELEGRAM_CHAT_ID": "1"}) is None  # token missing
    assert (
        notifier_from_env({"WALLEXBOT_TELEGRAM_TOKEN": " ", "WALLEXBOT_TELEGRAM_CHAT_ID": "1"})
        is None
    )


def test_both_variables_make_a_notifier():
    n = notifier_from_env(
        {"WALLEXBOT_TELEGRAM_TOKEN": "123:abc", "WALLEXBOT_TELEGRAM_CHAT_ID": "42"}
    )
    assert n is not None and n.chat_id == "42"
    assert "123:abc" not in repr(n)  # the token never shows up in logs
