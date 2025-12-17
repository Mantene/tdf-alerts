"""
Unit tests for TDF Title Monitor
Run with: pytest test_tdf_monitor.py -v
"""

import os
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

# Import the modules to test (assuming main script is named tdf_monitor.py)
import sys
sys.path.insert(0, os.path.dirname(__file__))

from tdf_monitor import (
    ConfigManager,
    StateManager,
    TitleAvailability,
    TDFScraper,
    NotificationHandler
)


class TestConfigManager:
    """Tests for ConfigManager class"""
    
    def test_load_valid_config(self, tmp_path):
        """Test loading a valid configuration file"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
tdf_credentials:
  email: test@example.com
  password: testpass123
titles:
  - Title One
  - Title Two
notifications:
  method: console
""")
        
        config_manager = ConfigManager(str(config_file))
        assert config_manager.config is not None
        assert config_manager.get_titles() == ['Title One', 'Title Two']
    
    def test_missing_config_file(self):
        """Test handling of missing configuration file"""
        with pytest.raises(FileNotFoundError):
            ConfigManager("nonexistent.yaml")
    
    def test_invalid_yaml_format(self, tmp_path):
        """Test handling of invalid YAML format"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: content: :")
        
        with pytest.raises(Exception):
            ConfigManager(str(config_file))
    
    def test_missing_required_fields(self, tmp_path):
        """Test validation of missing required fields"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
tdf_credentials:
  email: test@example.com
""")
        
        with pytest.raises(ValueError):
            ConfigManager(str(config_file))
    
    def test_empty_titles_list(self, tmp_path):
        """Test validation of empty titles list"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
tdf_credentials:
  email: test@example.com
  password: testpass
titles: []
notifications:
  method: console
""")
        
        with pytest.raises(ValueError):
            ConfigManager(str(config_file))
    
    def test_environment_variable_override(self, tmp_path, monkeypatch):
        """Test that environment variables override config file"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
tdf_credentials:
  email: config@example.com
  password: configpass
titles:
  - Test Title
notifications:
  method: console
""")
        
        monkeypatch.setenv('TDF_EMAIL', 'env@example.com')
        monkeypatch.setenv('TDF_PASSWORD', 'envpass')
        
        config_manager = ConfigManager(str(config_file))
        email, password = config_manager.get_credentials()
        
        assert email == 'env@example.com'
        assert password == 'envpass'
    
    def test_get_filter_date(self, tmp_path):
        """Test retrieving filter date"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
tdf_credentials:
  email: test@example.com
  password: testpass
titles:
  - Test Title
filter_date: "12/25/2025"
notifications:
  method: console
""")
        
        config_manager = ConfigManager(str(config_file))
        assert config_manager.get_filter_date() == "12/25/2025"
    
    def test_no_filter_date(self, tmp_path):
        """Test when no filter date is provided"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
tdf_credentials:
  email: test@example.com
  password: testpass
titles:
  - Test Title
notifications:
  method: console
