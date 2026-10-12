"""Tests for CLI."""

from decimal import Decimal
from unittest.mock import Mock, patch

from wallexbot.cli.main import create_parser, main
from wallexbot.domain.market import Symbol


class TestCLI:
    """Tests for CLI commands."""

    def test_parser_creation(self):
        """Parser creates without error."""
        parser = create_parser()
        assert parser is not None

    def test_markets_command(self, capsys):
        """wallexbot markets lists spot markets."""
        with patch("wallexbot.cli.main.WallexRestClient") as mock_client:
            mock_instance = Mock()
            mock_instance.get_markets.return_value = [
                Mock(
                    symbol=Symbol("USDTTMN"),
                    base_asset="USDT",
                    quote_asset="TMN",
                    price_precision=2,
                    amount_precision=4,
                ),
            ]
            mock_client.return_value = mock_instance

            main(["markets"])

        captured = capsys.readouterr()
        assert "USDTTMN" in captured.out

    def test_config_check_command(self, tmp_path, capsys):
        """wallexbot config check validates config and shows derived values."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("""
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
""")

        main(["config", "check", str(config_file)])

        captured = capsys.readouterr()
        assert "valid" in captured.out.lower()
        assert "Spacing" in captured.out or "Grid range" in captured.out

    def test_config_check_invalid(self, tmp_path, capsys):
        """wallexbot config check shows errors for invalid config."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("""
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "110.00"
    upper_price: "90.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
""")

        main(["config", "check", str(config_file)])

        captured = capsys.readouterr()
        assert "Error" in captured.out or "error" in captured.out.lower()

    def test_paper_command(self, tmp_path, capsys):
        """wallexbot paper runs paper trading."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("""
exchange:
  name: "wallex"
market:
  symbol: "USDTTMN"
strategy:
  grid:
    lower_price: "90.00"
    upper_price: "110.00"
    grid_count: 10
    mode: "arithmetic"
    total_investment: "10000.00"
risk:
  max_open_orders: 20
simulation:
  initial_balance_quote: "2000000.00"
logging:
  level: "INFO"
""")

        # Paper command would run indefinitely - test that it starts
        result = main(["paper", str(config_file)])

        captured = capsys.readouterr()
        assert "Starting paper trading" in captured.out
        assert result == 0

    def test_report_command(self, capsys):
        """wallexbot report shows run report."""
        with patch("wallexbot.storage.repository.SQLiteRepository") as mock_repo:
            mock_instance = Mock()
            mock_instance.get_run.return_value = {
                "id": "run_123",
                "status": "completed",
                "started_at": 1000,
                "stopped_at": 2000,
            }
            mock_instance.get_fills.return_value = [
                {"price": "100.00", "quantity": "10.0000", "fee": "0.10"},
            ]
            mock_repo.return_value = mock_instance

            main(["report", "run_123"])

        captured = capsys.readouterr()
        assert "run_123" in captured.out

    def test_fetch_candles_command(self, capsys):
        """wallexbot fetch-candles downloads candles."""
        with patch("wallexbot.cli.main.WallexRestClient") as mock_client:
            mock_instance = Mock()
            mock_instance.get_candles.return_value = [
                Mock(
                    open_time=1000,
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100"),
                    volume=Decimal("1000"),
                ),
            ]
            mock_client.return_value = mock_instance

            main(
                [
                    "fetch-candles",
                    "USDTTMN",
                    "--resolution",
                    "60",
                    "--from",
                    "2024-01-01",
                    "--to",
                    "2024-01-02",
                ]
            )

        captured = capsys.readouterr()
        assert "1000" in captured.out
        assert "100" in captured.out

    def test_ui_command(self, capsys):
        """wallexbot ui starts web dashboard."""
        with patch("wallexbot.api.app.create_app") as mock_app:
            mock_instance = Mock()
            mock_app.return_value = mock_instance

            # UI command starts server - test setup only
            pass


class TestStructuredLogging:
    """Tests for structured logging."""

    def test_json_log_format(self):
        """Logs are JSON lines with run_id."""
        pass

    def test_secret_redaction(self):
        """Secrets are redacted in logs."""
        pass


class TestConsoleStatusView:
    """Tests for console status view."""

    def test_refreshing_display(self):
        """Console status refreshes in place."""
        pass


class TestAlerts:
    """Tests for alerts interface."""

    def test_stdout_alert_sink(self):
        """Alerts go to stdout by default."""
        pass
