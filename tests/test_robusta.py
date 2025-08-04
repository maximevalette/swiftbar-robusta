#!/usr/bin/env python3
"""Unit tests for the SwiftBar Robusta plugin."""

import sys
import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, mock_open

# Add parent directory to path to import the plugin
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import after path is set
import importlib.util

spec = importlib.util.spec_from_file_location("robusta_plugin", "robusta.5m.py")
robusta_plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(robusta_plugin)

# Import classes and functions from the plugin
Alert = robusta_plugin.Alert
ClusterConfig = robusta_plugin.ClusterConfig
DisplayConfig = robusta_plugin.DisplayConfig
RobustaAPI = robusta_plugin.RobustaAPI
SwiftBarRenderer = robusta_plugin.SwiftBarRenderer
detect_changes = robusta_plugin.detect_changes
load_state = robusta_plugin.load_state
save_state = robusta_plugin.save_state


class TestAlert:
    """Test the Alert dataclass."""

    def test_alert_creation(self):
        """Test creating an Alert instance."""
        alert = Alert(
            alert_name="PodCrashLooping",
            title="Pod is crash looping",
            description="Pod app-1 is restarting frequently",
            source="prometheus",
            priority="HIGH",
            started_at="2025-01-15T10:30:00.000Z",
            resolved_at=None,
            cluster="prod-cluster",
            namespace="default",
            app="frontend",
            kind="Pod",
            resource_name="app-1",
            resource_node="node-1",
        )

        assert alert.alert_name == "PodCrashLooping"
        assert alert.priority == "HIGH"
        assert alert.resolved_at is None

    def test_alert_unique_id(self):
        """Test Alert unique ID generation."""
        alert = Alert(
            alert_name="PodCrashLooping",
            title="Pod is crash looping",
            description=None,
            source="prometheus",
            priority="HIGH",
            started_at="2025-01-15T10:30:00.000Z",
            resolved_at=None,
            cluster="prod-cluster",
            namespace="default",
            app="frontend",
            kind="Pod",
            resource_name="app-1",
            resource_node="node-1",
        )

        expected_id = (
            "prod-cluster:PodCrashLooping:default:app-1:2025-01-15T10:30:00.000Z"
        )
        assert alert.get_unique_id() == expected_id

    def test_alert_priority_properties(self):
        """Test Alert priority-related properties."""
        alert = Alert(
            alert_name="test",
            title="Test alert",
            description=None,
            source="test",
            priority="CRITICAL",
            started_at="2025-01-15T10:30:00.000Z",
            resolved_at=None,
            cluster="test",
            namespace="test",
            app="test",
            kind="test",
            resource_name="test",
            resource_node="test",
        )

        assert alert.priority_weight == 4
        assert alert.priority_symbol == " ✗"
        assert alert.priority_color == "#EF5B58"

    def test_alert_age(self):
        """Test Alert age calculation."""
        # Create alert that started 2 hours ago
        started = datetime.now(timezone.utc) - timedelta(hours=2)
        alert = Alert(
            alert_name="test",
            title="Test alert",
            description=None,
            source="test",
            priority="HIGH",
            started_at=started.isoformat(),
            resolved_at=None,
            cluster="test",
            namespace="test",
            app="test",
            kind="test",
            resource_name="test",
            resource_node="test",
        )

        assert alert.age == "2h"

    def test_alert_is_stale(self):
        """Test Alert stale detection."""
        # Create alert that started 25 hours ago (stale)
        started = datetime.now(timezone.utc) - timedelta(hours=25)
        stale_alert = Alert(
            alert_name="test",
            title="Test alert",
            description=None,
            source="test",
            priority="LOW",
            started_at=started.isoformat(),
            resolved_at=None,
            cluster="test",
            namespace="test",
            app="test",
            kind="test",
            resource_name="test",
            resource_node="test",
        )

        assert stale_alert.is_stale is True

        # Create fresh alert
        started = datetime.now(timezone.utc) - timedelta(hours=1)
        fresh_alert = Alert(
            alert_name="test",
            title="Test alert",
            description=None,
            source="test",
            priority="LOW",
            started_at=started.isoformat(),
            resolved_at=None,
            cluster="test",
            namespace="test",
            app="test",
            kind="test",
            resource_name="test",
            resource_node="test",
        )

        assert fresh_alert.is_stale is False


class TestRobustaAPI:
    """Test the RobustaAPI class."""

    def test_api_initialization(self):
        """Test RobustaAPI initialization."""
        config = ClusterConfig(
            name="test-cluster",
            account_id="test-account",
            api_key="test-key",
            base_url="https://api.test.com",
            timeout=30,
        )

        api = RobustaAPI(config)
        assert api.config == config
        assert api.session.headers["Authorization"] == "Bearer test-key"
        assert api.session.headers["Content-Type"] == "application/json"

    @patch("requests.Session.get")
    def test_fetch_alert_report_success(self, mock_get):
        """Test successful alert report fetching."""
        config = ClusterConfig(
            name="test-cluster", account_id="test-account", api_key="test-key"
        )
        api = RobustaAPI(config)

        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = [
            {"aggregation_key": "PodCrashLooping", "alert_count": 5},
            {"aggregation_key": "NodeNotReady", "alert_count": 2},
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        end_time = datetime.now(timezone.utc)

        result = api.fetch_alert_report(start_time, end_time)

        assert len(result) == 2
        assert result[0]["aggregation_key"] == "PodCrashLooping"
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    def test_fetch_unresolved_alerts(self, mock_get):
        """Test fetching unresolved alerts."""
        config = ClusterConfig(
            name="test-cluster", account_id="test-account", api_key="test-key"
        )
        api = RobustaAPI(config)

        # First call returns report
        report_response = Mock()
        report_response.json.return_value = [
            {"aggregation_key": "PodCrashLooping", "alert_count": 1}
        ]
        report_response.raise_for_status = Mock()

        # Second call returns alerts
        alerts_response = Mock()
        alerts_response.json.return_value = [
            {
                "alert_name": "PodCrashLooping",
                "title": "Pod is crash looping",
                "description": "Pod app-1 is restarting",
                "source": "prometheus",
                "priority": "HIGH",
                "started_at": "2025-01-15T10:30:00.000Z",
                "resolved_at": None,
                "namespace": "default",
                "app": "frontend",
                "kind": "Pod",
                "resource_name": "app-1",
                "resource_node": "node-1",
            }
        ]
        alerts_response.raise_for_status = Mock()

        # Create empty responses for additional alert types
        empty_response = Mock()
        empty_response.json.return_value = []
        empty_response.raise_for_status = Mock()
        
        mock_get.side_effect = [
            report_response,  # Initial report fetch
            alerts_response,  # PodCrashLooping alerts
            empty_response,   # CrashLoopBackoff
            empty_response,   # JobFailure
            empty_response    # ImagePullBackoff
        ]

        alerts = api.fetch_unresolved_alerts(hours_back=24)

        assert len(alerts) == 1
        assert alerts[0].alert_name == "PodCrashLooping"
        assert alerts[0].priority == "HIGH"
        assert alerts[0].cluster == "test-cluster"

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        config = ClusterConfig(name="test", account_id="test", api_key="test")
        api = RobustaAPI(config)

        dt = datetime(2025, 1, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)
        formatted = api._format_timestamp(dt)

        assert formatted == "2025-01-15T10:30:45.123Z"


class TestSwiftBarRenderer:
    """Test the SwiftBarRenderer class."""

    def test_sanitize_for_menu(self):
        """Test text sanitization for menu display."""
        config = DisplayConfig()
        renderer = SwiftBarRenderer(config)

        # Test newline removal
        text = "Line 1\nLine 2\rLine 3"
        sanitized = renderer._sanitize_for_menu(text)
        assert sanitized == "Line 1 Line 2 Line 3"

        # Test multiple spaces collapse
        text = "Too    many     spaces"
        sanitized = renderer._sanitize_for_menu(text)
        assert sanitized == "Too many spaces"

        # Test None handling
        assert renderer._sanitize_for_menu(None) is None

    @patch("builtins.print")
    def test_render_menu_bar_title(self, mock_print):
        """Test menu bar title rendering."""
        config = DisplayConfig()
        renderer = SwiftBarRenderer(config)

        # Test with no alerts
        renderer._render_menu_bar_title([])
        mock_print.assert_called_with(":bell:")
        mock_print.reset_mock()

        # Test with mixed priority alerts
        alerts = [
            Alert(
                alert_name="critical",
                title="Critical alert",
                description=None,
                source="test",
                priority="CRITICAL",
                started_at="2025-01-15T10:00:00Z",
                resolved_at=None,
                cluster="test",
                namespace="test",
                app="test",
                kind="test",
                resource_name="test",
                resource_node="test",
            ),
            Alert(
                alert_name="high",
                title="High alert",
                description=None,
                source="test",
                priority="HIGH",
                started_at="2025-01-15T10:00:00Z",
                resolved_at=None,
                cluster="test",
                namespace="test",
                app="test",
                kind="test",
                resource_name="test",
                resource_node="test",
            ),
        ]

        renderer._render_menu_bar_title(alerts)
        # Should show critical icon and count
        mock_print.assert_called_with(":exclamationmark.octagon.fill: C:1 H:1")


class TestStateManagement:
    """Test state management functions."""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"")
    @patch("pickle.load")
    def test_load_state_existing(self, mock_pickle_load, mock_file, mock_exists):
        """Test loading existing state."""
        mock_exists.return_value = True
        mock_pickle_load.return_value = {
            "alerts": {},
            "last_update": "2025-01-15T10:00:00Z",
        }

        state = load_state()

        assert "alerts" in state
        assert "last_update" in state

    @patch("pathlib.Path.exists")
    def test_load_state_new(self, mock_exists):
        """Test loading state when file doesn't exist."""
        mock_exists.return_value = False

        state = load_state()

        assert state == {}

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    @patch("pickle.dump")
    def test_save_state(self, mock_pickle_dump, mock_file, mock_mkdir):
        """Test saving state."""
        alerts = [
            Alert(
                alert_name="test",
                title="Test alert",
                description=None,
                source="test",
                priority="HIGH",
                started_at="2025-01-15T10:00:00Z",
                resolved_at=None,
                cluster="test",
                namespace="test",
                app="test",
                kind="test",
                resource_name="test",
                resource_node="test",
            )
        ]

        save_state(alerts)

        mock_mkdir.assert_called_once()
        mock_pickle_dump.assert_called_once()

        # Check that the state contains the alert
        saved_state = mock_pickle_dump.call_args[0][0]
        assert "alerts" in saved_state
        assert "last_update" in saved_state
        assert len(saved_state["alerts"]) == 1


