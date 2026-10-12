"""Tests for Telegram alerts and pluggable strategies."""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from tests.helpers.clock import FakeClock
from wallexbot.alerts.telegram import TelegramNotifier
from wallexbot.strategies.registry import StrategyPlugin, StrategyRegistry
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridMode, GridParameters


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
            clock=FakeClock(),
        )

    @pytest.mark.asyncio
    async def test_send_message(self, notifier, mock_transport):
        """Send message via Telegram Bot API."""
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
        mock_transport.post.return_value = mock_response

        await notifier.start()
        try:
            await notifier.send("Test message")
            # Give time for the background task to process
            import asyncio

            await asyncio.sleep(0.1)
        finally:
            await notifier.stop()

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
        mock_response_429.json.return_value = {
            "ok": False,
            "error_code": 429,
            "description": "Too Many Requests",
        }

        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"ok": True}

        mock_transport.post.side_effect = [mock_response_429, mock_response_ok]

        await notifier.start()
        try:
            await notifier.send("Test")
            import asyncio

            await asyncio.sleep(0.2)  # Wait for retries
        finally:
            await notifier.stop()

        assert mock_transport.post.call_count == 2

    @pytest.mark.asyncio
    async def test_failure_never_crashes_bot(self, notifier, mock_transport):
        """Notification failures never crash the bot."""
        mock_transport.post.side_effect = Exception("Network error")

        await notifier.start()
        try:
            # Should not raise
            await notifier.send("Test")
            import asyncio

            await asyncio.sleep(0.1)
        finally:
            await notifier.stop()

    @pytest.mark.asyncio
    async def test_batching(self, notifier, mock_transport):
        """Messages are batched and rate-limited."""
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True}
        mock_transport.post.return_value = mock_response

        await notifier.start()
        try:
            # Send multiple messages quickly
            for i in range(5):
                await notifier.send(f"Message {i}")
            import asyncio

            await asyncio.sleep(0.1)
        finally:
            await notifier.stop()

        # Should be batched or sent with delays
        assert mock_transport.post.call_count >= 1


class TestTelegramTemplates:
    """Tests for message templates."""

    def test_english_template(self):
        """English message template."""
        from wallexbot.alerts.telegram import format_alert_en

        msg = format_alert_en(
            "out_of_range", {"price": "115.00", "upper": "110.00", "lower": "90.00"}
        )
        assert "out of range" in msg.lower()
        assert "115.00" in msg

    def test_persian_template(self):
        """Persian message template."""
        from wallexbot.alerts.telegram import format_alert_fa

        msg = format_alert_fa(
            "out_of_range", {"price": "115.00", "upper": "110.00", "lower": "90.00"}
        )
        assert "محدوده" in msg or "خارج" in msg


class TestStrategyRegistry:
    """Tests for strategy plugin registry."""

    def test_register_strategy(self):
        """Register a strategy plugin."""
        registry = StrategyRegistry()

        @registry.register("test_grid")
        class TestGridStrategyPlugin(StrategyPlugin):
            @property
            def name(self) -> str:
                return "test_grid"

            @property
            def params_model(self):
                from pydantic import BaseModel

                class Params(BaseModel):
                    lower_price: str = "90.00"
                    upper_price: str = "110.00"
                    grid_count: int = 10
                    mode: str = "arithmetic"
                    total_investment: str = "10000.00"

                return Params

            def create_strategy(self, market, params):
                grid_params = GridParameters(
                    lower_price=Decimal(params.lower_price),
                    upper_price=Decimal(params.upper_price),
                    grid_count=params.grid_count,
                    mode=GridMode(params.mode),
                    total_investment=Decimal(params.total_investment),
                )
                return GridStrategy(market=market, params=grid_params)

        assert "test_grid" in registry.list_strategies()
        plugin = registry.get("test_grid")
        assert plugin is not None
        assert plugin.name == "test_grid"

    def test_strategy_params_model(self):
        """Strategy params model used for config form."""
        registry = StrategyRegistry()

        @registry.register("test_grid")
        class TestGridStrategyPlugin(StrategyPlugin):
            @property
            def name(self) -> str:
                return "test_grid"

            @property
            def params_model(self):
                from pydantic import BaseModel

                class Params(BaseModel):
                    lower_price: str = "90.00"
                    upper_price: str = "110.00"
                    grid_count: int = 10
                    mode: str = "arithmetic"
                    total_investment: str = "10000.00"

                return Params

            def create_strategy(self, market, params):
                grid_params = GridParameters(
                    lower_price=Decimal(params.lower_price),
                    upper_price=Decimal(params.upper_price),
                    grid_count=params.grid_count,
                    mode=GridMode(params.mode),
                    total_investment=Decimal(params.total_investment),
                )
                return GridStrategy(market=market, params=grid_params)

        # Should have params model
        params_model = registry.get_params_model("test_grid")
        assert params_model is not None

    def test_contract_tests(self):
        """Contract test suite for strategies."""
        registry = StrategyRegistry()

        @registry.register("valid_grid")
        class ValidGridStrategyPlugin(StrategyPlugin):
            @property
            def name(self) -> str:
                return "valid_grid"

            @property
            def params_model(self):
                from pydantic import BaseModel

                class Params(BaseModel):
                    lower_price: str = "90.00"
                    upper_price: str = "110.00"
                    grid_count: int = 10
                    mode: str = "arithmetic"
                    total_investment: str = "10000.00"

                return Params

            def create_strategy(self, market, params):
                # params could be a GridParameters object or a Params model
                if isinstance(params, GridParameters):
                    grid_params = params
                else:
                    grid_params = GridParameters(
                        lower_price=Decimal(str(params.lower_price)),
                        upper_price=Decimal(str(params.upper_price)),
                        grid_count=params.grid_count,
                        mode=GridMode(params.mode),
                        total_investment=Decimal(str(params.total_investment)),
                    )
                return GridStrategy(market=market, params=grid_params)

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
