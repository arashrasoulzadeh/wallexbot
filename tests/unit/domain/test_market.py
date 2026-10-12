"""Tests for Symbol and Market models."""

from decimal import Decimal

import pytest

from wallexbot.domain.market import Market, OrderStatus, OrderType, Side, Symbol


class TestSymbol:
    """Tests for Symbol value object."""

    def test_symbol_creation(self):
        symbol = Symbol("USDTTMN")
        assert str(symbol) == "USDTTMN"
        assert symbol == "USDTTMN"

    def test_symbol_equality(self):
        assert Symbol("USDTTMN") == Symbol("USDTTMN")
        assert Symbol("USDTTMN") != Symbol("BTCTMN")

    def test_symbol_hashable(self):
        symbols = {Symbol("USDTTMN"), Symbol("BTCTMN")}
        assert len(symbols) == 2


class TestMarket:
    """Tests for Market model from /hector/web/v1/markets."""

    def test_market_from_fixture(self):
        # Sample from Wallex markets API
        data = {
            "symbol": "USDTTMN",
            "baseAsset": "USDT",
            "quoteAsset": "TMN",
            "pricePrecision": 2,
            "amountPrecision": 4,
            "isSpot": True,
        }
        market = Market.from_api_response(data)
        assert market.symbol == Symbol("USDTTMN")
        assert market.base == "USDT"
        assert market.quote == "TMN"
        assert market.price_precision == 2
        assert market.amount_precision == 4
        assert market.is_spot is True

    def test_market_skip_non_spot(self):
        data = {
            "symbol": "BTCUSDT_PERP",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "pricePrecision": 2,
            "amountPrecision": 4,
            "isSpot": False,
        }
        market = Market.from_api_response(data)
        assert market.is_spot is False

    def test_market_missing_precision_raises(self):
        data = {
            "symbol": "USDTTMN",
            "baseAsset": "USDT",
            "quoteAsset": "TMN",
            # missing pricePrecision and amountPrecision
            "isSpot": True,
        }
        with pytest.raises(ValueError, match="precision"):
            Market.from_api_response(data)

    def test_market_unknown_precision_explicit_error(self):
        data = {
            "symbol": "USDTTMN",
            "baseAsset": "USDT",
            "quoteAsset": "TMN",
            "pricePrecision": None,
            "amountPrecision": 4,
            "isSpot": True,
        }
        with pytest.raises(ValueError, match="precision"):
            Market.from_api_response(data)

    def test_market_price_precision_step(self):
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        assert market.price_step == Decimal("0.01")
        assert market.amount_step == Decimal("0.0001")

    def test_market_quantize_price(self):
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        assert market.quantize_price(Decimal("123.456")) == Decimal("123.45")
        assert market.quantize_price(Decimal("123.45")) == Decimal("123.45")

    def test_market_quantize_amount(self):
        market = Market(
            symbol=Symbol("USDTTMN"),
            base="USDT",
            quote="TMN",
            price_precision=2,
            amount_precision=4,
            is_spot=True,
        )
        assert market.quantize_amount(Decimal("1.23456")) == Decimal("1.2345")
        assert market.quantize_amount(Decimal("1.2345")) == Decimal("1.2345")


class TestEnums:
    """Tests for domain enums."""

    def test_side_enum(self):
        assert Side.BUY.value == "BUY"
        assert Side.SELL.value == "SELL"

    def test_order_type_enum(self):
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.STOP_LIMIT.value == "STOP_LIMIT"
        assert OrderType.STOP_MARKET.value == "STOP_MARKET"

    def test_order_status_enum(self):
        assert OrderStatus.NEW.value == "NEW"
        assert OrderStatus.PARTIALLY_FILLED.value == "PARTIALLY_FILLED"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.CANCELED.value == "CANCELED"
        assert OrderStatus.REJECTED.value == "REJECTED"
        assert OrderStatus.UNKNOWN.value == "UNKNOWN"

    def test_order_status_unknown_wire_value(self):
        # Unknown wire values should map to UNKNOWN, not crash
        assert OrderStatus.from_wire("SOME_NEW_STATUS") == OrderStatus.UNKNOWN
        assert OrderStatus.from_wire("") == OrderStatus.UNKNOWN
        assert OrderStatus.from_wire(None) == OrderStatus.UNKNOWN
