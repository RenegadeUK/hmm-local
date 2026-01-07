# Home Miner Manager v1.0.0

🎉 **Production Release** - Modern, Dockerized ASIC miner management platform with energy-based automation and Octopus Agile pricing integration.

![Docker](https://img.shields.io/badge/Docker-20.10+-2496ED?logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)
![WCAG](https://img.shields.io/badge/WCAG-AA-green)
![PWA](https://img.shields.io/badge/PWA-Ready-5A0FC8?logo=pwa&logoColor=white)

---

**Manage your Bitcoin miners with intelligence:**
- 📊 Real-time monitoring with health scoring
- ⚡ Automatic energy optimization with Octopus Agile
- 🏥 Pool health monitoring with smart failover
- 🎨 Customizable dashboards with drag-and-drop
- 🔔 Smart notifications (Telegram, Discord)
- 🌓 Dark/light theme with WCAG AA compliance

---

## Table of Contents

- [Supported Miners](#supported-miners)
- [Features](#features)
- [Quick Start](#quick-start)
- [Getting Started Guide](#getting-started-guide)
- [System Requirements](#system-requirements)
- [Configuration](#configuration)
- [Security Best Practices](#security-best-practices)
- [Architecture](#architecture)
- [API Documentation](#api-documentation)
- [Miner-Specific Notes](#miner-specific-notes)
- [Network Auto-Discovery](#network-auto-discovery)
- [Notifications Setup](#notifications-setup)
- [Custom Dashboards](#custom-dashboards)
- [Hardware Predictions](#hardware-predictions)
- [Overclocking Profiles](#overclocking-profiles)
- [Bulk Operations](#bulk-operations)
- [Themes & Accessibility](#themes--accessibility)
- [Automation Examples](#automation-examples)
- [Pool Strategies](#pool-strategies)
- [Octopus Agile Integration](#octopus-agile-integration)
- [Audit Logs](#audit-logs)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Frequently Asked Questions](#frequently-asked-questions)
- [License](#license)
- [Contributing](#contributing)
- [Support](#support)

## Supported Miners

- **Avalon Nano 3 / 3S** - cgminer TCP API (port 4028)
- **Bitaxe 601** - REST API
- **NerdQaxe++** - REST API
- **NMMiner ESP32** - UDP telemetry + config (lottery miner)
- **XMRig** - HTTP API (CPU mining) - See [XMRig Setup Guide](docs/XMRIG_SETUP.md)

## Features

### Core Features
- 📊 **Real-time Telemetry** - Monitor hashrate, temperature, power consumption, and shares
- 🌊 **Pool Management** - Configure and switch between mining pools with health monitoring
- ⚡ **Smart Automation** - Rule-based automation with triggers and actions
- 💡 **Octopus Agile Pricing** - Automatic energy price tracking (no API key required)
- 🎨 **Modern UI** - Clean v0-inspired design with sidebar navigation and dark/light themes
- 🔔 **Notifications** - Telegram Bot API and Discord Webhook support with configurable alerts

### Advanced Analytics
- 📈 **Health Scoring** - Miner health based on uptime, temperature, reject rate, and hashrate stability
- 📊 **Comparative Analytics** - Time-series charts with day/week/month views
- 📉 **Historical Tracking** - Performance trends and analysis with CSV export
- ⚡ **Energy Consumption** - Total kWh calculation with per-miner breakdowns
- 🎯 **ROI Calculator** - Real-time profitability (coin value - energy cost)
- 🔮 **Hardware Predictions** - AI-powered anomaly detection for temperature, hashrate, and reject rates

### Intelligent Pool Management
- 🏥 **Health Monitoring** - Connectivity checks every 5min with response time and reject rate tracking
- 🔄 **Automatic Failover** - Smart pool switching on high reject rate, offline pools, or low health scores
- 📊 **Performance Comparison** - Luck %, latency trends, and reject rates over time (24h/3d/7d/30d)
- 🎯 **Multi-Pool Strategies** - Round-robin rotation and load balancing by health/latency/reject rate
- ⚖️ **Priority Weighting** - Assign pool priorities for intelligent load distribution

### Energy Optimization
- 🔋 **Smart Scheduling** - Auto-adjust modes based on Agile pricing thresholds
- 💰 **Price Forecasting** - 24-hour ahead predictions with visualization
- ⚡ **Auto-Optimization** - Automatic mode switching when electricity is cheap/expensive
- 📉 **Cost Analysis** - Break-even projections and profitability tracking

### Hardware Management
- 🔍 **Network Auto-Discovery** - Scan for Avalon Nano, Bitaxe, and NerdQaxe devices
- 🕐 **Scheduled Scanning** - Configurable auto-discovery intervals (1-168 hours)
- 🔧 **Overclocking Profiles** - Save/load/apply custom tuning presets (frequency, voltage, mode)
- 🎛️ **Bulk Operations** - Enable/disable, set mode, switch pool, restart, apply profiles to multiple miners
- 📦 **Firmware Tracking** - Display firmware versions from telemetry

### UI/UX Enhancements
- 🌓 **Dark/Light Theme** - Toggle with user preferences and localStorage persistence
- 📱 **Progressive Web App** - Installable on mobile/desktop with offline support
- ♿ **WCAG AA Compliant** - All text meets 4.5:1 minimum contrast ratios
- 🔍 **FAQ Search** - Real-time filtering with text highlighting
- 📄 **Paginated Logs** - 50 events per page with filter tiles (All/Info/Success/Warning/Error)
- 🎨 **Custom Dashboards** - Create multiple dashboards with drag-and-drop widget builder (12 widget types)
- 📊 **Real-time Widgets** - Live hashrate, temperature, power, reject rate, and more

### Advanced Features
- 📝 **Audit Logging** - Track all configuration changes with filtering and search
-  **Developer Mode** - Mock miners and simulation mode for testing without hardware

## Quick Start

### Using Docker Compose (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd home_miner_manager
```

2. Copy environment file:
```bash
cp .env.example .env
```

3. Start the container:
```bash
docker-compose up -d
```

4. Access the web interface:
```
http://localhost:8080
```

## Getting Started Guide

After installation, follow these steps to set up your mining operation:

### 1. Add Your First Miner

**Option A: Auto-Discovery (Recommended)**
- Go to **Settings → Discovery**
- Add your local network range (e.g., `192.168.1.0/24`)
- Click "Scan Network"
- Found miners will appear in the results
- Enable "Auto-add discovered miners" for automatic addition

**Option B: Manual Addition**
- Go to **Miners → Add Miner**
- Enter miner name, type, and IP address
- Click "Save"

### 2. Configure Mining Pools

- Go to **Pools → Add Pool**
- Enter pool details:
  - Name (e.g., "Public Pool")
  - URL (e.g., `stratum+tcp://pool.example.com`)
  - Port (e.g., `3333`)
  - Wallet address
  - Password (usually `x`)
- Click "Save"
- Assign pools to miners in **Miners** list

### 3. Set Up Energy Pricing (Optional but Recommended)

- Go to **Energy → Pricing**
- Select your Octopus Agile region (A-P for UK)
- Prices will automatically sync every 30 minutes
- View current and upcoming prices

### 4. Enable Energy Optimization (Optional)

- Go to **Energy → Optimization**
- Set price threshold (e.g., 15 p/kWh)
- Enable "Auto-Optimization"
- System will automatically adjust miner modes based on electricity prices

### 5. Configure Notifications (Optional)

- Go to **Notifications**
- Set up Telegram Bot or Discord Webhook
- Configure alert thresholds:
  - Miner offline (e.g., 10 minutes)
  - High temperature (e.g., 85°C)
  - High reject rate (e.g., 5%)
- Test notifications before enabling

### 6. Create Custom Dashboard (Optional)

- Go to **Dashboards**
- Click "Create New Dashboard"
- Name it (e.g., "Main Overview")
- Add widgets by dragging from sidebar
- Arrange and resize as desired
- Click "Save Layout"

### Manual Docker Build

```bash
docker build -t v0-miner-controller .
docker run -d \
  -p 8080:8080 \
  -v ./config:/config \
  -e WEB_PORT=8080 \
  -e TZ=UTC \
  --name miner-controller \
  v0-miner-controller
```

## System Requirements

### Minimum Requirements
- **CPU:** 1 core (x86_64 or ARM64)
- **RAM:** 512 MB
- **Storage:** 1 GB for application + logs
- **OS:** Linux, macOS, Windows (with Docker)
- **Docker:** Version 20.10+ with Docker Compose

### Recommended Requirements
- **CPU:** 2+ cores for better performance
- **RAM:** 1 GB (allows more telemetry history)
- **Storage:** 5 GB (for extensive logs and analytics)
- **Network:** Gigabit Ethernet for fast miner discovery

### Supported Architectures
- `linux/amd64` (Intel/AMD 64-bit)
- `linux/arm64` (Raspberry Pi 4, Apple Silicon)
- `linux/arm/v7` (Raspberry Pi 3)

### Performance Notes
- Handles 50+ miners with minimal resource usage
- Telemetry polling every 60 seconds per miner
- Database auto-cleanup keeps size under 100 MB

## Configuration

All configuration is stored in the `/config` volume:

```
/config
├── config.yaml      # Main configuration file
├── data.db          # SQLite database
└── logs/           # Application logs
```

### Environment Variables

- `WEB_PORT` - Web interface port (default: 8080)
- `TZ` - Timezone (default: UTC)
- `PUID` - User ID for file permissions (default: 1000)
- `PGID` - Group ID for file permissions (default: 1000)

## Security Best Practices

### Network Security
- Run on isolated VLAN or network segment with miners
- Use firewall rules to restrict access to web interface (port 8080)
- Consider using reverse proxy (nginx/Traefik) with HTTPS/SSL

### Access Control
- Do not expose directly to internet without authentication
- Use VPN (WireGuard/OpenVPN) for remote access
- Change default ports if exposed to untrusted networks
- Consider adding HTTP Basic Auth via reverse proxy

### Data Protection
- `/config` volume contains sensitive data (wallet addresses, API keys)
- Ensure proper file permissions (PUID/PGID)
- Regular backups of `/config` directory recommended
- Keep Docker images updated for security patches

### Future Security Features
- Multi-user support with role-based access control (RBAC)
- Two-factor authentication (2FA) for admin access
- API key authentication for REST endpoints
- Encrypted database storage

## Architecture

```
/app
├── main.py              # FastAPI application entry point
├── core/               # Core services
│   ├── config.py       # Configuration management
│   ├── database.py     # SQLite models and session
│   └── scheduler.py    # APScheduler for periodic tasks
├── adapters/           # Miner adapters
│   ├── base.py         # Base adapter interface
│   ├── avalon_nano.py  # Avalon Nano 3/3S
│   ├── bitaxe.py       # Bitaxe 601
│   ├── nerdqaxe.py     # NerdQaxe++
│   └── nmminer.py      # NMMiner ESP32
├── api/                # REST API endpoints
│   ├── miners.py       # Miner management
│   ├── pools.py        # Pool management
│   ├── automation.py   # Automation rules
│   └── dashboard.py    # Dashboard stats
└── ui/                 # Web interface
    ├── routes.py       # Jinja2 template routes
    ├── templates/      # HTML templates
    └── static/         # CSS/JS assets
```

## API Documentation

Once running, visit:
- API Docs: `http://localhost:8080/docs`
- Health Check: `http://localhost:8080/health`

### Key Endpoints

**Miners:**
- `GET /api/miners/` - List all miners
- `POST /api/miners/` - Add new miner
- `GET /api/miners/{id}/telemetry` - Get current telemetry
- `POST /api/miners/{id}/mode` - Set operating mode
- `POST /api/miners/{id}/restart` - Restart miner
- `GET /api/analytics/miner/{id}` - Get per-miner analytics with time ranges

**Pools:**
- `GET /api/pools/` - List all pools with health scores
- `POST /api/pools/` - Add new pool
- `GET /api/pool_health/` - Get pool health metrics
- `POST /api/pool_health/trigger_failover` - Manually trigger pool failover
- `GET /api/pool_health/performance` - Get pool performance comparison
- `GET /api/strategy_pools/` - List multi-pool strategies
- `POST /api/strategy_pools/execute/{id}` - Execute a pool strategy

**Automation:**
- `GET /api/automation/` - List all rules
- `POST /api/automation/` - Create new rule
- `PUT /api/automation/{id}` - Update existing rule
- `DELETE /api/automation/{id}` - Delete rule

**Dashboard:**
- `GET /api/dashboard/stats` - Overall statistics with health scores
- `GET /api/dashboard/energy/current` - Current energy price
- `GET /api/dashboard/energy/timeline` - Price timeline with forecasts
- `GET /api/widgets/data` - Real-time widget data
- `GET /api/dashboards/` - List custom dashboards
- `POST /api/dashboards/` - Create custom dashboard

**Discovery:**
- `GET /api/discovery/networks` - List configured network ranges
- `POST /api/discovery/scan` - Trigger network scan
- `GET /api/discovery/settings` - Get auto-discovery settings

**Bulk Operations:**
- `POST /api/bulk/enable` - Enable multiple miners
- `POST /api/bulk/disable` - Disable multiple miners
- `POST /api/bulk/set_mode` - Set mode for multiple miners
- `POST /api/bulk/switch_pool` - Switch pool for multiple miners
- `POST /api/bulk/restart` - Restart multiple miners
- `POST /api/bulk/apply_profile` - Apply tuning profile to multiple miners

**Notifications:**
- `GET /api/notifications/config` - Get notification configuration
- `POST /api/notifications/config` - Update notification settings
- `POST /api/notifications/test` - Test notification channels
- `GET /api/notifications/alerts` - List configured alerts

**Audit:**
- `GET /api/audit/` - Get audit logs with filtering

## Miner-Specific Notes

### Avalon Nano 3 / 3S
- Uses cgminer TCP API on port 4028
- Power calculation: `watts = raw_power_code / (millivolts / 1000)`
- Modes: `low`, `med`, `high`
- Mode detection via WORKMODE field in estats MM ID string

### Bitaxe 601 / NerdQaxe++
- REST API with native power/frequency/temperature
- Modes: `eco`, `standard`, `turbo`, `oc`
- Supports overclocking profiles with custom frequency/voltage

### NMMiner ESP32
- **Telemetry only** via UDP broadcast (port 12345)
- Config via UDP (port 12347)
- No power metrics or tuning available
- Pool control only (IP "0.0.0.0" = broadcast to all)
- Limited automation support (pool switching only)

### XMRig (CPU Mining)
- HTTP API for telemetry and control
- Supports pool switching and hashrate monitoring
- Temperature and power metrics from system
- See [XMRig Setup Guide](docs/XMRIG_SETUP.md) for configuration details
- Compatible with Monero (XMR) mining pools

## Octopus Agile Integration

The platform includes comprehensive UK energy pricing support:

1. **Setup Pricing:**
   - Go to **Energy → Pricing** page
   - Select your region (A-P)
   - System automatically fetches half-hourly prices from Octopus API
   - No API key required - uses public tariff data

2. **Energy Optimization:**
   - Navigate to **Energy → Optimization**
   - View 24-hour price forecast with color-coded visualization
   - Set price threshold for auto-optimization
   - Enable auto-optimization to automatically adjust miner modes
   - View real-time ROI calculator (coin value - energy cost)

3. **Price-Based Automation:**
   - Create automation rules based on price thresholds
   - Automatically switch to eco mode when prices are high
   - Switch to turbo mode during cheap periods
   - Prevent conflicts with existing automation rules

## Network Auto-Discovery

Automatically discover miners on your network:

1. **Configure Networks:**
   - Go to **Settings → Discovery**
   - Add network ranges using CIDR notation (e.g., `192.168.1.0/24`)
   - Auto-detection suggests your local network

2. **Scan for Miners:**
   - Click "Scan Network" to discover Avalon Nano (port 4028), Bitaxe, and NerdQaxe devices
   - Enable "Auto-add discovered miners" to automatically add them
   - Set scan interval for scheduled auto-discovery (1-168 hours)

3. **Supported Protocols:**
   - **Avalon Nano:** cgminer API on port 4028
   - **Bitaxe/NerdQaxe:** HTTP API on ports 80, 8080, 4000

## Notifications Setup

Configure alerts for critical miner events:

1. **Telegram Bot:**
   - Create a bot via [@BotFather](https://t.me/botfather)
   - Get bot token and chat ID
   - Add to **Notifications** page

2. **Discord Webhook:**
   - Create webhook in Discord server settings
   - Copy webhook URL
   - Add to **Notifications** page

3. **Alert Types:**
   - Miner Offline (duration threshold)
   - High Temperature (per miner type)
   - High Reject Rate (percentage)
   - Pool Failure (offline/unreachable)
   - Low Hashrate (percentage drop)

4. **Alert Configuration:**
   - Set thresholds for each alert type
   - Choose notification channels
   - Enable/disable individual alerts
   - Test notifications before saving

## Custom Dashboards

Create personalized dashboards with drag-and-drop widgets:

1. **Create Dashboard:**
   - Go to **Dashboards** page
   - Click "Create New Dashboard"
   - Name your dashboard (e.g., "Overview", "Power Monitoring")

2. **Add Widgets:**
   - Click "Edit Layout" to enter design mode
   - Choose from 12 widget types:
     - Total Hashrate, Avg Temperature, Total Power
     - Online Miners Count, Active Pools, Automation Rules
     - Current Energy Price, Hourly Energy Cost
     - Total Shares, Avg Reject Rate, Uptime, Health Score
   - Drag widgets to arrange layout
   - Resize widgets by dragging corners

3. **Real-Time Updates:**
   - All widgets update automatically every 5 seconds
   - No page refresh required
   - Click dashboard name to view

## Hardware Predictions

AI-powered anomaly detection warns you before problems occur:

1. **View Predictions:**
   - Go to **Miners → [Miner Name] → Analytics**
   - Scroll to "Hardware Health Predictions"

2. **Prediction Types:**
   - **Temperature Issues:** Warns if temperature trending upward
   - **Hashrate Decline:** Detects gradual hashrate degradation
   - **Power Anomalies:** Identifies unusual power consumption patterns
   - **Reject Rate Problems:** Predicts increasing reject rates
   - **Disconnection Patterns:** Warns of unstable connectivity

3. **How It Works:**
   - Analyzes last 48 hours of telemetry data
   - Uses statistical thresholds and trend analysis
   - Provides severity scores (low/medium/high)
   - Offers actionable recommendations

## Overclocking Profiles

Save and apply custom tuning configurations:

1. **Create Profile:**
   - Go to **Settings → Tuning**
   - Configure frequency, voltage, and mode for each miner type
   - Save with a descriptive name (e.g., "Winter Turbo", "Summer Eco")

2. **Apply Profile:**
   - Select miners from list
   - Choose profile from dropdown
   - Click "Apply to Selected" for bulk application

3. **Supported Settings:**
   - **Avalon Nano:** Mode (low/med/high)
   - **Bitaxe/NerdQaxe:** Frequency (MHz), Voltage (mV), Mode (eco/standard/turbo/oc)

## Bulk Operations

Manage multiple miners simultaneously:

1. **Available Operations:**
   - Enable/Disable miners
   - Set operating mode
   - Switch mining pool
   - Restart miners
   - Apply tuning profile

2. **How to Use:**
   - Go to **Miners** page
   - Select checkboxes for target miners
   - Choose operation from "Bulk Actions" dropdown
   - Confirm operation

3. **Conflict Prevention:**
   - System validates compatibility before applying
   - Warns if operation not supported by selected miners
   - Skips incompatible miners automatically

## Themes & Accessibility

The platform is designed for maximum usability:

1. **Dark/Light Theme:**
   - Toggle switch in top navigation bar
   - Preferences saved in browser localStorage
   - Consistent theming across all pages
   - Smooth transitions between themes

2. **WCAG AA Compliance:**
   - All text meets 4.5:1 minimum contrast ratios
   - Tested with WAVE and axe DevTools
   - Full audit documented in WCAG_AA_AUDIT.md
   - Keyboard navigation support

3. **Progressive Web App:**
   - Install on mobile/desktop via browser prompt
   - Works offline with cached resources
   - Service worker for background updates
   - Push notification support (ready for future use)
   - App icons for all platforms (Android, iOS, Windows, macOS)

## Automation Examples

### Price-Based Mining
Automatically switch to eco mode when electricity is expensive:
```json
{
  "name": "Expensive Energy Mode",
  "trigger": {
    "type": "price_threshold",
    "threshold": 10,
    "comparison": "above"
  },
  "action": {
    "type": "apply_mode",
    "mode": "eco"
  },
  "enabled": true
}
```

### Time-Based Profiles
Run turbo mode during cheap overnight hours:
```json
{
  "name": "Night Turbo Mode",
  "trigger": {
    "type": "time_window",
    "start": "02:00",
    "end": "07:00"
  },
  "action": {
    "type": "apply_mode",
    "mode": "turbo"
  },
  "enabled": true
}
```

### Temperature-Based Mode Switching
Reduce mode if miner gets too hot:
```json
{
  "name": "Overheat Protection",
  "trigger": {
    "type": "temperature",
    "threshold": 85,
    "comparison": "above"
  },
  "action": {
    "type": "apply_mode",
    "mode": "eco"
  },
  "enabled": true
}
```

## Pool Strategies

### Round-Robin Pool Rotation
Rotate between pools every 6 hours:
```json
{
  "name": "6-Hour Rotation",
  "strategy_type": "round_robin",
  "interval_hours": 6,
  "pool_ids": [1, 2, 3],
  "enabled": true
}
```

### Load Balancing by Health
Automatically assign miners to healthiest pools:
```json
{
  "name": "Health-Based Balancing",
  "strategy_type": "load_balance",
  "criteria": "health",
  "pool_ids": [1, 2, 3],
  "enabled": true
}
```

## Audit Logs

Track all configuration changes for compliance and troubleshooting:

1. **View Audit Logs:**
   - Go to **Settings → Audit Logs**
   - See chronological list of all changes

2. **Logged Events:**
   - Miner added/removed/updated
   - Pool added/removed/updated
   - Automation rule created/modified/deleted
   - Tuning profile applied
   - Pool strategy executed
   - Bulk operations performed
   - Settings changes

3. **Filtering:**
   - Filter by action type (create/update/delete)
   - Filter by entity type (miner/pool/automation/etc)
   - Search by description or username
   - Date range filtering

4. **Audit Information:**
   - Timestamp with timezone
   - User (future multi-user support)
   - Action performed
   - Entity affected
   - Detailed description

## Development

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run development server
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### Testing

```bash
# Run with test config
CONFIG_DIR=./test_config python app/main.py
```

### Building PWA Icons

```bash
cd app/ui/static
python generate_icons.py
```

## Troubleshooting

### Miner Not Discovered
- Ensure miner is on the same network
- Check firewall rules (ports 4028, 80, 8080, 4000)
- Verify miner IP is within configured network range
- Check miner is powered on and accessible

### Energy Prices Not Loading
- Check internet connectivity
- Verify Octopus Agile region is correct
- Review application logs in **Logs** page
- Prices update every 30 minutes

### Pool Health Always Low
- Check pool is reachable from Docker container
- Verify pool URL and port are correct
- Ensure firewall allows outbound connections
- Review pool health history in **Pools → Performance**

### Notifications Not Sending
- Test notification channels in **Notifications** page
- Verify bot token/webhook URL is correct
- Check alert thresholds match actual conditions
- Review notification logs in database

## Roadmap

### Completed Features ✅
- Monitoring & Analytics with health scoring
- Energy Optimization with auto-scheduling
- Pool Management with automatic failover
- Hardware Expansion with auto-discovery
- UI/UX Improvements (dark mode, PWA, WCAG AA)
- Audit logging

### Planned Features 🚧
- **Remote Agent Management:** Windows/Linux/macOS agents for system control (shutdown, restart, process management)
- **Multi-User Support:** Different access levels (admin/viewer/operator)
- **API Webhooks:** POST events to external services
- **Two-Factor Authentication:** Enhanced security for admin access
- **Voice Control:** Alexa/Google Home integration
- **Multi-Language Support:** i18n for global users
- **PDF Export:** Performance reports and analytics
- **Carbon Footprint Tracking:** UK grid mix data integration

## Frequently Asked Questions

### General Questions

**Q: Can I run this without Docker?**  
A: While possible, Docker is strongly recommended. You'd need Python 3.11+, manually install dependencies, and manage the service yourself.

**Q: Does this work with other cryptocurrencies?**  
A: Yes! The platform is pool-agnostic. Any Bitcoin-compatible miner (SHA-256) and XMRig for Monero (CPU mining) are supported.

**Q: How much bandwidth does this use?**  
A: Minimal. Each miner polls every 60 seconds (~1 KB per update). For 10 miners, expect ~5-10 MB/day.

**Q: Can I access this remotely?**  
A: Yes, but use a VPN (WireGuard/OpenVPN) for security. Do NOT expose directly to the internet without HTTPS and authentication.

### Energy & Pricing

**Q: Do I need Octopus Agile for this to work?**  
A: No! Agile pricing is optional. The platform works perfectly without it, you just won't have automated energy optimization.

**Q: Does this work outside the UK?**  
A: Yes for miner management. Octopus Agile pricing is UK-only, but you can still use time-based automation rules.

**Q: How accurate is the ROI calculator?**  
A: It uses current spot prices (Bitcoin/Monero) and your actual power consumption. Accuracy depends on pool fees and mining difficulty changes.

### Miners & Hardware

**Q: My miner isn't being discovered. Help?**  
A: Check: (1) Miner is powered on, (2) On same network, (3) Firewall allows port access, (4) IP is within configured CIDR range.

**Q: Can I mix different miner types?**  
A: Absolutely! That's the whole point. Manage Avalon Nano, Bitaxe, NerdQaxe, NMMiner, and XMRig all from one dashboard.

**Q: Does overclocking void my warranty?**  
A: Consult your miner's warranty terms. Home Miner Manager provides the tools, but YOU are responsible for the settings you apply.

**Q: What's the maximum number of miners supported?**  
A: Tested with 50+ miners. Actual limit depends on your hardware resources. Each miner uses ~10 MB RAM.

### Pools & Automation

**Q: Can I use multiple pools simultaneously?**  
A: Each miner connects to one pool at a time, but you can configure multiple pools and use automation/strategies to switch between them.

**Q: What happens if my primary pool goes down?**  
A: If pool health monitoring is enabled, the system automatically switches to the next available healthy pool based on your configuration.

**Q: Do automation rules conflict with each other?**  
A: The system checks for conflicts. The most recently triggered rule takes precedence. Energy optimization prevents conflicts automatically.

### Technical Questions

**Q: Where is my data stored?**  
A: Everything is in the `/config` volume: SQLite database, logs, and configuration files. This makes backups simple.

**Q: Can I access the database directly?**  
A: Yes! It's SQLite in `/config/data.db`. Use any SQLite browser. Schema is documented via SQLAlchemy models in `app/core/database.py`.

**Q: Does this phone home or collect analytics?**  
A: NO. Zero telemetry. All data stays on your machine. No tracking, no analytics, no external calls except to mining pools and Octopus Agile API (if configured).

**Q: Why is the database growing large?**  
A: Telemetry history accumulates. The system auto-purges old data (30 days for pool health, configurable for telemetry). Check **Settings** to adjust retention.

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Here's how you can help:

### Reporting Issues
- Check existing issues first to avoid duplicates
- Provide detailed reproduction steps
- Include log excerpts (from **Logs** page or `config/logs/`)
- Mention your Docker version and OS

### Feature Requests
- Explain the use case and benefits
- Check the [Roadmap](#roadmap) to see if it's planned
- Be open to discussion about implementation

### Pull Requests
- Fork the repository
- Create a feature branch (`git checkout -b feature/amazing-feature`)
- Follow existing code style (FastAPI, SQLAlchemy patterns)
- Test your changes thoroughly
- Update documentation (README, docstrings)
- Commit with clear messages
- Open PR with detailed description

### Development Guidelines
- Use type hints for all functions
- Add docstrings to public methods
- Write unit tests for new features (future)
- Follow WCAG AA guidelines for UI changes
- Test on both light and dark themes
- Ensure PWA compatibility for UI changes

## Support

### Getting Help

- **Documentation:** Read this README and [XMRig Setup Guide](docs/XMRIG_SETUP.md)
- **FAQ:** Check [Frequently Asked Questions](#frequently-asked-questions)
- **GitHub Issues:** [Report bugs or request features](https://github.com/yourusername/home-miner-manager/issues)
- **Community:** Join discussions in GitHub Discussions (if enabled)

### Before Asking for Help

1. Check the [Troubleshooting](#troubleshooting) section
2. Review application logs in **Logs** page
3. Verify Docker containers are running: `docker ps`
4. Check Docker logs: `docker logs home_miner_manager-app-1`
5. Ensure you're on the latest version

### Providing Feedback

We'd love to hear from you:
- ⭐ Star the project if you find it useful
- 📣 Share with other miners
- 💡 Suggest improvements
- 🐛 Report bugs
- 🤝 Contribute code or documentation

---

**Built with ❤️ for the Bitcoin and Monero mining community**

*Disclaimer: Mining cryptocurrency involves financial risk. This software is provided "as is" without warranty. Always do your own research and mine responsibly.*
