"""Build the Telegram notifier from environment variables (off unless both are set).

The token is a secret that can post as your bot, so it is read from the environment only: never from
a config file, the database or the web UI.
"""

from collections.abc import Mapping

from wallexbot.alerts.telegram import TelegramNotifier

TOKEN_VAR = "WALLEXBOT_TELEGRAM_TOKEN"
CHAT_VAR = "WALLEXBOT_TELEGRAM_CHAT_ID"
ALERT_KINDS = ["halted", "failed", "out_of_range"]


def notifier_from_env(env: Mapping[str, str]) -> TelegramNotifier | None:
    """A notifier when both the bot token and the chat id are set, otherwise None."""
    token = env.get(TOKEN_VAR, "").strip()
    chat = env.get(CHAT_VAR, "").strip()
    if not token or not chat:
        return None
    return TelegramNotifier(bot_token=token, chat_id=chat)
