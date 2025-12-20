DANVIC.dev — Copilot Instructions
Home Miner Manager v1.0.0 — Production Release
DANVIC.dev — Copilot Instructions
Home Miner Manager v1.0.0 — Production Release
1. Project Purpose
Home Miner Manager v1.0.0 is a production-ready, Dockerized, UI-driven platform designed to manage
ASIC miners:
- Avalon Nano 3 / 3S
- Bitaxe 601
- NerdQaxe++
- NMMiner ESP32 (lottery miner)
The platform handles telemetry, pool management, energy-based automation, Octopus Agile
pricing, MQTT export, and a modular dashboard. It runs entirely as a single Docker container
with a /config volume containing all persistent data.

## CRITICAL: Agent Behavior Rules

**These rules MUST be followed for every interaction:**

1. **NEVER make code changes without explicit user permission** - Always ask before modifying any file
2. **Always search existing code first** - Use grep_search, file_search, or semantic_search before creating new files or functions to avoid duplicates and conflicts
3. **NEVER interrupt running processes** - Do not kill Flask app, terminal processes, or any background jobs without user request
4. **Test after every change** - Validate that changes work correctly and didn't break anything before proceeding
5. **Work in small incremental chunks** - Make one small change, test it, get confirmation, then continue
6. **Track incomplete work** - When a feature is partially implemented:
   - Explicitly state "⚠️ INCOMPLETE" and list what's not finished
   - Warn user if they want to switch tasks
   - Maintain a checklist of remaining work
7. **Always finish what you start** - Never leave a job half-done without user acknowledgment
8. **Respect running applications** - If Flask app is running, do not execute terminal commands that would interfere with it
9. **Document before changing** - Always document what exists before making changes:
   - Document current implementation and requirements
   - Update documentation after changes are complete
   - Save design documents and requirements analysis

**Before making ANY change:**
- Search for existing implementations
- Ask user for permission
- Explain what will be changed and why
- Get explicit "yes" before proceeding

10. High-Level Copilot Rules
Copilot MUST:
- **BEFORE adding new functionality, ALWAYS check and understand what is already in place** - review existing code, patterns, validation logic, and similar features to avoid duplication or conflicts.
- Follow FastAPI + SQLite + MQTT + APScheduler architecture.
- Store ALL data in /config (config.yaml, data.db, logs/).
- Use WEB_PORT env var (default 8080).
- Generate UI using Jinja2 templates with sidebar navigation, breadcrumbs, and wizards.
- Implement a unified MinerAdapter interface across all miner types.
- Implement Octopus Agile pricing WITHOUT an API key.
- Write clear, modular, maintainable Python.
- **ALWAYS log errors and failures with detailed context for debugging**.
- **ALWAYS implement automatic recovery mechanisms - the system MUST self-heal without user intervention**.
- When failures occur, log the issue AND implement retry logic, reconciliation processes, or fallback strategies.
- Users should never need to manually fix transient issues (network timeouts, API failures, miner restarts, etc).


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
- **Mode Detection: MUST use WORKMODE field from estats MM ID string, NOT frequency**.
  - WORKMODE values: 0=low, 1=med, 2=high
  - Parse using _detect_current_mode() method
  - Example MM ID string: "Ver[1200-80-21042601_4ec6bb0_211fc83] DNA[020100002e8accf8] MEMFREE[176976.0] NETFAIL[0 0 0 0 0 0 0 0] SYSTEMSTATU[Work: In Work, Hash Board: 1 ] Elapsed[1234] BOOTBY[0x01.00000000] LV[0] MW[0 0 0] LED[0] MGHS[123.45] MTmax[90] MTavg[85] TA[100] Core[A3200] PING[12] POWS[0] FANR[3000] FAN[100] WORKMODE[2] PVT_T[85-92/87]"
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

11.1 Monitoring & Analytics ✅ COMPLETED
- ✅ Health scoring system based on uptime, temperature, reject rate, hashrate stability
- ✅ Miner type-aware temperature thresholds (95°C for Avalon Nano, 75°C for NerdQaxe, 70°C for Bitaxe)
- ✅ Comparative analytics with time-series charts (day/week/month)
- ✅ Historical performance tracking and trend analysis
- ✅ CSV export of performance reports
- ✅ Per-miner analytics page with dynamic time ranges (6h/24h/3d/7d)
- ✅ Independent hashrate unit display (GH/s vs TH/s per metric)
- ✅ Total energy consumption calculation (kWh) based on selected time range
- ✅ Cache busting for real-time data updates when switching miners
- ✅ Real-time dashboard widgets with drag-and-drop customization (12 widget types)
- ✅ Custom dashboard system: create multiple dashboards, GridStack-based builder, auto-save layouts
- Future: PDF export of performance reports

