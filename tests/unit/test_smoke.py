"""Smoke test to verify the package is importable and has a version."""

import wallexbot


def test_version_exists():
    """Test that the package has a version attribute."""
    assert hasattr(wallexbot, "__version__")
    assert isinstance(wallexbot.__version__, str)
    assert len(wallexbot.__version__) > 0


def test_version_format():
    """Test that version follows semantic versioning (major.minor.patch)."""
    parts = wallexbot.__version__.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit()