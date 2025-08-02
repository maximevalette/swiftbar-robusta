#!/usr/bin/env uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "pyyaml",
#     "python-dateutil",
# ]
# ///

# <xbar.title>Robusta Alerts</xbar.title>
# <xbar.version>v1.1</xbar.version>
# <xbar.author>Maxime Valette</xbar.author>
# <xbar.author.github>maximevalette</xbar.author.github>
# <xbar.desc>Monitor unresolved Robusta alerts across multiple Kubernetes clusters</xbar.desc>
# <xbar.dependencies>uv</xbar.dependencies>
# <xbar.var>string(VAR_CONFIG_PATH="~/.config/swiftbar/robusta.yml"): Path to config file</xbar.var>

import sys
import os
import json
import yaml
import requests
import base64
import re
import pickle
import subprocess
from datetime import datetime, timedelta, timezone
from dateutil import parser
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

# Alert priority symbols and colors
SYMBOLS = {
    "CRITICAL": " ✗",
    "HIGH": " ⚠",
    "MEDIUM": " ⊙",
    "LOW": " ◦",
    "INFO": " ℹ",
    "unknown": " ⋯",
}

COLORS = {
    "CRITICAL": "#EF5B58",
    "HIGH": "#F3BA61",
    "MEDIUM": "#61D3E5",
    "LOW": "#39C988",
    "INFO": "#898989",
    "unknown": "#898989",
}

PRIORITY_WEIGHT = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "INFO": 0,
    "unknown": 0,
}


@dataclass
class Alert:
    alert_name: str
    title: str
    description: Optional[str]
    source: str
    priority: str
    started_at: str
    resolved_at: Optional[str]
    cluster: str
    namespace: str
    app: str
    kind: Optional[str]
    resource_name: str
    resource_node: str

    def get_unique_id(self) -> str:
        """Generate a unique identifier for this alert"""
        # Use a composite key
        return f"{self.cluster}:{self.alert_name}:{self.namespace}:{self.resource_name}:{self.started_at}"

    @property
    def priority_weight(self) -> int:
        return PRIORITY_WEIGHT.get(self.priority, 0)

    @property
    def priority_symbol(self) -> str:
        return SYMBOLS.get(self.priority, SYMBOLS["unknown"])

    @property
    def priority_color(self) -> str:
        return COLORS.get(self.priority, COLORS["unknown"])

    @property
    def age(self) -> str:
        """Calculate human-readable age of the alert"""
        started = parser.parse(self.started_at)
        now = datetime.now(timezone.utc)
        delta = now - started

        if delta.days > 0:
            return f"{delta.days}d"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600}h"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60}m"
        else:
            return f"{delta.seconds}s"

    @property
    def is_stale(self) -> bool:
        """Check if alert is older than configured stale threshold"""
        started = parser.parse(self.started_at)
        now = datetime.now(timezone.utc)
        return (now - started) > timedelta(hours=24)  # Default 24h threshold

    @property
    def robusta_url(self) -> Optional[str]:
        """Generate Robusta platform URL for this alert"""
        # This will be set after alert creation when we have access to the cluster config
        return getattr(self, "_robusta_url", None)


@dataclass
class ClusterConfig:
    name: str
    account_id: str
    api_key: str
    base_url: str = "https://api.robusta.dev"
    timeout: int = 30
    dashboard_url: Optional[str] = None


@dataclass
class DisplayConfig:
    show_cluster_in_title: bool = True
    show_age: bool = True
    show_namespace: bool = True
    stale_alert_hours: int = 24
    refresh_interval_minutes: int = 5
    debug: bool = False


