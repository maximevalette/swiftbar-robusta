# SwiftBar Robusta Plugin

A [SwiftBar](https://github.com/swiftbarapp/SwiftBar) plugin for monitoring unresolved [Robusta](https://robusta.dev) alerts across multiple Kubernetes clusters directly from your macOS menu bar.

![SwiftBar Robusta Plugin Screenshot](https://github.com/user-attachments/assets/screenshot-placeholder.png)

## Features

- 🔔 Real-time monitoring of unresolved Kubernetes alerts
- 🎯 Priority-based alert grouping (Critical, High, Medium, Low, Info)
- 🏢 Multi-cluster support
- 📊 Alert count in menu bar with visual indicators
- ⏱️ Alert age tracking
- 🔗 Direct links to Robusta dashboard
- 📋 Copy alert details to clipboard
- 🔔 macOS notifications for new and resolved alerts
- 🔄 Configurable refresh intervals

## Prerequisites

- macOS
- [SwiftBar](https://github.com/swiftbarapp/SwiftBar) installed
- [uv](https://github.com/astral-sh/uv) Python package manager
- Robusta account with API access

## Installation

### 1. Install SwiftBar

```bash
brew install --cask swiftbar
```

### 2. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Install the Plugin

1. Clone this repository or download the `robusta.5m.py` file
2. Copy the plugin to your SwiftBar plugins directory:

```bash
# Default SwiftBar plugin directory
cp robusta.5m.py ~/Library/Application\ Support/SwiftBar/Plugins/

# Make it executable
chmod +x ~/Library/Application\ Support/SwiftBar/Plugins/robusta.5m.py
```

3. The plugin will automatically create a default configuration file on first run at `~/.config/swiftbar/robusta.yml`

### 4. Configure Your Clusters

Edit `~/.config/swiftbar/robusta.yml` with your Robusta API credentials:

```yaml
clusters:
  - name: prod-cluster-1
    account_id: YOUR_ACCOUNT_ID_1
    api_key: YOUR_API_KEY_1
    base_url: https://api.robusta.dev
    timeout: 30
    dashboard_url: https://platform.robusta.dev  # Optional: for direct alert links
    
  - name: staging-cluster
    account_id: YOUR_ACCOUNT_ID_2
    api_key: YOUR_API_KEY_2
    base_url: https://api.robusta.dev
    timeout: 30

display:
  show_cluster_in_title: true
  show_age: true
  show_namespace: true
  stale_alert_hours: 24
  refresh_interval_minutes: 5
  debug: false
```

### 5. Refresh SwiftBar

Click on the SwiftBar icon and select "Refresh All" or restart SwiftBar.

## Getting Robusta API Credentials

1. Log in to your [Robusta platform](https://platform.robusta.dev)
2. Navigate to Settings → API Keys
3. Create a new API key with read permissions
4. Copy the Account ID and API Key to your configuration

## Configuration Options

### Cluster Configuration

- `name`: Display name for the cluster
- `account_id`: Your Robusta account ID
- `api_key`: API key for authentication
- `base_url`: Robusta API endpoint (default: https://api.robusta.dev)
- `timeout`: API request timeout in seconds
- `dashboard_url`: Optional URL to your Robusta dashboard for direct alert links

### Display Configuration

- `show_cluster_in_title`: Show cluster name in menu bar title
- `show_age`: Display alert age
- `show_namespace`: Show Kubernetes namespace
- `stale_alert_hours`: Hours to look back for alerts (default: 24)
- `refresh_interval_minutes`: How often to refresh data (filename controls this)
- `debug`: Enable debug output for troubleshooting

## Customizing Refresh Interval

The refresh interval is controlled by the filename. The `5m` in `robusta.5m.py` means refresh every 5 minutes. You can change this to:

- `robusta.30s.py` - Every 30 seconds
- `robusta.1m.py` - Every minute
- `robusta.10m.py` - Every 10 minutes
- `robusta.1h.py` - Every hour

Simply rename the file and refresh SwiftBar.

## Menu Bar Icons

The plugin uses different icons based on the highest priority alert:

- 🛑 Red octagon: Critical alerts present
- ⚠️ Yellow triangle: High priority alerts (no critical)
- 🔔 Bell with badge: Medium/Low/Info alerts only
- 🔔 Bell: No alerts

## Troubleshooting

### Enable Debug Mode

Set `debug: true` in your configuration file to see detailed API calls and responses.

### Check Logs

SwiftBar logs can be found in Console.app under the SwiftBar process.

### Common Issues

1. **"Created default config" message**: Edit the configuration file with your API credentials
2. **No alerts showing**: Verify your API credentials and that you have unresolved alerts in Robusta
3. **Connection errors**: Check your internet connection and API endpoint URL
4. **Permission denied**: Ensure the plugin file is executable (`chmod +x`)

## Development

### Running Tests

```bash
# Install test dependencies
uv pip install pytest pytest-mock

# Run tests
uv run pytest tests/
```

### Project Structure

```
swiftbar-robusta/
├── robusta.5m.py          # Main plugin script
├── README.md              # This file
├── LICENSE                # MIT License
├── example-config.yml     # Example configuration
├── tests/                 # Unit tests
│   └── test_robusta.py
├── .github/               # GitHub Actions workflows
│   └── workflows/
│       └── ci.yml
└── .gitignore
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [SwiftBar](https://github.com/swiftbarapp/SwiftBar) for the excellent macOS menu bar utility
- [Robusta](https://robusta.dev) for Kubernetes monitoring and alerting
- [uv](https://github.com/astral-sh/uv) for fast Python package management

## Support

- For plugin issues: [Open an issue](https://github.com/yourusername/swiftbar-robusta/issues)
- For SwiftBar issues: [SwiftBar GitHub](https://github.com/swiftbarapp/SwiftBar)
- For Robusta issues: [Robusta Documentation](https://docs.robusta.dev)