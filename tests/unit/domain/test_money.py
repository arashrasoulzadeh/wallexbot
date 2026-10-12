"""Tests for money math helpers."""

from decimal import Decimal

import pytest

from wallexbot.domain.money import parse_wire_string, quantize_down, quantize_to_precision


class TestQuantizeDown:
    """Tests for quantize_down: round toward zero to a step/precision."""

    def test_quantize_down_basic(self):
        assert quantize_down(Decimal("1.2345"), Decimal("0.01")) == Decimal("1.23")
        assert quantize_down(Decimal("1.2399"), Decimal("0.01")) == Decimal("1.23")
        assert quantize_down(Decimal("-1.2345"), Decimal("0.01")) == Decimal("-1.23")

    def test_quantize_down_to_precision(self):
        assert quantize_down(Decimal("1.234567"), Decimal("0.0001")) == Decimal("1.2345")
        assert quantize_down(Decimal("100.999"), Decimal("1")) == Decimal("100")

    def test_quantize_down_idempotent(self):
        value = Decimal("1.2345")
        step = Decimal("0.01")
        result = quantize_down(value, step)
        assert quantize_down(result, step) == result

    def test_quantize_down_never_increases_magnitude(self):
        step = Decimal("0.01")
        for val in [Decimal("1.234"), Decimal("-1.234"), Decimal("0.009"), Decimal("-0.009")]:
            result = quantize_down(val, step)
            assert abs(result) <= abs(val)

    def test_quantize_down_returns_decimal(self):
        result = quantize_down(Decimal("1.23"), Decimal("0.01"))
        assert isinstance(result, Decimal)

    def test_quantize_down_rejects_float(self):
        with pytest.raises(TypeError, match="float"):
            quantize_down(1.23, Decimal("0.01"))  # type: ignore
        with pytest.raises(TypeError, match="float"):
            quantize_down(Decimal("1.23"), 0.01)  # type: ignore

    def test_quantize_down_zero_step_raises(self):
        with pytest.raises(ValueError, match="step"):
            quantize_down(Decimal("1.23"), Decimal("0"))


class TestQuantizeToPrecision:
    """Tests for quantize_to_precision: round to specific decimal places."""

    def test_quantize_to_precision_basic(self):
        assert quantize_to_precision(Decimal("1.234567"), 2) == Decimal("1.23")
        assert quantize_to_precision(Decimal("1.239999"), 2) == Decimal("1.23")
        assert quantize_to_precision(Decimal("-1.234567"), 2) == Decimal("-1.23")

    def test_quantize_to_precision_zero_digits(self):
        assert quantize_to_precision(Decimal("123.456"), 0) == Decimal("123")
        assert quantize_to_precision(Decimal("-123.456"), 0) == Decimal("-123")

    def test_quantize_to_precision_idempotent(self):
        value = Decimal("1.234567")
        result = quantize_to_precision(value, 4)
        assert quantize_to_precision(result, 4) == result

    def test_quantize_to_precision_never_increases_magnitude(self):
        for val in [Decimal("1.234"), Decimal("-1.234"), Decimal("0.009"), Decimal("-0.009")]:
            result = quantize_to_precision(val, 2)
            assert abs(result) <= abs(val)

    def test_quantize_to_precision_rejects_float(self):
        with pytest.raises(TypeError, match="float"):
            quantize_to_precision(1.23, 2)  # type: ignore

    def test_quantize_to_precision_negative_digits_raises(self):
        with pytest.raises(ValueError, match="digits"):
            quantize_to_precision(Decimal("1.23"), -1)


class TestParseWireString:
    """Tests for parsing wire format strings from API."""

    def test_parse_integer_string(self):
        assert parse_wire_string("82494") == Decimal("82494")

    def test_parse_decimal_string(self):
        assert parse_wire_string("0.00001136") == Decimal("0.00001136")

    def test_parse_trailing_zeros(self):
        assert parse_wire_string("255.7500000000000000") == Decimal("255.75")

    def test_parse_scientific_notation(self):
        assert parse_wire_string("1.23E-5") == Decimal("0.0000123")

    def test_parse_returns_decimal(self):
        result = parse_wire_string("123.45")
        assert isinstance(result, Decimal)

    def test_parse_rejects_float(self):
        with pytest.raises(TypeError, match="float"):
            parse_wire_string(123.45)  # type: ignore

    def test_parse_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            parse_wire_string("not-a-number")


class TestPropertyQuantize:
    """Property-based tests for quantize functions."""

    def test_quantize_down_property_idempotent(self):
        from hypothesis import given
        from hypothesis import strategies as st

        @given(
            st.decimals(min_value=-1000, max_value=1000, places=10),
            st.decimals(min_value=0.00000001, max_value=100, places=8).filter(lambda x: x > 0),
        )
        def test_impl(value: Decimal, step: Decimal):
            result = quantize_down(value, step)
            assert quantize_down(result, step) == result
            assert abs(result) <= abs(value)

        test_impl()

    def test_quantize_to_precision_property_idempotent(self):
        from hypothesis import given
        from hypothesis import strategies as st

        @given(
            st.decimals(min_value=-1000, max_value=1000, places=10),
            st.integers(min_value=0, max_value=8),
        )
        def test_impl(value: Decimal, digits: int):
            result = quantize_to_precision(value, digits)
            assert quantize_to_precision(result, digits) == result
            assert abs(result) <= abs(value)

        test_impl()
