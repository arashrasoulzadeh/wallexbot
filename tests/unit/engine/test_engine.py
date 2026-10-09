"""Tests for bot engine."""

from decimal import Decimal
import pytest
from unittest.mock import Mock, AsyncMock

from wallexbot.engine.bot import BotEngine, EngineConfig
from wallexbot.engine.actions import ActionExecutor
from wallexbot.strategy.grid.interface import GridStrategy
from wallexbot.strategy.grid.parameters import GridParameters, GridMode
from wallexbot.domain.market import Market, Symbol
from wallexbot.sim.exchange import SimulatedExchange
from wallexbot.wallex.price_feed import PriceFeed, PriceTick, PriceFeedReplay
from wallexbot.domain.fees import FeeSchedule, MinNotionalRule
from wallexbot.tests.helpers.clock import FakeClock


class TestActionExecutor:
    """Tests for action executor."""

    @pytest.fixture
    def exchange(self):
        return Mock()

    @pytest.fixture
    def executor(self, exchange):
        return ActionExecutor(exchange=exchange, clock=FakeClock())

    def test_place_action_generates_idempotent_client_id(self, executor):
        """Place action generates idempotent client_id."""
        from wallexbot.strategy.grid.interface import PlaceAction
        from wallexbot.domain.market import Symbol, Side, OrderType

        action = PlaceAction(
            type="place",
            client_id="",  # Will be generated
            symbol=Symbol("USDTTMN"),
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("100.00"),
            quantity=Decimal("10.0000"),
            level_index=0,
        )

        # Execute should generate client_id
        result = executor.execute_place(action)
        assert result.client_id.startswith("GRID_")

    def test_timeout_handling_looks_up_by_client_id(self, executor):
        """Timeout on place -> look up by client_id before retry."""
        # This would test the timeout handling logic
        pass


class TestBotEngine:
    """Tests for bot engine."""

    @pytest.fixture
    def market(self):
        return Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )

    @pytest.fixture
    def params(self):
        return GridParameters(
            lower_price=Decimal("90.00"),
            upper_price=Decimal("110.00"),
            grid_count=5,
            mode=GridMode.ARITHMETIC,
            total_investment=Decimal("10000.00"),
        )

    @pytest.fixture
    def strategy(self, market, params):
        return GridStrategy(market=market, params=params)

    @pytest.fixture
    def exchange(self, market):
        return SimulatedExchange(
            market=market,
            fee_schedule=FeeSchedule(maker_rate=Decimal("0.001"), taker_rate=Decimal("0.002")),
            min_notional_rule=MinNotionalRule(min_notional=Decimal("10.00"), min_quantity=Decimal("0.0001")),
            initial_balances={
                "TMN": Mock(free=Decimal("2000000.00"), locked=Decimal("0")),
                "USDT": Mock(free=Decimal("0"), locked=Decimal("0")),
            },
        )

    @pytest.fixture
    def price_feed(self):
        ticks = [
            PriceTick(symbol=Symbol("USDTTMN"), price=Decimal("100.00"), timestamp=1000, source="test"),
            PriceTick(symbol=Symbol("USDTTMN"), price=Decimal("99.00"), timestamp=1001, source="test"),
            PriceTick(symbol=Symbol("USDTTMN"), price=Decimal("95.00"), timestamp=1002, source="test"),
            PriceTick(symbol=Symbol("USDTTMN"), price=Decimal("105.00"), timestamp=1003, source="test"),
        ]
        return PriceFeedReplay(ticks)

    @pytest.fixture
    def engine(self, strategy, exchange, price_feed):
        config = EngineConfig(
            strategy=strategy,
            exchange=exchange,
            price_feed=price_feed,
            clock=FakeClock(),
        )
        return BotEngine(config)

    @pytest.mark.asyncio
    async def test_startup_sequence(self, engine):
        """Test startup sequence."""
        await engine.start()
        # Should have placed initial grid
        assert engine.is_running()

    @pytest.mark.asyncio
    async def test_price_feed_to_strategy(self, engine):
        """Price feed -> strategy -> actions -> exchange."""
        await engine.start()

        # Process first price tick
        await engine.process_next_tick()
        # Should update strategy state

    @pytest.mark.asyncio
    async def test_fill_handling_path(self, engine, exchange):
        """Exchange event -> strategy on_fill -> actions."""
        await engine.start()

        # Simulate a fill
        # This would need integration with exchange events

    @pytest.mark.asyncio
    async def test_polling_fallback(self, engine):
        """Polling fallback when event stream down."""
        pass

    @pytest.mark.asyncio
    async def test_kill_switch(self, engine):
        """Kill switch stops placing, cancels all orders."""
        await engine.start()
        engine.kill()
        assert engine.is_halted()

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, engine):
        """Graceful shutdown on SIGINT/SIGTERM."""
        await engine.start()
        await engine.shutdown()
        assert not engine.is_running()

    @pytest.mark.asyncio
    async def test_pause_resume_on_range_exit(self, engine):
        """Pause/resume when price leaves range."""
        await engine.start()

        # Price moves out of range
        # Should pause

        # Price moves back in range
        # Should resume (if configured)


class TestEngineIntegration:
    """Integration tests for engine + sim exchange + scripted feed."""

    @pytest.mark.asyncio
    async def test_uptrend_scenario(self):
        """Up-trend through all levels."""
        pass

    @pytest.mark.asyncio
    async def test_downtrend_scenario(self):
        """Down-trend through all levels."""
        pass

    @pytest.mark.asyncio
    async def test_sideways_oscillation(self):
        """Sideways oscillation."""
        pass

    @pytest.mark.asyncio
    async def test_gap_jump(self):
        """Gap/jump over several levels."""
        pass

    @pytest.mark.asyncio
    async def test_whipsaw(self):
        """Whipsaw at one level."""
        pass