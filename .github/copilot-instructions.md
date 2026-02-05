# DANVIC.dev — Copilot Instructions
# Home Miner Manager (HMM-Local) v1.0.0 — Production Release

## 1. Project Purpose

Home Miner Manager v1.0.0 is a production-ready, Dockerized platform for managing ASIC miners with intelligent automation:

**Supported Hardware:**
- Avalon Nano 3 / 3S (cgminer API)
- Bitaxe 601 (HTTP REST API)
- NerdQaxe++ (HTTP REST API)
- NMMiner ESP32 (UDP broadcast telemetry)

**Core Features:**
- Real-time telemetry collection (30-second intervals)
- Octopus Agile pricing integration (UK regions A-P)
- Agile Solo Strategy: Price-based band automation with champion mode
- Pool management with health monitoring and failover
- Home Assistant integration for power control
- Custom dashboards with drag-and-drop widgets
- Hardware health predictions
- Audit logging for all configuration changes

**Architecture:**
- **Single Docker container** (FastAPI + React + PostgreSQL)
- Database: **PostgreSQL 16** embedded in container (localhost:5432)
- UI: React 18 + TypeScript + Vite + TailwindCSS
- Scheduler: APScheduler (1-minute strategy execution)
- Volume: `/config` (config.yaml, postgres/, logs/, plugins/)
- **Fresh install only** - No migration system, schema deployed from models

---

## 2. CRITICAL: Agent Behavior Rules

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
10. **BEFORE adding new functionality, ALWAYS check and understand what is already in place** - review existing code, patterns, validation logic, and similar features to avoid duplication or conflicts
11. **ALWAYS log errors and failures with detailed context for debugging**
12. **ALWAYS implement automatic recovery mechanisms** - the system MUST self-heal without user intervention
13. When failures occur, log the issue AND implement retry logic, reconciliation processes, or fallback strategies
14. Users should never need to manually fix transient issues (network timeouts, API failures, miner restarts, etc)

**Before making ANY change:**
- Search for existing implementations
- Ask user for permission
- Explain what will be changed and why
- Get explicit "yes" before proceeding

---

## 3. Architecture Overview

### 3.1 Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Backend | FastAPI | 0.115+ | REST API and WebSocket server |
| Database | PostgreSQL | 16+ | Primary data store |
| Database (Fallback) | SQLite | 3.x | Development/fallback |
| Frontend | React | 18 | UI framework |
| UI Build | Vite | 5.x | Build tool for React |
| Styling | TailwindCSS | 3.x | Utility-first CSS |
| Components | shadcn/ui | - | React component library |
| Scheduler | APScheduler | 3.x | Background job execution |
| ORM | SQLAlchemy | 2.0+ | Async database operations |

### 3.2 Folder Structure

```
/app
  /adapters           # Miner adapter implementations
    avalon_nano.py    # Avalon Nano 3/3S (cgminer API)
    bitaxe.py         # Bitaxe 601 (HTTP REST)
    nerdqaxe.py       # NerdQaxe++ (HTTP REST)
    nmminer.py        # NMMiner ESP32 (UDP telemetry)
  /api                # FastAPI route handlers
    agile_solo_strategy.py
    analytics.py
    automation.py
    dashboard.py
    miners.py
    operations.py
    pools.py
    settings.py
    websocket.py
  /core               # Core business logic
    agile_solo_strategy.py  # Main strategy execution
    automation.py
    config.py
    database.py       # SQLAlchemy models
    migrations.py     # Database schema migrations
    pool_slots.py     # Avalon pool slot sync
    scheduler.py      # APScheduler jobs
  /integrations
    braiins.py        # Braiins Pool API
    octopus_agile.py  # Octopus Energy pricing
    solopool.py       # Solo.ckpool API
  /ui
    /static/app/      # React build output (auto-generated)
    ui_routes.py      # Serve React app
  main.py             # FastAPI application entry point

/ui-react             # React source code
  /src
    /components       # Reusable React components
    /pages            # Page components
    /services         # API client functions
  package.json
  vite.config.ts

/config (mounted volume)
  config.yaml         # User configuration
  data.db             # SQLite database (if used)
  /logs               # Application logs
```

### 3.3 Database Architecture

**PostgreSQL Only:**
- Embedded in single container (localhost:5432)
- Data directory: `/config/postgres/`
- Fresh install deploys schema from SQLAlchemy models
- No migrations - clean deployment only

**Key Models:**
- `Miner`: Hardware configuration and state
- `Telemetry`: Time-series performance data
- `Pool`: Mining pool configuration
- `PoolHealthLog`: Pool monitoring history
- `AgileStrategy`: Price band configuration and state
- `AgileStrategyBand`: Individual price band settings
- `EnergyPrice`: Octopus Agile pricing data
- `Automation`: Custom automation rules
- `Event`: System event log
- `AuditLog`: Configuration change tracking

**Schema Deployment:**
- `init_db()` calls `Base.metadata.create_all()`
- Tables created from model definitions
- No migration system - this is a new product

---

## 4. Miner Adapter Requirements

### 4.1 Avalon Nano 3 / 3S

**Protocol:** cgminer TCP API on port 4028

**Key Methods:**
- `summary`: Get hashrate, temperature, uptime
- `pools`: Get pool status and shares
- `estats`: Get detailed statistics (includes WORKMODE)

**Power Calculation:**
```python
watts = raw_power_code / (millivolts / 1000)
```

**Modes:** `low` / `med` / `high`

**Mode Detection:**
- MUST use `WORKMODE` field from `estats` MM ID string
- WORKMODE values: 0=low, 1=med, 2=high
- Do NOT use frequency for mode detection
- Example MM ID: `"Ver[1200-80-21042601_4ec6bb0_211fc83] ... WORKMODE[2] ..."`

**Pool Switching:**
- Use `app/core/pool_slots.py` for Avalon-specific pool management
- Sync logical pools to physical slots (0-2)
- Handle pool slot ordering

### 4.2 Bitaxe 601

**Protocol:** HTTP REST API

**Endpoints:**
- `GET /api/system/info` - Get hashrate, temperature, frequency
- `POST /api/system/restart` - Restart device
- `PATCH /api/system` - Update settings

**Modes:** `eco` / `standard` / `turbo` / `oc`

**Native Metrics:**
- Power consumption (watts)
- Frequency (MHz)
- Temperature (°C)

### 4.3 NerdQaxe++

**Protocol:** HTTP REST API (similar to Bitaxe)

**Modes:** `eco` / `standard` / `turbo` / `oc`

**Features:**
- Tuning profiles
- Mode switching
- Real-time telemetry

### 4.4 NMMiner ESP32

**Protocol:** UDP broadcast (telemetry only)

**Telemetry Port:** 12345 (JSON broadcasts)

**Configuration Port:** 12347 (send JSON config)

**Ingested Data:**
- Hashrate
- Shares (accepted/rejected)
- Temperature
- RSSI (Wi-Fi signal)
- Uptime
- Firmware version
- Pool in use

**Configuration:**
- Send config JSON to UDP 12347
- IP `"0.0.0.0"` targets ALL devices
- Update pool settings only (no power/mode control)

**Limitations:**
- No power metrics
- No tuning support
- Limited automation capabilities

---

## 5. Agile Solo Strategy

### 5.1 Overview

Price-based automation system that adjusts miner behavior based on Octopus Agile electricity pricing.

**Execution:** Every 1 minute via APScheduler  
**Reconciliation:** Every 5 minutes (corrects drift)

### 5.2 Price Bands

Each band defines:
- Coin to mine (BCH, DGB, BC2, BTC)
- Price threshold (pence/kWh)
- Target mode per miner type
- Pool assignment

**Band Priority:** Sorted by `sort_order` (ascending)

**Band Matching:**
- Current price compared against thresholds
- Highest matching band selected
- Hysteresis prevents rapid switching

### 5.3 Champion Mode (NEW - 2 Feb 2026)

**Purpose:** Maximize efficiency during expensive electricity (Band 5: 20-30p/kWh)

**Behavior:**
- When Band 5 active AND champion mode enabled:
  - Calculate efficiency (W/TH) for all miners from last 6 hours telemetry
  - Select most efficient miner as "champion"
  - Champion runs in LOWEST mode (eco/low)
  - All other miners turn OFF via Home Assistant
  - Champion remains sticky until band exit

**Champion Selection:**
```python
efficiency = average_power_watts / (average_hashrate_th * 1000)
# Lower W/TH = better efficiency
```

**Promotion on Failure:**
- Track consecutive failures (pool unknown, switch failed)
- After 3 consecutive failures, promote next best miner
- Send notification on promotion
- Update audit log

**Database Fields:**
- `champion_mode_enabled` (boolean): Enable/disable feature
- `current_champion_miner_id` (integer): Active champion miner

### 5.4 Home Assistant Integration

**Device Control:**
- Turn miners ON/OFF via HA switch entities
- Entity ID format: `switch.miner_{name_lowercase}`
- Examples: `switch.miner_blue`, `switch.miner_bitaxe01`

**Keepalive System:**
- Every 5 minutes, check if HA state matches database
- If mismatch detected, send corrective command
- Prevents drift from manual HA changes

---

## 6. Energy Pricing (Octopus Agile)

### 6.1 API Integration

**Tariff:** AGILE-FLEX-22-11-25  
**Regions:** A-P (UK distribution network operators)  
**Authentication:** None required (public API)

**API Endpoint:**
```
https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25/electricity-tariffs/E-1R-AGILE-FLEX-22-11-25-{REGION}/standard-unit-rates/
```

**Data Format:**
- 30-minute pricing slots
- Fetch 48 hours ahead (~96 slots)
- Auto-refresh every 4 hours

### 6.2 Storage

**Table:** `energy_prices`

**Fields:**
- `region` (A-P)
- `valid_from` (datetime)
- `valid_to` (datetime)
- `price_pence` (numeric)
- `created_at` (datetime)

### 6.3 UI Features

- Current price display (large)
- Next 6 hours forecast chart
- 24-hour timeline with band overlays
- Auto-optimization toggle

---

## 7. UI Architecture

### 7.1 React Application

**Build Process:**
```bash
cd ui-react
npm install
npm run build  # Output: app/ui/static/app/
```

**CRITICAL:** Always run `npm run build` after React changes

**Routing:**
- Single-page application (SPA)
- React Router for client-side routing
- FastAPI serves index.html at `/` (catch-all)

### 7.2 API Integration

**Base URL:** `/api/`

**HTTP Client:** Axios with React Query

**WebSocket:** `/ws/updates` for real-time data

**Authentication:** None (single-user application)

### 7.3 Key Pages

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | Dashboard | Main overview with widgets |
| `/miners` | Miners | Miner list and configuration |
| `/pools` | Pools | Pool management |
| `/agile-strategy` | AgileStrategy | Band configuration + champion mode |
| `/operations` | Operations | Current strategy state |
| `/analytics` | Analytics | Performance charts |
| `/settings` | Settings | Global configuration |

### 7.4 Theme System

**Modes:** Light / Dark (toggle in header)

**Persistence:** `localStorage.theme`

**Implementation:** CSS variables + Tailwind dark: classes

**Champion Mode Theme:** Purple (`#purple-500`) for champion-related UI elements

---

## 8. Database Migrations

### 8.1 Migration System

**File:** `app/core/migrations.py`

**Execution:** Automatic on container startup

**Pattern:**
```python
async with engine.begin() as conn:
    try:
        await conn.execute(text("""
            ALTER TABLE foo ADD COLUMN bar VARCHAR(100)
        """))
        print("✓ Migration completed")
        core_migrations_ran = True  # If core model changed
    except Exception as e:
        print(f"⚠ Migration skipped: {e}")
```

### 8.2 PostgreSQL Compatibility

**Rules:**
- Use `BOOLEAN DEFAULT FALSE` (not `DEFAULT 0`)
- Use `ADD COLUMN IF NOT EXISTS` for idempotency
- Test both PostgreSQL and SQLite syntax
- Use `SERIAL` (PostgreSQL) vs `AUTOINCREMENT` (SQLite) handling

### 8.3 Core Model Warning

If migration modifies core models (AgileStrategy, Miner, etc.), display warning:

```
================================================================================
⚠️  CORE MODEL MIGRATIONS COMPLETED
⚠️  Container restart required for schema changes to take effect
⚠️  Run: docker-compose restart
================================================================================
```

**Why:** SQLAlchemy caches schema on startup; restart ensures fresh state.

---

## 9. Docker & Deployment

### 9.1 Environment Variables

```bash
WEB_PORT=8080          # Web UI port (only exposed port)
TZ=Europe/London       # Timezone for logs/schedules
PUID=1000              # User ID for file permissions
PGID=1000              # Group ID for file permissions
```

**NEVER add more environment variables beyond these four.**

### 9.2 Container Lifecycle

**Startup:**
1. Initialize PostgreSQL (embedded) if first run
2. Start PostgreSQL server (localhost:5432)
3. Load configuration from `/config/config.yaml`
4. Connect to PostgreSQL database
5. Deploy schema from models (`init_db()`)
6. Load pool plugins from `/config/plugins/`
7. Start APScheduler jobs
8. Start FastAPI server (uvicorn)

**Deployment:**
```bash
docker-compose pull    # Get latest image
docker-compose down    # Stop container
docker-compose up -d   # Start with new image
```

**Note:** This is a single-container architecture. PostgreSQL runs inside the same container as the application.

### 9.3 GitHub Actions CI/CD

**Main Workflow:** `.github/workflows/docker-publish.yml`
- Runs on: `ubuntu-latest` (GitHub-hosted runner)
- Triggers: Push to `main`, tags, pull requests
- Outputs: `ghcr.io/renegadeuk/hmm-local:main-{sha}`