11.2 Energy Optimization ✅ COMPLETED
- ✅ Smart scheduling: auto-adjust modes based on Agile pricing thresholds
- ✅ ROI calculator: real-time profitability (coin value - energy cost)
- ✅ Price forecast visualization with 24-hour ahead predictions
- ✅ Auto-optimization toggle with configurable price threshold
- ✅ Manual trigger button for immediate optimization
- ✅ Conflict prevention with automation rules
- Future: Break-even projections and mining profitability alerts
- Future: Carbon footprint tracking using UK grid mix data
- Future: Power consumption forecasting

11.3 Pool Management ✅ COMPLETED
- ✅ Pool health monitoring: connectivity checks every 5min, response time measurement, reject rate tracking
- ✅ Automatic pool health scoring (0-100): reachability 40pts, response time 30pts, reject rate 30pts
- ✅ Intelligent failover: auto-switch on high reject rate, pool offline, or low health score
- ✅ Configurable failover thresholds and enable/disable toggle
- ✅ Manual failover trigger via UI
- ✅ Pool health metrics displayed in pools table (health score, response time, reject rate)
- ✅ Historical pool health tracking with 30-day auto-purge
- ✅ Pool performance comparison: luck %, latency trends, health scores, reject rates over time (24h/3d/7d/30d)
- ✅ Multi-chart comparison view with color-coded pool legends
- ✅ Multi-pool strategies: round-robin rotation at fixed intervals, load balancing by health/latency/reject rate
- ✅ Pool priority field for weighted load balancing
- ✅ Strategy execution via scheduler (every minute)
- ✅ Strategy management UI with manual execution and configuration
- ✅ Per-miner strategy assignment with conflict prevention

11.4 Hardware Expansion ✅ COMPLETED
- ✅ Network auto-discovery: scan for Avalon Nano (cgminer API), Bitaxe/NerdQaxe (HTTP API)
- ✅ Configurable network ranges with custom CIDR notation
- ✅ Auto-add discovered miners toggle
- ✅ Scheduled auto-discovery with configurable scan interval (1-168 hours)
- ✅ Manual per-network scanning with discovery settings page
- ✅ Auto-detection of local network CIDR for quick setup
- ✅ Firmware management: track and display firmware versions from telemetry
- ✅ Overclocking profiles: save/load/apply custom tuning presets (frequency, voltage, mode)
- ✅ Bulk operations: enable/disable, set mode, switch pool, restart, apply profile to multiple miners
- ✅ Hardware health predictions: statistical analysis of telemetry trends predicting temperature issues, hashrate decline, power anomalies, reject rate problems, and disconnection patterns

11.5 UI/UX Improvements ✅ COMPLETED
- ✅ Collapsible FAQ sections with smooth animations and expand/collapse all
- ✅ FAQ search functionality with real-time filtering and text highlighting
- ✅ Logs page filter tiles (All/Info/Success/Warning/Error) with event counts
- ✅ Pagination on logs page: 50 events per page, 4 pages (200 total), filters work across all pages
- ✅ Dark/light theme toggle with user preferences and localStorage persistence
- ✅ Theme CSS variables system for consistent theming across all pages
- ✅ WCAG AA accessibility compliance: all text meets 4.5:1 minimum contrast ratios
- ✅ Progressive Web App (PWA): installable on mobile/desktop, offline support, service worker caching, push notifications ready
- Future: Voice control integration (Alexa/Google Home)
- Future: Multi-language support

11.6 Advanced Features ✅ PARTIALLY COMPLETED
- ✅ Audit logging: track all configuration changes (database model, API endpoints, UI page with filtering)
- ❌ Backup/restore: REMOVED - Copilot incapable of delivering usable implementation. OAuth complexity, poor UX, overly complicated for simple configuration export. Feature removed entirely.
- ✅ Integrated MQTT broker: Eclipse Mosquitto 2.0 in Docker stack for self-contained messaging infrastructure
- Future: API webhooks: POST events to external services
- Future: Multi-user support: different access levels (admin/viewer/operator)
- Future: Two-factor authentication for admin access
- Future: Rate limiting and API throttling

11.7 Remote Agent Management 🚧 PLANNED
- Windows agent: lightweight Python service for remote system control
  - System control: shutdown, restart, sleep, hibernate, lock, log off, power plans
  - Process management: start/stop applications, kill processes, launch scripts
  - Monitoring: CPU/RAM/Disk usage, running processes, network stats, uptime
  - File operations: run scheduled tasks, execute PowerShell/batch scripts
  - MQTT communication: subscribe to commands, publish telemetry
  - Security: API key authentication, command signing, whitelist, audit logging
  - Local override: physical disable for safety
- UI integration: Agents section with system stats cards and quick actions
- Automation integration: "Shut down idle machines when electricity is expensive"
- Wake-on-LAN: power on machines remotely
- Agent installer: Windows Service, auto-start on boot
- Cross-platform: Linux/macOS agent support
- Fleet management: bulk agent commands, health monitoring

11.8 Developer Experience
- Plugin system: community-developed miner adapters
- Auto-generated OpenAPI/Swagger documentation
- Simulation mode: test automation rules without hardware
- Development mode with mock miners
- Comprehensive unit and integration tests
- CI/CD pipeline templates