class TestChangeDetection:
    """Test change detection functionality."""

    def test_detect_new_alerts(self):
        """Test detection of new alerts."""
        current_alerts = [
            Alert(
                alert_name="new_alert",
                title="New alert",
                description=None,
                source="test",
                priority="HIGH",
                started_at="2025-01-15T11:00:00Z",
                resolved_at=None,
                cluster="test",
                namespace="test",
                app="test",
                kind="test",
                resource_name="test",
                resource_node="test",
            )
        ]

        previous_state = {"alerts": {}, "last_update": "2025-01-15T10:00:00Z"}

        new_alerts, resolved_alerts = detect_changes(current_alerts, previous_state)

        assert len(new_alerts) == 1
        assert new_alerts[0].alert_name == "new_alert"
        assert len(resolved_alerts) == 0

    def test_detect_resolved_alerts(self):
        """Test detection of resolved alerts."""
        current_alerts = []

        previous_state = {
            "alerts": {
                "test:old_alert:test:test:2025-01-15T10:00:00Z": {
                    "alert_name": "old_alert",
                    "priority": "HIGH",
                }
            },
            "last_update": "2025-01-15T10:00:00Z",
        }

        new_alerts, resolved_alerts = detect_changes(current_alerts, previous_state)

        assert len(new_alerts) == 0
        assert len(resolved_alerts) == 1
        assert resolved_alerts[0]["alert_name"] == "old_alert"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