**Escape Hatch:** `.github/workflows/escape-hatch.yml`
- Manual trigger only (`workflow_dispatch`)
- Runs on: `[self-hosted, hmm-builder]`
- Optional GHCR push (default: build only)
- Tag format: `escape-{sha}`
- Use when GitHub Actions is down

---

## 10. High-Level Copilot Rules

Copilot MUST:
- Follow FastAPI + PostgreSQL/SQLite + APScheduler + React architecture
- Store ALL persistent data in `/config` (config.yaml, data.db, logs/)
- Use `WEB_PORT` env var (default 8080) - DO NOT add more env vars
- Build React UI with `npm run build` after UI changes
- Implement unified MinerAdapter interface across all miner types
- Use Octopus Agile pricing WITHOUT an API key (public API)
- Write clear, modular, maintainable Python with type hints
- ALWAYS log errors and failures with detailed context
- ALWAYS implement automatic recovery mechanisms
- System MUST self-heal without user intervention
- When failures occur, implement retry logic and reconciliation

**Database:**
- Support both PostgreSQL (primary) and SQLite (fallback)
- Write migrations compatible with both databases
- Use async SQLAlchemy 2.0+ patterns
- Add `core_migrations_ran = True` for core model changes

**React:**
- Use TypeScript for all new components
- Follow existing patterns (React Query, Axios, shadcn/ui)
- Maintain theme consistency (light/dark toggle)
- Test UI changes before committing

---

## 11. Current Feature Status

### 11.1 Completed Features ✅

**Monitoring & Analytics:**
- Health scoring (uptime, temperature, reject rate, hashrate stability)
- Per-miner analytics with time-series charts (6h/24h/3d/7d)
- Custom dashboards with drag-and-drop widgets (GridStack)
- Hardware health predictions (statistical trend analysis)
- CSV export of performance reports

**Energy Optimization:**
- Agile Solo Strategy with price-based bands
- Champion mode for expensive bands (W/TH efficiency selection)
- ROI calculator (real-time profitability)
- Price forecast visualization (24 hours ahead)
- Auto-optimization toggle

**Pool Management:**
- Pool health monitoring (connectivity, response time, reject rate)
- Health scoring (0-100): 40pts reachability, 30pts latency, 30pts rejects
- Intelligent failover (auto-switch on low health)
- Multi-pool strategies (round-robin, load balancing)
- Historical health tracking (30-day retention)

**Hardware:**
- Network auto-discovery (cgminer API, HTTP API)
- Firmware version tracking
- Overclocking profiles (save/load/apply)
- Bulk operations (enable/disable, mode change, pool switch, restart)

**UI/UX:**
- Dark/light theme toggle
- Progressive Web App (PWA) - installable
- FAQ with search and collapsible sections
- Logs page with filtering and pagination
- WCAG AA accessibility compliance

**Advanced:**
- Audit logging for configuration changes
- Telegram and Discord notifications
- Home Assistant integration with keepalive
- WebSocket real-time updates

### 11.2 In Progress 🚧

- None currently

### 11.3 Planned 📋

**Remote Agent Management:**
- Windows/Linux/macOS agent for PC control
- System power management (shutdown, restart, sleep)
- Process management (start/stop applications)
- Wake-on-LAN integration
- Automation: "Shut down idle PCs when electricity is expensive"

**Developer Experience:**
- Plugin system for community miner adapters
- Simulation mode for testing without hardware
- Comprehensive unit/integration tests

---

## 12. Deployment Best Practices

### 12.1 Production Deployment

**Standard Process:**
```bash
# SSH to production server
ssh user@host

# Navigate to compose directory
cd /path/to/hmm-local

# Pull latest image
docker-compose pull

# Stop and remove container
docker-compose down

# Start with new image
docker-compose up -d

# Watch logs for migration success
docker logs -f HMM-Local
```

**Look for:**
```
✓ Added {column_name} column to {table}
```

**If core migrations ran:**
```
================================================================================
⚠️  CORE MODEL MIGRATIONS COMPLETED
⚠️  Container restart required for schema changes to take effect
⚠️  Run: docker-compose restart
================================================================================
```

Then run: `docker-compose restart`

### 12.2 Database Backups

**PostgreSQL:**
```bash
docker exec hmm-pg pg_dump -U hmm hmm > backup_$(date +%Y%m%d).sql
```

**Restore:**
```bash
docker exec -i hmm-pg psql -U hmm hmm < backup_20260202.sql
```

---

**Project Maintainer:** DANVIC.dev  
**Version:** 1.0.0 (Production)  
**Last Updated:** 2 February 2026