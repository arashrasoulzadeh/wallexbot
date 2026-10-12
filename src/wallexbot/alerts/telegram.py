"""Telegram notifier for alerts."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from wallexbot.domain import Clock, SystemClock

logger = logging.getLogger(__name__)


@dataclass
class TelegramNotifier:
    """Sends alerts via Telegram Bot API."""

    bot_token: str = field(repr=False)
    chat_id: str
    transport: object | None = None  # httpx.AsyncClient or mock
    clock: Clock = field(default_factory=SystemClock)
    _queue: asyncio.Queue[dict[str, str]] = field(default_factory=asyncio.Queue, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    async def start(self) -> None:
        """Start the notifier background task."""
        self._task = asyncio.create_task(self._process_queue())

    async def stop(self) -> None:
        """Stop the notifier."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def send(self, message: str, severity: str = "info") -> None:
        """Queue a message for sending."""
        await self._queue.put({"message": message, "severity": severity})

    async def send_alert(self, event_type: str, data: dict[str, Any], lang: str = "en") -> None:
        """Send a formatted alert."""
        if lang == "fa":
            message = format_alert_fa(event_type, data)
        else:
            message = format_alert_en(event_type, data)
        await self.send(message, severity="warning")

    async def _process_queue(self) -> None:
        """Process message queue with rate limiting."""
        last_sent = 0.0
        min_interval = 1.0  # Minimum 1 second between messages

        while True:
            try:
                item = await self._queue.get()
                now = self.clock.now()

                # Rate limiting
                if now - last_sent < min_interval:
                    await asyncio.sleep(min_interval - (now - last_sent))

                await self._send_telegram(item["message"])
                last_sent = self.clock.now()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram send failed: {e}")
                # Never crash the bot

    async def _send_telegram(self, message: str) -> None:
        """Send message via Telegram Bot API."""
        if self.transport is None:
            import httpx

            async with httpx.AsyncClient() as client:
                await self._do_send(client, message)
        else:
            await self._do_send(self.transport, message)

    async def _do_send(self, client: Any, message: str) -> None:
        """Actually send the message."""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        response = await client.post(url, json=data)

        if response.status_code == 429:
            # Rate limited - retry after delay
            retry_after = response.json().get("parameters", {}).get("retry_after", 5)
            await self.clock.async_sleep(retry_after)
            response = await client.post(url, json=data)

        if response.status_code != 200:
            logger.warning(f"Telegram API error: {response.status_code} {response.text}")


def format_alert_en(event_type: str, data: dict[str, Any]) -> str:
    """Format alert message in English."""
    templates = {
        "out_of_range": "⚠️ Price out of range: {price} (range: {lower}-{upper})",
        "risk_limit": "🚨 Risk limit hit: {limit} = {value}",
        "feed_disconnected": "📡 Feed disconnected for {seconds}s",
        "run_halted": "🛑 Run halted: {reason}",
        "daily_summary": "📊 Daily Summary: PnL={pnl}, Cycles={cycles}, Fees={fees}",
        "cycle_completed": "✅ Grid cycle completed at level {level}: profit={profit}",
    }
    template = templates.get(event_type, "Alert: {event_type} - {data}")
    return template.format(**data)


def format_alert_fa(event_type: str, data: dict[str, Any]) -> str:
    """Format alert message in Persian."""
    templates = {
        "out_of_range": "⚠️ قیمت خارج از محدوده: {price} (محدوده: {lower}-{upper})",
        "risk_limit": "🚨 محدودیت ریسک: {limit} = {value}",
        "feed_disconnected": "📡 قطع ارتباط فید برای {seconds} ثانیه",
        "run_halted": "🛑 ربات متوقف: {reason}",
        "daily_summary": "📊 خلاصه روزانه: سود/زیان={pnl}, چرخه‌ها={cycles}, کارمزد={fees}",
        "cycle_completed": "✅ چرخه گرید در سطح {level} تکمیل: سود={profit}",
    }
    template = templates.get(event_type, "هشدار: {event_type} - {data}")
    return template.format(**data)