""")
        
        config_manager = ConfigManager(str(config_file))
        assert config_manager.get_filter_date() is None


class TestStateManager:
    """Tests for StateManager class"""
    
    def test_initial_state_no_file(self, tmp_path):
        """Test initialization with no existing state file"""
        state_file = tmp_path / "state.json"
        state_manager = StateManager(str(state_file))
        
        assert state_manager.state == {}
    
    def test_load_existing_state(self, tmp_path):
        """Test loading existing state from file"""
        state_file = tmp_path / "state.json"
        initial_state = {
            "Hamilton": ["12/25/2025", "12/26/2025"],
            "Wicked": ["12/27/2025"]
        }
        state_file.write_text(json.dumps(initial_state))
        
        state_manager = StateManager(str(state_file))
        assert state_manager.state == initial_state
    
    def test_should_alert_new_title(self, tmp_path):
        """Test that should_alert returns True for new titles"""
        state_file = tmp_path / "state.json"
        state_manager = StateManager(str(state_file))
        
        assert state_manager.should_alert("New Title", ["12/25/2025"]) is True
    
    def test_should_alert_no_new_dates(self, tmp_path):
        """Test that should_alert returns False when no new dates"""
        state_file = tmp_path / "state.json"
        state_manager = StateManager(str(state_file))
        state_manager.state = {
            "Hamilton": ["12/25/2025", "12/26/2025"]
        }
        
        assert state_manager.should_alert("Hamilton", ["12/25/2025"]) is False
    
    def test_should_alert_with_new_dates(self, tmp_path):
        """Test that should_alert returns True when new dates exist"""
        state_file = tmp_path / "state.json"
        state_manager = StateManager(str(state_file))
        state_manager.state = {
            "Hamilton": ["12/25/2025"]
        }
        
        assert state_manager.should_alert("Hamilton", ["12/25/2025", "12/26/2025"]) is True
    
    def test_get_new_dates(self, tmp_path):
        """Test getting only new dates"""
        state_file = tmp_path / "state.json"
        state_manager = StateManager(str(state_file))
        state_manager.state = {
            "Hamilton": ["12/25/2025"]
        }
        
        new_dates = state_manager.get_new_dates(
            "Hamilton", 
            ["12/25/2025", "12/26/2025", "12/27/2025"]
        )
        
        assert set(new_dates) == {"12/26/2025", "12/27/2025"}
    
    def test_update_state_new_title(self, tmp_path):
        """Test updating state with a new title"""
        state_file = tmp_path / "state.json"
        state_manager = StateManager(str(state_file))
        
        state_manager.update_state("New Title", ["12/25/2025"])
        
        assert "New Title" in state_manager.state
        assert state_manager.state["New Title"] == ["12/25/2025"]
    
    def test_update_state_merge_dates(self, tmp_path):
        """Test that update_state merges dates for existing titles"""
        state_file = tmp_path / "state.json"
        state_manager = StateManager(str(state_file))
        state_manager.state = {
            "Hamilton": ["12/25/2025"]
        }
        
        state_manager.update_state("Hamilton", ["12/26/2025", "12/27/2025"])
        
        assert set(state_manager.state["Hamilton"]) == {
            "12/25/2025", "12/26/2025", "12/27/2025"
        }
    
    def test_state_persistence(self, tmp_path):
        """Test that state is persisted to file"""
        state_file = tmp_path / "state.json"
        state_manager = StateManager(str(state_file))
        
        state_manager.update_state("Test Title", ["12/25/2025"])
        
        # Load state again to verify persistence
        state_manager2 = StateManager(str(state_file))
        assert state_manager2.state["Test Title"] == ["12/25/2025"]
    
    def test_invalid_json_recovery(self, tmp_path):
        """Test recovery from corrupted state file"""
        state_file = tmp_path / "state.json"
        state_file.write_text("invalid json content {")
        
        state_manager = StateManager(str(state_file))
        assert state_manager.state == {}


class TestTitleAvailability:
    """Tests for TitleAvailability dataclass"""
    
    def test_create_title_availability(self):
        """Test creating TitleAvailability object"""
        title = TitleAvailability(
            title="Hamilton",
            dates=["12/25/2025", "12/26/2025"],
            url="https://example.com"
        )
        
        assert title.title == "Hamilton"
        assert len(title.dates) == 2
        assert title.url == "https://example.com"
    
    def test_title_availability_hash(self):
        """Test that titles can be hashed (for sets/dicts)"""
        title1 = TitleAvailability(title="Hamilton", dates=["12/25/2025"])
        title2 = TitleAvailability(title="Hamilton", dates=["12/26/2025"])
        
        # Same title should hash the same
        assert hash(title1) == hash(title2)
    
    def test_optional_url(self):
        """Test that URL is optional"""
        title = TitleAvailability(title="Test", dates=["12/25/2025"])
        assert title.url is None


class TestTDFScraper:
    """Tests for TDFScraper class"""
    
    def test_scraper_initialization(self):
        """Test TDFScraper initialization"""
        scraper = TDFScraper("test@example.com", "password123")
        
        assert scraper.email == "test@example.com"
        assert scraper.password == "password123"
        assert scraper.LOGIN_URL == "https://my.tdf.org/account/login"
    
    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful login"""
        scraper = TDFScraper("test@example.com", "password")
        
        # Mock page object
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.url = "https://nycgw47.tdf.org/TDFCustomOfferings/Current"
        mock_page.query_selector_all = AsyncMock(return_value=[])
        
        result = await scraper.login(mock_page)
        
        assert result is True
        mock_page.goto.assert_called_once()
        assert mock_page.fill.call_count == 2  # email and password
    
    @pytest.mark.asyncio
    async def test_login_with_error_message(self):
        """Test login failure with error message on page"""
        scraper = TDFScraper("test@example.com", "wrongpassword")
        
        # Mock page with error element
        mock_error = AsyncMock()
        mock_error.text_content = AsyncMock(return_value="Invalid credentials")
        
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[mock_error])
        
        result = await scraper.login(mock_page)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_navigate_to_offerings(self):
        """Test navigation to offerings page"""
        scraper = TDFScraper("test@example.com", "password")
        
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        
        await scraper.navigate_to_offerings(mock_page)
        
        mock_page.goto.assert_called_once_with(
            scraper.OFFERINGS_URL,
            wait_until='networkidle',
            timeout=30000
        )
    
    @pytest.mark.asyncio
    async def test_apply_date_filter(self):
        """Test applying date filter"""
        scraper = TDFScraper("test@example.com", "password")
        
        mock_input = AsyncMock()
        mock_input.fill = AsyncMock()
        
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_input)
        mock_page.wait_for_timeout = AsyncMock()
        
        await scraper.apply_date_filter(mock_page, "12/25/2025")
        
        mock_input.fill.assert_called_once_with("12/25/2025")


