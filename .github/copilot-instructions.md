DANVIC.dev — Copilot Instructions
v0 Miner Controller — Full Development Specification
DANVIC.dev — Copilot Instructions
v0 Miner Controller — Full Development Specification
1. Project Purpose
The v0 Miner Controller is a modern, Dockerized, UI-driven platform designed to manage
ASIC miners:
- Avalon Nano 3 / 3S
- Bitaxe 601
- NerdQaxe++
- NMMiner ESP32 (lottery miner)
The platform handles telemetry, pool management, energy-based automation, Octopus Agile
pricing, MQTT export, and a modular dashboard. It runs entirely as a single Docker container
with a /config volume containing all persistent data.
2. High-Level Copilot Rules
Copilot MUST:
- Follow FastAPI + SQLite + MQTT + APScheduler architecture.
- Store ALL data in /config (config.yaml, data.db, logs/).
- Use WEB_PORT env var (default 8080).
- Generate UI using Jinja2 templates with sidebar navigation, breadcrumbs, and wizards.
- Implement a unified MinerAdapter interface across all miner types.
- Implement Octopus Agile pricing WITHOUT an API key.
- Write clear, modular, maintainable Python.
3. Folder Structure
/app
/adapters
/core
/api
/ui
main.py
/config (mounted volume)
4. Miner Adapter Requirements
4.1 Avalon Nano 3 / 3S
- cgminer TCP API on port 4028.
- Parse summary, pools, estats.
- Compute watts from PS[] fields:
watts = raw_power_code / (millivolts / 1000)
- Modes: low / med / high.
- Support pool switching and mode changes.
4.2 Bitaxe 601
- REST API (system/info, system/restart, etc).
- Provides native power/freq/temp.
- Modes: eco / standard / turbo / oc.
4.3 NerdQaxe++
- Same REST style as Bitaxe.
- Supports tuning, mode switching, telemetry.
4.4 NMMiner ESP32 (UDP discovery + config)
Telemetry (UDP 12345):
- MUST listen for JSON broadcasts.
- MUST ingest: Hashrate, Shares, Temp, RSSI, Uptime, Firmware, PoolInUse.
Configuration (UDP 12347):
- MUST support sending config JSON to update pool settings.
- IP "0.0.0.0" means ALL devices.
- Apply logical pools ® PrimaryPool / PrimaryAddress / PrimaryPassword.
- No power metrics; no tuning; limited automation.
5. Energy Pricing (Octopus Agile)
- Region selector (A–P).
- Use public Agile tariff API.
- No API key required.
- Store prices in SQLite.
- Expose current slot, next slot, timeline.
- Allow automation rules based on price.
6. Automation Engine
Triggers:
- Price threshold
- Time windows
- Miner offline / overheat
- Pool failure
Actions:
- Apply profile/mode (Avalon/Bitaxe/NerdQaxe)
- Switch logical pools
- Trigger NMMiner UDP config
- Log events / alerts
Rules stored in SQLite with JSON condition/action schema.
7. UI Requirements
- Left sidebar navigation.
- Breadcrumbs at top of all pages.
- Clean v0 visual design.
- Wizards for major flows (setup, add miner, pool setup, automation rules, Agile pricing).
- Configurable dashboard widgets.
8. Docker Requirements
- MUST run as a single container.
- MUST expose only WEB_PORT.
- MUST mount /config.
- MUST run uvicorn main:app --host 0.0.0.0 --port $WEB_PORT.
9. Notifications System
- Telegram Bot API and Discord Webhook support.
- Database models: NotificationConfig, AlertConfig, NotificationLog.
- Alert types: miner_offline, high_temperature, high_reject_rate, pool_failure, low_hashrate.
- Scheduler checks alerts every 5 minutes.
- UI at /notifications for channel setup and alert configuration.
- Test notification endpoints available.

10. Copilot Behaviour Rules
- ALWAYS follow this architecture.
- ALWAYS use SQLite + FastAPI + Jinja2.
- Treat NMMiner as telemetry + pool-control-only.
- NEVER add more env vars beyond WEB_PORT, TZ, PUID, PGID.
- Generate maintainable, modular Python code.

11. Future Enhancement Roadmap

11.1 Monitoring & Analytics
- Health scoring system based on uptime, temperature, reject rate, hashrate stability
- Comparative analytics with time-series charts (day/week/month)
- Historical performance tracking and trend analysis
- Real-time dashboard widgets with drag-and-drop customization
- CSV/PDF export of performance reports

11.2 Energy Optimization
- Smart scheduling: auto-adjust modes based on Agile pricing thresholds
- ROI calculator: real-time profitability (coin value - energy cost)
- Break-even projections and mining profitability alerts
- Carbon footprint tracking using UK grid mix data
- Power consumption forecasting

11.3 Pool Management
- Intelligent failover: auto-switch on high reject rate or pool offline
- Pool performance comparison: luck %, latency, reject rates over time
- Multi-pool strategies: round-robin, load balancing
- Pool response time monitoring
- Automatic pool health scoring

11.4 Hardware Expansion
- Network auto-discovery: scan for miners and suggest adding
- Firmware management: check for updates, display versions
- Overclocking profiles: save/load custom tuning presets
- Bulk operations: apply settings to multiple miners
- Hardware health predictions based on telemetry trends

11.5 UI/UX Improvements
- Dark/light theme toggle with user preferences
- Custom dashboard layouts: drag-and-drop widgets, per-user configs
- Progressive Web App (PWA) for mobile access
- Voice control integration (Alexa/Google Home)
- Multi-language support
- Accessibility improvements (WCAG compliance)

11.6 Advanced Features
- API webhooks: POST events to external services
- Backup/restore: export/import full configuration
- Multi-user support: different access levels (admin/viewer/operator)
- Audit logging: track all configuration changes
- Two-factor authentication for admin access
- Rate limiting and API throttling

11.7 Developer Experience
- Plugin system: community-developed miner adapters
- Auto-generated OpenAPI/Swagger documentation
- Simulation mode: test automation rules without hardware
- Development mode with mock miners
- Comprehensive unit and integration tests
- CI/CD pipeline templates