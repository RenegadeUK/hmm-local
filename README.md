# Home Miner Manager

**The complete mining management platform built for profitability.** Intelligent energy optimization, automated solo mining strategies, and comprehensive miner management—all in one powerful dashboard.

![Docker](https://img.shields.io/badge/Docker-20.10+-2496ED?logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)
![WCAG](https://img.shields.io/badge/WCAG-AA-green)
![PWA](https://img.shields.io/badge/PWA-Ready-5A0FC8?logo=pwa&logoColor=white)

---

## Why Home Miner Manager?

Mining profitably at home requires more than just hardware—it requires intelligence. Home Miner Manager automatically optimizes when and what you mine based on real-time energy prices and coin profitability.

### 🎯 The Agile Solo Strategy

**Mine the right coin at the right time:**
- ⚡ **Fully Configurable Bands** - Set 5 price bands with custom coin and mode per band
- 💰 **Dynamic Coin Switching** - Auto-switch between OFF/DGB/BCH/BTC based on energy prices
- 🎛️ **Per-Band Modes** - Configure eco/standard/turbo/overclock for each price tier
- 🔄 **Hysteresis Prevention** - Look-ahead logic prevents rapid oscillation between bands
- 📊 **Band Analytics** - Track band transitions, time in each band, and profitability
- 🏠 **UK Octopus Agile** - No API key required, automatic price updates every 30 minutes
- 💡 **Example Strategy**: OFF above 20p → DGB eco 12-20p → DGB std 7-12p → BCH OC 4-7p → BTC OC below 4p

![Agile Solo Strategy](screenshots/agile-solo-strategy.png)

### ⚡ Intelligent Energy Management

**Stop wasting money on expensive electricity:**
- 🔋 **Real-time Pricing** - Half-hourly Octopus Agile tariff integration
- 📈 **24-Hour Forecast** - See upcoming prices with visual sparkline charts
- 💰 **Automatic Optimization** - Mine during cheap slots, idle during expensive ones
- ⚙️ **Manual Override** - Force enable/disable independent of price bands
- 📊 **Cost Tracking** - Total energy consumption with per-miner breakdowns
- 💡 **Typical Result**: 20-40% reduction in electricity costs vs always-on mining

![Energy Dashboard](screenshots/energy-dashboard.png)

---

## 🚀 Quick Start

**Runs on anything—Raspberry Pi, spare laptop, NAS, or dedicated server.**

```bash
git clone https://github.com/RenegadeUK/home_miner_manager.git
cd home_miner_manager
cp .env.example .env
docker-compose up -d
```

Access at `http://localhost:8080`

---

## 📋 Table of Contents

- [Features](#-features)
- [Supported Hardware](#-supported-hardware)
- [Dashboard](#️-dashboard)
- [CPU Dashboard](#-cpu-dashboard)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Agile Solo Strategy Setup](#-agile-solo-strategy-setup)
- [Pool Management](#-pool-management)
- [Notifications](#-notifications)
- [API Documentation](#-api-documentation)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## ✨ Features

### 🎯 Configurable Agile Solo Strategy

The crown jewel—fully database-driven band configuration:

- **5 Configurable Bands** - Each band defines a price range with custom coin and modes
- **Per-Band Configuration**:
  - Target coin: OFF, DGB, BCH, or BTC
  - Bitaxe mode: eco, standard, turbo, overclock
  - Avalon Nano mode: low, medium, high
- **Hysteresis Logic** - Look-ahead confirmation prevents rapid band switching
- **Visual Band Editor** - Dropdowns for each slot, live preview of current band
- **Reset to Defaults** - One-click restore of proven profitable strategy
- **Audit Trail** - Every band change, transition, and override logged with timestamps
- **REST API** - Full CRUD operations for programmatic control

![Band Configuration](screenshots/band-editor.png)

### 📊 Pool Analytics & Monitoring

**Native integrations with detailed statistics:**

- **Solopool (BCH/DGB/BTC)**:
  - Workers online with hashrate sparklines
  - 24-hour hashrate charts
  - Best share tracking
  - Immature/unpaid balance monitoring

![Pool Dashboard](screenshots/pool-analytics.png)

### 🔧 Hardware Management

**Comprehensive multi-brand support:**

- **Avalon Nano 3/3S** - cgminer API with pool slot management
- **Bitaxe (All Models)** - Full REST API integration with frequency tuning
- **NerdQaxe++** - REST API with mode presets
- **NMMiner ESP32** - UDP telemetry + configuration

**Features:**
- 🔍 **Network Auto-Discovery** - Scan and auto-add compatible miners
- 🎛️ **Bulk Operations** - Enable/disable, restart, change modes across multiple miners
- 📦 **Firmware Tracking** - Display and track firmware versions
- 🔧 **Overclocking Profiles** - Save/load/apply custom tuning presets
- 📊 **Real-time Telemetry** - Hashrate, temperature, power, fan speed, chip stats

![Miner Management](screenshots/miner-dashboard.png)
### ⚙️ Dashboard

**Main view for all your miners:**

- **Avalon Nano / Bitaxe / NerdQaxe / NMMiner** - All miners in one view
- **Pool Slot Management** - Visual pool assignment per miner
- **Mode Controls** - Quick access to eco/standard/turbo/overclock settings
- **Agile Strategy Integration** - See current band and target modes
- **Real-time Stats** - Hashrate, temperature, power consumption
- **Bulk Actions** - Manage multiple miners simultaneously

![Dashboard](screenshots/asic-dashboard.png)

###  Notifications & Alerts

**Stay informed without being overwhelmed:**

- **Telegram Bot** - Rich messages with inline buttons
- **Discord Webhooks** - Embeds with color-coded severity
- **Configurable Alerts**:
  - Miner offline/online
  - Temperature warnings
  - High reject rates
  - Energy price thresholds
  - Block discoveries
  - Band transitions
- **Rate Limiting** - Prevent notification spam
- **Custom Templates** - Markdown support for formatted messages

![Notifications](screenshots/notifications.png)

### 🔐 Security & Auiting

**Enterprise-grade logging and access control:**

- 📝 **Full Audit Trail** - Every configuration change logged with user, timestamp, before/after
- 🔍 **Searchable Logs** - Filter by action type, user, date range, entity
- 🔒 **API Authentication** - Token-based security (optional for local installs)
- 🛡️ **Rate Limiting** - Prevent abuse and DOS attacks
- 📊 **Activity Monitoring** - Track API usage and system health

---

## 🖥️ Supported Hardware

| Hardware | API Type | Supported Features |
|----------|----------|-------------------|
| **Avalon Nano 3/3S** | cgminer TCP (4028) | Pool switching, mode control, telemetry, multi-slot management |
| **Bitaxe (All)** | REST API | Full control, frequency tuning, voltage adjustment, mode presets |
| **NerdQaxe++** | REST API | Mode control, telemetry, basic configuration |
| **NMMiner ESP32** | UDP | Telemetry, configuration, lottery mining tracking |

**System Requirements:**
- Docker 20.10+ and Docker Compose
- 512 MB RAM minimum (runs great on Raspberry Pi)
- Any x86_64 or ARM64 system

---

## 📦 Installation

### Docker Compose (Recommended)

1. **Clone the repository:**
```bash
git clone https://github.com/RenegadeUK/home_miner_manager.git
cd home_miner_manager
```

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env if needed (defaults work for most users)
```

3. **Start the platform:**
```bash
docker-compose up -d
```

4. **Access the dashboard:**
```
http://localhost:8080
```

### Manual Installation (Advanced)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

---

## ⚙️ Configuration

### Initial Setup

1. **Set Your Octopus Agile Region**
   - Navigate to **Energy → Pricing**
   - Select your region (A-P for UK postcode areas)
   - Prices sync automatically every 30 minutes

2. **Add Your First Miner**
   - Use **Auto-Discovery**: Settings → Discovery → Scan Network
   - Or manually: Miners → Add Miner

3. **Configure Pools**
   - Pools → Add Pool
   - Enter pool URL, port, wallet address
   - Assign to miners

### Configuration Files

**Main Configuration:** `config/config.yaml`
```yaml
app:
  host: "0.0.0.0"
  port: 8080
  
energy:
  provider: "octopus_agile"
  default_region: "B"
  update_interval_minutes: 30
  
notifications:
  telegram:
    enabled: false
    bot_token: "YOUR_BOT_TOKEN"
    chat_id: "YOUR_CHAT_ID"
  discord:
    enabled: false
    webhook_url: "YOUR_WEBHOOK_URL"
```

**Environment Variables:** `.env`
```bash
# Database
DATABASE_URL=sqlite+aiosqlite:///./config/miner_manager.db

# API Settings
API_AUTH_ENABLED=false
API_KEY=your-secure-key-here

# Logging
LOG_LEVEL=INFO
```

---

## 🎯 Agile Solo Strategy Setup

The Agile Solo Strategy is the core intelligence of the platform. Here's how to configure it:

### Understanding Bands

The strategy uses **5 configurable bands**, each defining:
- **Price Range** - Min/max energy price in pence per kWh
- **Target Coin** - OFF, DGB, BCH, or BTC
- **Miner Modes** - eco/standard/turbo/overclock for each miner type

### Default Band Configuration

| Band | Price Range | Coin | Bitaxe Mode | Avalon Mode | Rationale |
|------|-------------|------|-------------|-------------|-----------|
| 1 | ≥20p | OFF | - | - | Too expensive to mine |
| 2 | 12-20p | DGB | eco | low | Low power, decent profitability |
| 3 | 7-12p | DGB | standard | medium | Standard power, good returns |
| 4 | 4-7p | BCH | overclock | high | Higher power, best BCH profitability |
| 5 | <4p | BTC | overclock | high | Maximize hashrate, BTC solo lottery |

### Customizing Bands

1. Navigate to **Strategy → Band Configuration**
2. Click dropdown for coin or mode in any band
3. Select new value
4. Changes save automatically and apply at next 30-minute boundary
5. Monitor transitions in **Strategy → Audit Log**

![Band Configuration Editor](screenshots/band-config.png)

### Strategy Behavior

**Automatic Execution:**
- Runs every 30 minutes (aligned with Agile pricing slots)
- Evaluates current energy price
- Determines target band
- Applies hysteresis (look-ahead confirmation)
- Switches coin and modes if needed
- Logs transition with reason

**Hysteresis Logic:**
When upgrading to a cheaper band, the system checks if the *next* 30-minute slot also qualifies. This prevents rapid switching if a single cheap slot is followed by expensive slots.

**Manual Override:**
- **Enable Strategy** - Force enable regardless of price
- **Disable Strategy** - Force disable regardless of price  
- Override state persists until manually changed or strategy re-enabled

### Monitoring Strategy Performance

- **Current Band** - Dashboard shows active band and target coin/modes
- **Band Transitions** - Audit log tracks every band change with timestamp and reason
- **Time in Band** - Analytics show duration in each band over time
- **Profitability** - Track earnings per band to optimize configuration

---

## 🏊 Pool Management

### Supported Pools

**Solo Mining Pools:**
- **Solopool** - BCH, DGB, BTC solo mining with statistics API
- **Braiins Pool** - Bitcoin FPPS mining with detailed stats

**Public Pools:**
- Any stratum pool compatible with cgminer

### Adding a Pool

```json
{
  "name": "Solopool DGB",
  "url": "stratum+tcp://eu1.solopool.org",
  "port": 3014,
  "wallet": "your_dgb_address",
  "password": "x",
  "coin": "DGB"
}
```

### Pool Health Monitoring

The platform monitors:
- ✅ Connection status (active/inactive)
- 📊 Share acceptance rate
- ⏱️ Last share timestamp
- 🎯 Best share found
- 💰 Balance (for solo pools with API)

### Pool Analytics

**Solopool Integration:**
- Workers online count with sparkline charts
- 24-hour hashrate graph
- Best share tracking
- Immature/unpaid balance
- Auto-refresh every 5 minutes

![Pool Analytics](screenshots/pool-health.png)

---

## 🔔 Notifications

### Telegram Setup

1. Create bot with [@BotFather](https://t.me/botfather)
2. Get bot token
3. Send message to bot
4. Get chat ID from `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Add to `config.yaml`:

```yaml
notifications:
  telegram:
    enabled: true
    bot_token: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    chat_id: "123456789"
```

### Discord Setup

1. Create webhook in Discord server settings
2. Copy webhook URL
3. Add to `config.yaml`:

```yaml
notifications:
  discord:
    enabled: true
    webhook_url: "https://discord.com/api/webhooks/..."
```

### Notification Types

- 🔴 **Critical**: Miner offline, temperature danger
- ⚠️ **Warning**: High reject rate, temperature warning
- ℹ️ **Info**: Miner online, band transition
- ✅ **Success**: Block found, optimal price detected

### Rate Limiting

Notifications are rate-limited to prevent spam:
- Same event: 5-minute cooldown
- Temperature warnings: 15-minute cooldown
- Status changes: Immediate (online→offline→online)

---

## 📚 API Documentation

Full REST API with OpenAPI/Swagger documentation at `/docs`

### Key Endpoints

**Agile Solo Strategy:**
```bash
# Get strategy status
GET /api/settings/agile-solo-strategy

# Execute strategy manually
POST /api/settings/agile-solo-strategy/execute

# Enable/disable strategy
POST /api/settings/agile-solo-strategy/enable
POST /api/settings/agile-solo-strategy/disable

# Get all bands
GET /api/settings/agile-solo-strategy/bands

# Update a band
PATCH /api/settings/agile-solo-strategy/bands/{band_id}
{
  "target_coin": "BCH",
  "bitaxe_mode": "overclock",
  "avalon_nano_mode": "high"
}

# Reset bands to defaults
POST /api/settings/agile-solo-strategy/bands/reset
```

**Miners:**
```bash
# List all miners
GET /api/miners

# Get miner details
GET /api/miners/{miner_id}

# Update miner
PATCH /api/miners/{miner_id}

# Bulk operations
POST /api/miners/bulk/enable
POST /api/miners/bulk/disable
POST /api/miners/bulk/restart
```

**Energy:**
```bash
# Get current price
GET /api/energy/current-price

# Get price forecast
GET /api/energy/forecast

# Update prices
POST /api/energy/update-prices
```

### Authentication

API authentication is optional and disabled by default for local installations.

To enable:
```bash
# In .env
API_AUTH_ENABLED=true
API_KEY=your-secure-random-key-here
```

Include token in requests:
```bash
curl -H "Authorization: Bearer your-api-key" http://localhost:8080/api/miners
```

---

## 🛠️ Development

### Running Locally

```bash
# Clone repository
git clone https://github.com/RenegadeUK/home_miner_manager.git
cd home_miner_manager

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

### Project Structure

```
home_miner_manager/
├── app/
│   ├── main.py              # FastAPI application entry
│   ├── adapters/            # Hardware adapters
│   │   ├── avalon_nano.py
│   │   ├── bitaxe.py
│   │   ├── nerdqaxe.py
│   │   └── nmminer.py
│   ├── api/                 # REST API endpoints
│   │   ├── agile_solo_strategy.py
│   │   ├── miners.py
│   │   ├── pools.py
│   │   ├── energy.py
│   │   └── analytics.py
│   ├── core/                # Business logic
│   │   ├── agile_solo_strategy.py
│   │   ├── agile_bands.py
│   │   ├── scheduler.py
│   │   └── pool_slots.py
│   └── ui/                  # Frontend templates
├── config/
│   ├── config.yaml          # Main configuration
│   └── logs/                # Application logs
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Running Tests

```bash
# Run test suite
pytest

# Run specific test file
pytest test_agile_solo_strategy.py

# Run with coverage
pytest --cov=app tests/
```

### Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

## 🐛 Troubleshooting

### Miner Not Discovered

**Problem:** Auto-discovery doesn't find miners

**Solutions:**
- Verify miner is on same network
- Check IP range includes miner's address
- Ensure firewall allows discovery
- Try manual addition with known IP

### Strategy Not Executing

**Problem:** Agile Solo Strategy not switching coins/modes

**Solutions:**
- Check strategy is enabled: Strategy → Status
- Verify region is set: Energy → Pricing
- Check current price is within configured bands
- Review audit log for error messages: Strategy → Audit

### High Reject Rate

**Problem:** Pool shows high reject rate (>5%)

**Solutions:**
- Check network latency to pool
- Try different pool server (geographic proximity)
- Verify miner difficulty setting
- Check for network congestion

### Temperature Warnings

**Problem:** Miner temperature exceeds safe limits

**Solutions:**
- Improve airflow around miner
- Lower overclock settings
- Use lower power mode in strategy bands
- Clean dust from heatsinks/fans

### Energy Prices Not Updating

**Problem:** Agile prices showing stale data

**Solutions:**
- Check internet connectivity
- Verify region is correct: Energy → Pricing
- Manually trigger update: Energy → Update Now
- Check logs for API errors: docker logs v0-miner-controller

### Docker Container Won't Start

**Problem:** Container fails to start or crashes

**Solutions:**
```bash
# Check logs
docker logs v0-miner-controller

# Rebuild container
docker-compose down
docker-compose up -d --build

# Check for port conflicts
lsof -i :8080
```

### Database Errors

**Problem:** SQLite errors or database corruption

**Solutions:**
```bash
# Backup database
cp config/miner_manager.db config/miner_manager.db.backup

# Reset database (WARNING: loses data)
rm config/miner_manager.db
docker-compose restart
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- Octopus Energy for public Agile API
- Solopool for solo mining infrastructure
- cgminer/bfgminer developers
- FastAPI and Python community

---

## 📧 Support

- **Issues**: [GitHub Issues](https://github.com/RenegadeUK/home_miner_manager/issues)
- **Discussions**: [GitHub Discussions](https://github.com/RenegadeUK/home_miner_manager/discussions)

---

**Built with ❤️ for the home mining community**