class TestNotificationHandler:
    """Tests for NotificationHandler class"""
    
    def test_notification_handler_initialization(self):
        """Test NotificationHandler initialization"""
        config = {'method': 'email'}
        handler = NotificationHandler(config)
        
        assert handler.method == 'email'
    
    def test_format_alert_with_date_filter(self):
        """Test formatting alert message with date filter"""
        config = {'method': 'console'}
        handler = NotificationHandler(config)
        
        results = [
            TitleAvailability(
                title="Hamilton",
                dates=["12/25/2025"],
                url="https://example.com/hamilton"
            )
        ]
        
        message = handler.format_alert_message(results, "12/25/2025")
        
        assert "Hamilton" in message
        assert "12/25/2025" in message
        assert "Filter Date" in message
    
    def test_format_alert_without_date_filter(self):
        """Test formatting alert message without date filter"""
        config = {'method': 'console'}
        handler = NotificationHandler(config)
        
        results = [
            TitleAvailability(
                title="Hamilton",
                dates=["12/25/2025", "12/26/2025"],
                url="https://example.com/hamilton"
            )
        ]
        
        message = handler.format_alert_message(results)
        
        assert "Hamilton" in message
        assert "12/25/2025" in message
        assert "12/26/2025" in message
        assert "Available Dates" in message
    
    def test_format_alert_empty_results(self):
        """Test formatting alert with empty results"""
        config = {'method': 'console'}
        handler = NotificationHandler(config)
        
        message = handler.format_alert_message([])
        
        assert message == "No titles found."
    
    def test_format_alert_multiple_titles(self):
        """Test formatting alert with multiple titles"""
        config = {'method': 'console'}
        handler = NotificationHandler(config)
        
        results = [
            TitleAvailability(title="Hamilton", dates=["12/25/2025"]),
            TitleAvailability(title="Wicked", dates=["12/26/2025"])
        ]
        
        message = handler.format_alert_message(results)
        
        assert "Hamilton" in message
        assert "Wicked" in message
    
    @pytest.mark.asyncio
    async def test_send_notification_console(self, capsys):
        """Test sending console notification"""
        config = {'method': 'console'}
        handler = NotificationHandler(config)
        
        results = [
            TitleAvailability(title="Test Title", dates=["12/25/2025"])
        ]
        
        await handler.send_notification(results)
        
        captured = capsys.readouterr()
        assert "Test Title" in captured.out
    
    @pytest.mark.asyncio
    async def test_send_notification_empty_results(self):
        """Test that no notification is sent for empty results"""
        config = {'method': 'console'}
        handler = NotificationHandler(config)
        
        # Should not raise an error
        await handler.send_notification([])
    
    @pytest.mark.asyncio
    async def test_unknown_notification_method(self):
        """Test handling of unknown notification method"""
        config = {'method': 'unknown_method'}
        handler = NotificationHandler(config)
        
        results = [TitleAvailability(title="Test", dates=["12/25/2025"])]
        
        # Should not raise an error, just log
        await handler.send_notification(results)


class TestIntegration:
    """Integration tests for main workflow"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow_with_state(self, tmp_path):
        """Test complete workflow with state management"""
        # Setup
        config_file = tmp_path / "config.yaml"
        state_file = tmp_path / "state.json"
        
        config_file.write_text("""
tdf_credentials:
  email: test@example.com
  password: testpass
titles:
  - Hamilton
notifications:
  method: console
""")
        
        # First run - should alert
        state_manager = StateManager(str(state_file))
        
        result = TitleAvailability(
            title="Hamilton",
            dates=["12/25/2025", "12/26/2025"]
        )
        
        assert state_manager.should_alert(result.title, result.dates) is True
        state_manager.update_state(result.title, result.dates)
        
        # Second run - same dates, should not alert
        assert state_manager.should_alert(result.title, result.dates) is False
        
        # Third run - new date added, should alert
        new_result = TitleAvailability(
            title="Hamilton",
            dates=["12/25/2025", "12/26/2025", "12/27/2025"]
        )
        
        assert state_manager.should_alert(new_result.title, new_result.dates) is True
        new_dates = state_manager.get_new_dates(new_result.title, new_result.dates)
        assert new_dates == ["12/27/2025"]


# Test fixtures
@pytest.fixture
def sample_config(tmp_path):
    """Create a sample configuration file"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
tdf_credentials:
  email: test@example.com
  password: testpass
titles:
  - Hamilton
  - Wicked
notifications:
  method: console
""")
    return str(config_file)


@pytest.fixture
def sample_state(tmp_path):
    """Create a sample state file"""
    state_file = tmp_path / "state.json"
    initial_state = {
        "Hamilton": ["12/25/2025"]
    }
    state_file.write_text(json.dumps(initial_state))
    return str(state_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=tdf_monitor", "--cov-report=term-missing"])