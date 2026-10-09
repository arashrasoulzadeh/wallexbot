"""Money math helpers using Decimal for precise financial calculations."""

from decimal import Decimal, ROUND_DOWN, InvalidOperation


def quantize_down(value: Decimal, step: Decimal) -> Decimal:
    """
    Round `value` down toward zero to the nearest multiple of `step`.

    Args:
        value: The value to quantize (must be Decimal)
        step: The quantization step (must be Decimal > 0)

    Returns:
        Decimal quantized down to step precision

    Raises:
        TypeError: If value or step is not a Decimal
        ValueError: If step is zero or negative
    """
    _require_decimal(value, "value")
    _require_decimal(step, "step")

    if step <= 0:
        raise ValueError("step must be positive")

    if value == 0:
        return Decimal("0")

    # Calculate how many steps fit in the absolute value, then multiply back
    # This rounds toward zero (truncates)
    steps = (abs(value) // step) * step
    result = steps.copy_sign(value)

    # Ensure we didn't increase magnitude due to precision issues
    assert abs(result) <= abs(value) + Decimal("1e-20"), "quantize_down increased magnitude"
    return result


def quantize_to_precision(value: Decimal, digits: int) -> Decimal:
    """
    Round `value` down toward zero to `digits` decimal places.

    Args:
        value: The value to quantize (must be Decimal)
        digits: Number of decimal places (must be >= 0)

    Returns:
        Decimal quantized to the specified precision

    Raises:
        TypeError: If value is not a Decimal
        ValueError: If digits is negative
    """
    _require_decimal(value, "value")

    if digits < 0:
        raise ValueError("digits must be non-negative")

    if value == 0:
        return Decimal("0")

    # Create quantize exponent (e.g., 2 -> Decimal('0.01'))
    exp = Decimal("1") / (Decimal("10") ** digits)
    result = value.quantize(exp, rounding=ROUND_DOWN)

    # Ensure we didn't increase magnitude
    assert abs(result) <= abs(value) + Decimal("1e-20"), "quantize_to_precision increased magnitude"
    return result


def parse_wire_string(s: str) -> Decimal:
    """
    Parse a wire-format string (from API) to Decimal.

    Handles:
    - Integer strings: "82494"
    - Decimal strings: "0.00001136"
    - Trailing zeros: "255.7500000000000000"
    - Scientific notation: "1.23E-5"

    Args:
        s: String representation of a number

    Returns:
        Decimal value

    Raises:
        TypeError: If input is not a string
        ValueError: If string cannot be parsed as a number
    """
    if not isinstance(s, str):
        raise TypeError(f"Expected string, got {type(s).__name__} (float not allowed)")

    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f"Invalid wire string: {s!r}") from e


def _require_decimal(value: object, name: str) -> None:
    """Raise TypeError if value is not a Decimal."""
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal, not {type(value).__name__} (float not allowed)")