class RobustaAPI:
    def __init__(self, config: ClusterConfig, debug: bool = False):
        self.config = config
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
        )

    def fetch_alert_report(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Fetch alert report with aggregation keys"""
        url = f"{self.config.base_url}/api/query/report"
        params = {
            "account_id": self.config.account_id,
            "start_ts": self._format_timestamp(start_time),
            "end_ts": self._format_timestamp(end_time),
        }

        if self.debug:
            print(f"🔍 DEBUG: Fetching report from {url}")
            print(f"🔍 DEBUG: Params: {json.dumps(params, indent=2)}")

        try:
            response = self.session.get(url, params=params, timeout=self.config.timeout)
            response.raise_for_status()

            result = response.json()
            if self.debug:
                print(
                    f"🔍 DEBUG: Report response: {json.dumps(result[:3] if isinstance(result, list) else result, indent=2)}..."
                )
                if isinstance(result, list):
                    print(f"🔍 DEBUG: Total aggregation keys: {len(result)}")

            return result

        except requests.exceptions.HTTPError as e:
            if self.debug:
                print(
                    f"DEBUG: API Error fetching report from {self.config.name}: {str(e)}"
                )
                try:
                    error_content = e.response.text
                    print(f"DEBUG: Response content: {error_content[:500]}...")
                except AttributeError:
                    pass
            return []
        except requests.exceptions.RequestException as e:
            if self.debug:
                print(
                    f"DEBUG: Network error fetching report from {self.config.name}: {str(e)}"
                )
            return []

    def fetch_unresolved_alerts(self, hours_back: int = 24) -> List[Alert]:
        """Fetch unresolved alerts from the last N hours"""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)

        # Step 1: Get alert report with aggregation keys
        report = self.fetch_alert_report(start_time, end_time)
        if not report:
            return []

        all_alerts = []

        # Step 2: Fetch alerts for each aggregation key
        for idx, report_item in enumerate(report):
            aggregation_key = report_item.get("aggregation_key", "")
            alert_count = report_item.get("alert_count", 0)
            if not aggregation_key:
                continue

            url = f"{self.config.base_url}/api/query/alerts"
            params = {
                "account_id": self.config.account_id,
                "start_ts": self._format_timestamp(start_time),
                "end_ts": self._format_timestamp(end_time),
                "alert_name": aggregation_key,
            }

            if self.debug:
                print(
                    f"🔍 DEBUG: Fetching alerts for '{aggregation_key}' ({alert_count} total)"
                )
                print(f"🔍 DEBUG: URL: {url}")
                print(f"🔍 DEBUG: Params: {json.dumps(params, indent=2)}")

            try:
                response = self.session.get(
                    url, params=params, timeout=self.config.timeout
                )
                response.raise_for_status()

                alerts_data = response.json()

                if self.debug:
                    print(
                        f"🔍 DEBUG: Response for '{aggregation_key}': {len(alerts_data)} alerts"
                    )
                    if alerts_data:
                        print(
                            f"🔍 DEBUG: First alert sample: {json.dumps(alerts_data[0], indent=2)}"
                        )
                        # Show priority distribution
                        priority_counts: Dict[str, int] = {}
                        unresolved_priority_counts: Dict[str, int] = {}
                        resolved_priority_counts: Dict[str, int] = {}
                        for ad in alerts_data:
                            p = ad.get("priority", "unknown")
                            priority_counts[p] = priority_counts.get(p, 0) + 1
                            if ad.get("resolved_at") is None:
                                unresolved_priority_counts[p] = (
                                    unresolved_priority_counts.get(p, 0) + 1
                                )
                            else:
                                resolved_priority_counts[p] = (
                                    resolved_priority_counts.get(p, 0) + 1
                                )
                        print(
                            f"🔍 DEBUG: Priority distribution (all): {priority_counts}"
                        )
                        print(
                            f"🔍 DEBUG: Priority distribution (unresolved): {unresolved_priority_counts}"
                        )
                        print(
                            f"🔍 DEBUG: Priority distribution (resolved): {resolved_priority_counts}"
                        )

                for alert_data in alerts_data:
                    # Only include unresolved alerts
                    if alert_data.get("resolved_at") is None:
                        # Add cluster info to each alert
                        alert_data["cluster"] = self.config.name

                        # Debug: Show raw priority data before processing
                        if self.debug:
                            print(
                                f"🔍 DEBUG: Processing unresolved alert '{alert_data.get('alert_name', 'unknown')}'"
                            )
                            print(
                                f"🔍 DEBUG: Raw priority field: {alert_data.get('priority', 'NOT FOUND')}"
                            )
                            # Check all possible priority fields
                            for field in [
                                "priority",
                                "severity",
                                "level",
                                "alert_severity",
                                "alertSeverity",
                            ]:
                                if field in alert_data:
                                    print(
                                        f"🔍 DEBUG: Found field '{field}' = {alert_data[field]}"
                                    )

                        # Check if priority field exists, if not try common alternatives
                        if "priority" not in alert_data:
                            # Try common field names for priority/severity
                            for field in [
                                "severity",
                                "level",
                                "alert_severity",
                                "alertSeverity",
                            ]:
                                if field in alert_data:
                                    alert_data["priority"] = alert_data[field]
                                    if self.debug:
                                        print(
                                            f"🔍 DEBUG: Using '{field}' as priority: {alert_data[field]}"
                                        )
                                    break
                            else:
                                # Default to LOW if no priority field found
                                alert_data["priority"] = "LOW"
                                if self.debug:
                                    print(
                                        "🔍 DEBUG: No priority field found, defaulting to LOW"
                                    )

                        # Normalize priority values to uppercase
                        if "priority" in alert_data and isinstance(
                            alert_data["priority"], str
                        ):
                            original_priority = alert_data["priority"]
                            alert_data["priority"] = alert_data["priority"].upper()
                            if (
                                self.debug
                                and original_priority != alert_data["priority"]
                            ):
                                print(
                                    f"🔍 DEBUG: Normalized priority from '{original_priority}' to '{alert_data['priority']}'"
                                )

                        try:
                            # Extract only known Alert fields to avoid TypeErrors
                            alert_fields = {
                                "alert_name": alert_data.get("alert_name"),
                                "title": alert_data.get("title"),
                                "description": alert_data.get("description"),
                                "source": alert_data.get("source"),
                                "priority": alert_data.get("priority"),
                                "started_at": alert_data.get("started_at"),
                                "resolved_at": alert_data.get("resolved_at"),
                                "cluster": alert_data.get("cluster"),
                                "namespace": alert_data.get("namespace"),
                                "app": alert_data.get("app"),
                                "kind": alert_data.get("kind"),
                                "resource_name": alert_data.get("resource_name"),
                                "resource_node": alert_data.get("resource_node"),
                            }
                            alert = Alert(**alert_fields)
                            if self.debug:
                                print(
                                    f"🔍 DEBUG: Alert created with final priority: {alert.priority}"
                                )
                            # Set the robusta URL if dashboard_url is configured
                            if self.config.dashboard_url:
                                from urllib.parse import quote

                                # Format: &events=["KubeHpaMaxedOut"]
                                # %5B is [ and %5D is ]
                                alert_name_encoded = quote(f'"{alert.alert_name}"')
                                url = f"{self.config.dashboard_url}/graphs"
                                url += "?dates=21600"
                                url += "&grouping=%22ALERT_NAME%22"
                                url += f"&events=%5B{alert_name_encoded}%5D"
                                setattr(alert, "_robusta_url", url)
                            all_alerts.append(alert)
                        except Exception as e:
                            if self.debug:
                                print(
                                    f"🔍 DEBUG: Failed to create alert. Data keys: {list(alert_data.keys())}"
                                )
                                print(f"🔍 DEBUG: Error: {str(e)}")
                            print(
                                f"Warning: Could not parse alert data for {aggregation_key}: {str(e)}"
                            )
                            continue

            except requests.exceptions.HTTPError as e:
                if self.debug:
                    print(f"DEBUG: Error fetching {aggregation_key} alerts: {str(e)}")
                    if hasattr(e, "response") and e.response:
                        try:
                            error_content = e.response.text
                            print(f"DEBUG: Response: {error_content[:200]}...")
                        except AttributeError:
                            pass
                continue
            except requests.exceptions.RequestException as e:
                if self.debug:
                    print(f"DEBUG: Network error for {aggregation_key}: {str(e)}")
                continue

        if self.debug:
            print(f"🔍 DEBUG: Total unresolved alerts found: {len(all_alerts)}")

        return all_alerts

    def _format_timestamp(self, dt: datetime) -> str:
        """Format datetime to Robusta API expected format with milliseconds"""
        # Format: 2024-09-02T04:02:05.032Z
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class SwiftBarRenderer:
    def __init__(self, display_config: DisplayConfig):
        self.config = display_config

    def _sanitize_for_menu(self, text: str) -> str:
        """Sanitize text for menu display by removing newlines and extra spaces"""
        if not text:
            return text
        # Replace newlines and carriage returns with spaces
        sanitized = text.replace("\n", " ").replace("\r", " ").strip()
        # Collapse multiple spaces into one
        return " ".join(sanitized.split())

    def render(self, cluster_alerts: Dict[str, List[Alert]]):
        """Render the SwiftBar output"""
        all_alerts = []
        for alerts in cluster_alerts.values():
            all_alerts.extend(alerts)

        # Render menu bar title
        self._render_menu_bar_title(all_alerts)

        print("---")

        self._render_footer()
        print("---")

        if not all_alerts:
            print("No unresolved alerts")
            return

        # Render alerts grouped by cluster, then by priority
        priority_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        cluster_names = sorted(cluster_alerts.keys())

        for idx, cluster_name in enumerate(cluster_names):
            alerts = cluster_alerts[cluster_name]
            if not alerts:
                continue

            # Add separator between clusters (but not before the first one)
            if idx > 0:
                print("---")

            # Cluster name
            print(f"{cluster_name}")

            # Group alerts by priority for this cluster
            alerts_by_priority = defaultdict(list)
            for alert in alerts:
                alerts_by_priority[alert.priority].append(alert)

            # Render each priority level for this cluster
            for priority in priority_order:
                if priority in alerts_by_priority:
                    priority_alerts = alerts_by_priority[priority]
                    color = COLORS.get(priority, COLORS["unknown"])
                    symbol = SYMBOLS.get(priority, SYMBOLS["unknown"])
                    print(
                        f"{symbol} {priority} ({len(priority_alerts)}) | color={color}"
                    )
                    self._render_priority_submenu(priority_alerts)

    def _render_menu_bar_title(self, alerts: List[Alert]):
        """Render the menu bar title with alert count and highest priority"""
        if not alerts:
            print(":bell:")
            return

        # Count alerts by priority
        priority_counts: Dict[str, int] = {}
        for alert in alerts:
            priority = alert.priority
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        # Build title with priority breakdown
        # Priority labels: CRITICAL->C, HIGH->H, MEDIUM->M, LOW->L, INFO->I
        priority_labels = {
            "CRITICAL": "C",
            "HIGH": "H",
            "MEDIUM": "M",
            "LOW": "L",
            "INFO": "I",
        }

        # Build parts in priority order
        priority_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        title_parts = []

        for priority in priority_order:
            if priority in priority_counts and priority_counts[priority] > 0:
                label = priority_labels.get(priority, priority[0])
                title_parts.append(f"{label}:{priority_counts[priority]}")

        # Determine icon based on highest priority
        if "CRITICAL" in priority_counts and priority_counts["CRITICAL"] > 0:
            icon = ":exclamationmark.octagon.fill:"
        elif "HIGH" in priority_counts and priority_counts["HIGH"] > 0:
            icon = ":exclamationmark.triangle.fill:"
        else:
            icon = ":bell.badge:"

        # Print title with icon and priority breakdown
        title = " ".join(title_parts)
        print(f"{icon} {title}")

    def _render_priority_submenu(self, alerts: List[Alert]):
        """Render alerts as submenu items"""
        # Sort alerts by name only (already grouped by cluster)
        alerts.sort(key=lambda a: a.alert_name)

        # Show all alerts as submenu items
        for alert in alerts:
            self._render_alert_item(alert)

    def _render_alert_item(self, alert: Alert):
        """Render a single alert as a submenu item"""
        # Build alert title
        parts = [self._sanitize_for_menu(alert.alert_name)]

        if self.config.show_namespace:
            parts.append(
                f"{self._sanitize_for_menu(str(alert.namespace))}/{self._sanitize_for_menu(alert.resource_name)}"
            )
        else:
            parts.append(self._sanitize_for_menu(alert.resource_name))

        if self.config.show_age:
            parts.append(f"({alert.age})")

        # Main alert item
        print(f"-- {' '.join(parts)}")

        # Add submenu details
        if alert.description:
            # Split description by sentences and display each on a new line
            description = self._sanitize_for_menu(alert.description)
            # Split by common sentence endings
            sentences = re.split(r"(?<=[.!?])\s+", description)
            for sentence in sentences:
                if sentence.strip():
                    # Make the description clickable if we have a Robusta URL
                    if alert.robusta_url:
                        print(f"---- {sentence.strip()} | href={alert.robusta_url}")
                    else:
                        print(f"---- {sentence.strip()}")
        print(f"---- Cluster: {self._sanitize_for_menu(alert.cluster)} | color=#898989")
        print(
            f"---- Namespace: {self._sanitize_for_menu(str(alert.namespace))} | color=#898989"
        )
        print(f"---- App: {self._sanitize_for_menu(alert.app)} | color=#898989")
        print(
            f"---- Resource: {self._sanitize_for_menu(alert.resource_name)} | color=#898989"
        )
        print(
            f"---- Node: {self._sanitize_for_menu(str(alert.resource_node))} | color=#898989"
        )
        print(f"---- Started: {alert.started_at} | color=#898989")

        # Create alert details for copying
        alert_details_parts = []
        if alert.description:
            alert_details_parts.append(f"Description: {alert.description}")
        alert_details_parts.extend(
            [
                f"Alert: {alert.alert_name}",
                f"Cluster: {alert.cluster}",
                f"Namespace: {alert.namespace}",
                f"App: {alert.app}",
                f"Resource: {alert.resource_name}",
                f"Node: {alert.resource_node}",
                f"Priority: {alert.priority}",
                f"Started: {alert.started_at}",
            ]
        )

        # Join with newlines and encode to base64 to avoid shell escaping issues
        alert_text = "\n".join(alert_details_parts)
        encoded_text = base64.b64encode(alert_text.encode()).decode()

        # Add copy to clipboard option - use base64 to avoid any escaping issues
        print(
            f'---- Copy Alert Details | bash="echo {encoded_text} | base64 -d | pbcopy" terminal=false'
        )

    def _render_alert_line(self, alert: Alert, indent: str = ""):
        """Render a single alert line"""
        symbol = alert.priority_symbol

        # Build alert line
        parts = [symbol, alert.alert_name]

        # Always show cluster for grouped view
        parts.append(f"[{alert.cluster}]")

        if self.config.show_namespace:
            parts.append(f"{alert.namespace}/{alert.resource_name}")
        else:
            parts.append(alert.resource_name)

        if self.config.show_age:
            parts.append(f"({alert.age})")

        color = f"color={alert.priority_color}"
        line = f"{indent}{' '.join(parts)} | {color}"
        print(line)

        # Add submenu with details
        if alert.description:
            print(f"{indent}-- {alert.description} | color=#898989")
        print(f"{indent}-- Cluster: {alert.cluster} | color=#898989")
        print(f"{indent}-- App: {alert.app} | color=#898989")
        print(f"{indent}-- Node: {alert.resource_node} | color=#898989")
        print(f"{indent}-- Started: {alert.started_at} | color=#898989")

    def _render_footer(self):
        """Render footer with refresh option"""
        print("Refresh data | refresh=true")
        print(
            "Open config | href=file://"
            + str(Path("~/.config/swiftbar/robusta.yml").expanduser())
        )


def get_state_file_path() -> Path:
    """Get the path to the state file"""
    return Path("~/.config/swiftbar/robusta.state").expanduser()


def load_state() -> Dict[str, Any]:
    """Load the previous state from file"""
    state_file = get_state_file_path()
    if state_file.exists():
        try:
            with open(state_file, "rb") as f:
                return pickle.load(f)
        except Exception:
            # If state file is corrupted, start fresh
            return {}
    return {}


def save_state(alerts: List[Alert]):
    """Save current alerts to state file"""
    state_file = get_state_file_path()
    state_file.parent.mkdir(parents=True, exist_ok=True)

    # Store alerts as a dict keyed by unique ID
    state = {
        "alerts": {alert.get_unique_id(): asdict(alert) for alert in alerts},
        "last_update": datetime.now(timezone.utc).isoformat(),
    }

    with open(state_file, "wb") as f:
        pickle.dump(state, f)


def send_notification(title: str, message: str, sound: bool = True):
    """Send a macOS notification"""
    # Escape quotes in title and message
    title = title.replace('"', '\\"').replace("'", "\\'")
    message = message.replace('"', '\\"').replace("'", "\\'")

    script = f'''display notification "{message}" with title "{title}"'''
    if sound:
        script += ' sound name "Glass"'

    subprocess.run(["osascript", "-e", script], capture_output=True)


def detect_changes(
    current_alerts: List[Alert], previous_state: Dict[str, Any]
) -> Tuple[List[Alert], List[Dict[str, Any]]]:
    """Detect new and resolved alerts"""
    previous_alerts = previous_state.get("alerts", {})

    current_ids = {alert.get_unique_id(): alert for alert in current_alerts}
    previous_ids = set(previous_alerts.keys())

    # Find new alerts
    new_alert_ids = set(current_ids.keys()) - previous_ids
    new_alerts = [current_ids[alert_id] for alert_id in new_alert_ids]

    # Find resolved alerts
    resolved_alert_ids = previous_ids - set(current_ids.keys())
    resolved_alerts = [previous_alerts[alert_id] for alert_id in resolved_alert_ids]

    return new_alerts, resolved_alerts


def load_config() -> tuple[List[ClusterConfig], DisplayConfig]:
    """Load configuration from YAML file"""
    config_path = Path(
        os.environ.get("VAR_CONFIG_PATH", "~/.config/swiftbar/robusta.yml")
    ).expanduser()

    default_config: Dict[str, Any] = {
        "clusters": [],
        "display": {
            "show_cluster_in_title": True,
            "show_age": True,
            "show_namespace": True,
            "stale_alert_hours": 24,
            "refresh_interval_minutes": 5,
            "debug": False,
        },
    }

    if not config_path.exists():
        # Create default config file
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(
                {
                    "clusters": [
                        {
                            "name": "prod-cluster-1",
                            "account_id": "YOUR_ACCOUNT_ID_1",
                            "api_key": "YOUR_API_KEY_1",
                            "base_url": "https://api.robusta.dev",
                            "timeout": 10,
                        },
                        {
                            "name": "staging-cluster",
                            "account_id": "YOUR_ACCOUNT_ID_2",
                            "api_key": "YOUR_API_KEY_2",
                            "base_url": "https://api.robusta.dev",
                            "timeout": 10,
                        },
                    ],
                    "display": default_config["display"],
                },
                f,
                default_flow_style=False,
            )

        print(":gear.badge.exclamationmark:")
        print("---")
        print(f"Created default config at {config_path}")
        print("Please edit with your API credentials")
        sys.exit(1)

    try:
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f) or {}

        # Merge with defaults
        for key, value in default_config.items():
            if key not in config_data:
                config_data[key] = value
        
        # Merge display config
        display_config = config_data.get("display", {})
        config_data["display"] = default_config["display"].copy()
        config_data["display"].update(display_config)

        clusters = [ClusterConfig(**cluster) for cluster in config_data["clusters"]]
        display = DisplayConfig(**config_data["display"])

        return clusters, display

    except yaml.YAMLError as e:
        print(":gear.badge.exclamationmark:")
        print("---")
        print(f"Invalid YAML in {config_path}: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(":gear.badge.exclamationmark:")
        print("---")
        print(f"Failed to load config: {str(e)}")
        sys.exit(1)


def main():
    """Main execution function"""
    try:
        clusters_config, display_config = load_config()

        if not clusters_config:
            print(":bell.slash:")
            print("---")
            print("No clusters configured")
            return

        cluster_alerts = {}
        all_current_alerts = []

        # Fetch alerts from all clusters
        for cluster_config in clusters_config:
            api = RobustaAPI(cluster_config, debug=display_config.debug)
            alerts = api.fetch_unresolved_alerts(
                hours_back=display_config.stale_alert_hours
            )
            cluster_alerts[cluster_config.name] = alerts
            all_current_alerts.extend(alerts)

        # Load previous state and detect changes
        previous_state = load_state()
        new_alerts, resolved_alerts = detect_changes(all_current_alerts, previous_state)

        # Send notifications for changes
        if new_alerts:
            # Group new alerts by priority
            new_by_priority = defaultdict(list)
            for alert in new_alerts:
                new_by_priority[alert.priority].append(alert)

            # Build notification message
            priority_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
            message_parts = []
            for priority in priority_order:
                if priority in new_by_priority:
                    count = len(new_by_priority[priority])
                    message_parts.append(f"{count} {priority}")

            message = "New alerts: " + ", ".join(message_parts)

            # Add details of critical/high alerts
            critical_high = new_by_priority.get("CRITICAL", []) + new_by_priority.get(
                "HIGH", []
            )
            if critical_high:
                alert_names = [
                    f"{a.alert_name} ({a.cluster})" for a in critical_high[:3]
                ]  # Show up to 3
                if len(critical_high) > 3:
                    alert_names.append(f"and {len(critical_high) - 3} more...")
                message += "\n" + "\n".join(alert_names)

            send_notification("Robusta Alert", message, sound=True)

        if resolved_alerts:
            # Count resolved alerts by priority
            resolved_by_priority = defaultdict(int)
            for alert_data in resolved_alerts:
                priority = alert_data.get("priority", "unknown")
                resolved_by_priority[priority] += 1

            # Build notification message
            message_parts = []
            for priority, count in resolved_by_priority.items():
                if count > 0:
                    message_parts.append(f"{count} {priority}")

            message = "Resolved: " + ", ".join(message_parts)
            send_notification("Robusta Alert Resolved", message, sound=False)

        # Save current state
        save_state(all_current_alerts)

        # Render output
        renderer = SwiftBarRenderer(display_config)
        renderer.render(cluster_alerts)

    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(":exclamationmark.triangle:")
        print("---")
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
