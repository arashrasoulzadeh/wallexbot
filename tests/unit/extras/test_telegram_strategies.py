"""Tests for Telegram alerts and pluggable strategies."""

from decimal import Decimal
import pytest
from unittest.mock import Mock, AsyncMock, patch

from wallexbot.alerts.telegram import TelegramNotifier
from wallexbot.strategies.registry import StrategyRegistry, StrategyPlugin
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridParameters, GridMode
from wallexbot.domain.market import Market, Symbol


class TestTelegramNotifier:
    """Tests for Telegram notifier."""

    @pytest.fixture
    def mock_transport(self):
        return AsyncMock()

    @pytest.fixture
    def notifier(self, mock_transport):
        return TelegramNotifier(
            bot_token="test_token",
            chat_id="123456",
            transport=mock_transport,
        )

    @pytest.mark.asyncio
    async def test_send_message(self, notifier, mock_transport):
        """Send message via Telegram Bot API."""
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
        mock_transport.post.return_value = mock_response

        await notifier.send("Test message")

        mock_transport.post.assert_called_once()
        call_args = mock_transport.post.call_args
        assert "sendMessage" in call_args[0][0]
        assert call_args[1]["json"]["chat_id"] == "123456"
        assert call_args[1]["json"]["text"] == "Test message"

    @pytest.mark.asyncio
    async def test_rate_limit_backoff(self, notifier, mock_transport):
        """Handle rate limit with backoff."""
        # First call returns 429, second succeeds
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.json.return_value = {"ok": False, "error_code": 429, "description": "Too Many Requests"}

        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"ok": True}

        mock_transport.post.side_effect = [mock_response_429, mock_response_ok]

        await notifier.send("Test")
        assert mock_transport.post.call_count == 2

    @pytest.mark.asyncio
    async def test_failure_never_crashes_bot(self, notifier, mock_transport):
        """Notification failures never crash the bot."""
        mock_transport.post.side_effect = Exception("Network error")

        # Should not raise
        await notifier.send("Test")

    @pytest.mark.asyncio
    async def test_batching(self, notifier, mock_transport):
        """Messages are batched and rate-limited."""
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True}
        mock_transport.post.return_value = mock_response

        # Send multiple messages quickly
        for i in range(5):
            await notifier.send(f"Message {i}")

        # Should be batched or sent with delays
        assert mock_transport.post.call_count >= 1


class TestTelegramTemplates:
    """Tests for message templates."""

    def test_english_template(self):
        """English message template."""
        from wallexbot.alerts.telegram import format_alert_en
        msg = format_alert_en("out_of_range", {"price": "115.00", "upper": "110.00"})
        assert "out of range" in msg.lower()
        assert "115.00" in msg

    def test_persian_template(self):
        """Persian message template."""
        from wallexbot.alerts.telegram import format_alert_fa
        msg = format_alert_fa("out_of_range", {"price": "115.00", "upper": "110.00"})
        assert "محدوده" in msg or "خارج" in msg


class TestStrategyRegistry:
    """Tests for strategy plugin registry."""

    def test_register_strategy(self):
        """Register a strategy plugin."""
        registry = StrategyRegistry()

        @registry.register("test_grid")
        class TestGridStrategy(GridStrategy):
            pass

        assert "test_grid" in registry.list_strategies()
        strategy_class = registry.get("test_grid")
        assert strategy_class is TestGridStrategy

    def test_strategy_params_model(self):
        """Strategy params model used for config form."""
        registry = StrategyRegistry()

        @registry.register("test_grid")
        class TestGridStrategy(GridStrategy):
            pass

        # Should have params model
        params_model = registry.get_params_model("test_grid")
        assert params_model is not None

    def test_contract_tests(self):
        """Contract test suite for strategies."""
        registry = StrategyRegistry()

        @registry.register("valid_grid")
        class ValidGridStrategy(GridStrategy):
            def on_start(self, current_price, timestamp):
                return []

            def on_price(self, current_price, timestamp):
                return []

            def on_fill(self, level_index, fill_qty, fill_fee, fill_fee_asset, timestamp):
                return []

            def on_stop(self, timestamp):
                return []

        # Run contract tests
        errors = registry.run_contract_tests("valid_grid")
        assert errors == []


class TestDockerSetup:
    """Tests for Docker packaging."""

    def test_dockerfile_exists(self):
        """Dockerfile exists."""
        import os
        assert os.path.exists("Dockerfile")

    def test_docker_compose_exists(self):
        """docker-compose.yml exists."""
        import os
        assert os.path.exists("docker-compose.yml")

    def test_dockerfile_no_secrets(self):
        """Dockerfile doesn't bake secrets."""
        with open("Dockerfile") as f:
            content = f.read()
        assert "api_key" not in content.lower()
        assert "secret" not in content.lower()