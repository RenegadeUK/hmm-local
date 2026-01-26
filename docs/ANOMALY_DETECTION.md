# Anomaly Detection System - Phase A Implementation

## Overview

Implemented **Phase A: Rules + Robust Statistics** for autonomous miner health monitoring and anomaly detection. This system provides deterministic, explainable performance monitoring without LLM hallucinations.

**Status:** ✅ **COMPLETE - DEPLOYED**  
**Version:** 1.0.0  
**Deployed:** January 26, 2026

---

## Architecture

### Components

1. **Database Models** (`app/core/database.py`)
   - `MinerBaseline` - Stores median/MAD baselines per miner/mode
   - `HealthEvent` - Stores health scores, anomaly reasons, timestamps

2. **Anomaly Detection Engine** (`app/core/anomaly_detection.py`)
   - Baseline calculation using median + MAD (robust statistics)
   - Rule-based anomaly detection with configurable thresholds
   - Health scoring (0-100) with weighted metrics
   - Explainable outputs with reason codes

3. **Scheduler Jobs** (`app/core/scheduler.py`)
   - **Hourly**: Update baselines (recalculate median/MAD from 24h/7d data)
   - **Every 5 minutes**: Check all miner health and log events

4. **REST API** (`app/api/health.py`)
   - `GET /api/health/{miner_id}` - Latest health status
   - `GET /api/health/{miner_id}/history` - Historical events
   - `GET /api/health/all` - All miners summary
   - `GET /api/health/baselines/{miner_id}` - View baselines
   - `POST /api/health/baselines/update` - Manual baseline update
   - `POST /api/health/check` - Manual health check trigger

---

## How It Works

### 1. Baseline Calculation (Robust Statistics)

Uses **median + MAD** (Median Absolute Deviation) instead of mean + standard deviation to handle outliers:

```python
median = statistics.median(values)
deviations = [abs(x - median) for x in values]
mad = statistics.median(deviations)
```

**Why MAD?**
- Resistant to outliers (e.g., brief power spikes)
- More robust than standard deviation
- Better for real-world mining data

### 2. Per-Miner, Per-Mode Baselines

Calculates baselines separately for each:
- **Miner ID** - Each miner has unique characteristics
- **Operating Mode** - low/med/high/eco/standard/turbo/oc

**Metrics Tracked:**
- `hashrate_mean` - Average hashrate (GH/s or TH/s)
- `power_mean` - Average power consumption (W)
- `w_per_th` - Efficiency (W/TH)
- `temp_mean` - Average temperature (°C)
- `reject_rate` - Share reject rate (%)

**Timeframes:**
- 24-hour baseline (short-term)
- 7-day baseline (long-term)

### 3. Rule-Based Anomaly Detection

Five deterministic rules with configurable thresholds:

| Rule | Threshold | Severity | Example |
|------|-----------|----------|---------|
| **HASHRATE_DROP** | >15% below baseline | 🔴 High | 100 GH/s → 80 GH/s |
| **EFFICIENCY_DRIFT** | >20% worse W/TH | 🟠 Medium | 30 W/TH → 37 W/TH |
| **TEMP_HIGH** | >10°C above baseline | 🟡 Medium | 65°C → 77°C |
| **REJECT_RATE_SPIKE** | >5% increase | 🟡 Medium | 1% → 7% |
| **POWER_SPIKE** | >15% above baseline | 🟢 Low | 100W → 120W |

### 4. Health Scoring

Weighted average (0-100):

| Metric | Weight | Calculation |
|--------|--------|-------------|
| Hashrate | 30% | 100 - (drop_percent × 3) |
| Efficiency | 25% | 100 - (drift_percent × 2.5) |
| Temperature | 20% | 100 - (temp_excess × 2) |
| Reject Rate | 15% | 100 - (reject_increase × 15) |
| Power | 10% | 100 - (power_excess × 1) |

**Score Interpretation:**
- **90-100**: ✅ Excellent health
- **75-89**: 🟢 Good health
- **60-74**: 🟡 Fair health (monitor)
- **40-59**: 🟠 Poor health (investigate)
- **0-39**: 🔴 Critical health (urgent action)

---

## Database Schema

### MinerBaseline Table

```sql
CREATE TABLE miner_baselines (
    id TEXT PRIMARY KEY,
    miner_id TEXT NOT NULL,
    mode TEXT NOT NULL,  -- "low", "med", "high", "eco", etc.
    metric_name TEXT NOT NULL,  -- "hashrate_mean", "power_mean", etc.
    median_value REAL,
    mad_value REAL,  -- Median Absolute Deviation
    sample_count INTEGER,
    window TEXT NOT NULL,  -- "24h" or "7d"
    computed_at TIMESTAMP,
    UNIQUE(miner_id, mode, metric_name, window)
);

CREATE INDEX idx_miner_baselines_lookup 
ON miner_baselines(miner_id, mode, metric_name);
```

### HealthEvent Table

```sql
CREATE TABLE health_events (
    id TEXT PRIMARY KEY,
    miner_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    health_score REAL NOT NULL,  -- 0-100
    reasons TEXT,  -- JSON array of reason objects
    anomaly_score REAL,  -- Reserved for Phase B (Isolation Forest)
    FOREIGN KEY(miner_id) REFERENCES miners(id)
);

CREATE INDEX idx_health_events_miner_time 
ON health_events(miner_id, timestamp DESC);
```

**Reason Object Structure:**
```json
{
  "type": "HASHRATE_DROP",
  "severity": "high",
  "current": 82.5,
  "expected": 105.2,
  "difference": -21.6,
  "threshold": 15.78,
  "message": "Hashrate dropped 20.5% (current: 82.50 GH/s, expected: 105.20 GH/s)"
}
```

---

## API Endpoints

### Get Latest Health Status
```bash
GET /api/health/{miner_id}

Response:
{
  "miner_id": "abc123",
  "health_score": 78.5,
  "timestamp": "2026-01-26T22:17:51Z",
  "reasons": [
    {
      "type": "TEMP_HIGH",
      "severity": "medium",
      "current": 78.2,
      "expected": 65.5,
      "difference": 12.7,
      "message": "Temperature 12.7°C above baseline"
    }
  ]
}
```

### Get Health History
```bash
GET /api/health/{miner_id}/history?hours=24&limit=100

Response:
{
  "miner_id": "abc123",
  "events": [
    {
      "timestamp": "2026-01-26T22:15:00Z",
      "health_score": 92.3,
      "reasons": []
    },
    {
      "timestamp": "2026-01-26T22:10:00Z",
      "health_score": 65.8,
      "reasons": [{"type": "HASHRATE_DROP", ...}]
    }
  ]
}
```

### Get All Miners Health Summary
```bash
GET /api/health/all

Response:
{
  "summary": {
    "total_miners": 5,
    "healthy": 3,
    "warning": 1,
    "critical": 1
  },
  "miners": [
    {
      "miner_id": "abc123",
      "name": "Avalon Nano 3",
      "health_score": 95.2,
      "status": "healthy"
    },
    {
      "miner_id": "def456",
      "name": "Bitaxe 601",
      "health_score": 42.1,
      "status": "critical",
      "reasons": [...]
    }
  ]
}
```

### View Baselines
```bash
GET /api/health/baselines/{miner_id}?mode=high

Response:
{
  "miner_id": "abc123",
  "mode": "high",
  "baselines": {
    "24h": {
      "hashrate_mean": {"median": 105.2, "mad": 3.4, "samples": 288},
      "power_mean": {"median": 32.1, "mad": 1.2, "samples": 288},
      "w_per_th": {"median": 30.5, "mad": 0.8, "samples": 288},
      "temp_mean": {"median": 65.5, "mad": 2.1, "samples": 288},
      "reject_rate": {"median": 1.2, "mad": 0.3, "samples": 288}
    },
    "7d": {...}
  }
}
```

### Manual Baseline Update
```bash
POST /api/health/baselines/update?miner_id=abc123

Response:
{
  "success": true,
  "message": "Updated baselines for 1 miners",
  "updated_miners": ["abc123"]
}
```

### Manual Health Check
```bash
POST /api/health/check?miner_id=abc123

Response:
{
  "success": true,
  "message": "Health check completed for 1 miners",
  "results": [
    {
      "miner_id": "abc123",
      "health_score": 78.5,
      "reasons": [...]
    }
  ]
}
```

---

## Scheduler Jobs

### Update Miner Baselines (Hourly)
```python
@scheduler.scheduled_job("interval", hours=1, id="update_miner_baselines")
async def _update_miner_baselines():
    """Recalculate baselines using latest 24h/7d telemetry"""
    await update_baselines_for_all_miners()
```

**What it does:**
1. Query all enrolled miners
2. For each miner + mode combination:
   - Fetch last 24 hours of telemetry
   - Fetch last 7 days of telemetry
   - Calculate median + MAD for each metric
   - Store in `miner_baselines` table

**Runs at:** Every hour on the hour  
**Next run:** After application start + 1 hour

### Check Miner Health (Every 5 Minutes)
```python
@scheduler.scheduled_job("interval", minutes=5, id="check_miner_health")
async def _check_miner_health():
    """Detect anomalies and log health events"""
    await check_all_miners_health()
```

**What it does:**
1. Query all enrolled miners
2. Get latest telemetry (last 5 minutes)
3. Load baselines from database
4. Apply 5 detection rules
5. Calculate health score
6. Store event in `health_events` table

**Runs at:** Every 5 minutes  
**Next run:** After application start + 5 minutes

---

## Configuration

Currently using **hardcoded thresholds** (Phase A). These will become configurable in Phase B:

```python
# In anomaly_detection.py
HASHRATE_DROP_THRESHOLD = 0.15  # 15%
EFFICIENCY_DRIFT_THRESHOLD = 0.20  # 20%
TEMP_EXCESS_THRESHOLD = 10.0  # +10°C
REJECT_RATE_THRESHOLD = 0.05  # +5%
POWER_SPIKE_THRESHOLD = 0.15  # 15%
```

---

## Testing

### Manual Test: Update Baselines
```bash
curl -X POST http://localhost:8080/api/health/baselines/update
```

**Expected:**
- Calculates median + MAD from telemetry
- Stores baselines in database
- Returns success message

### Manual Test: Health Check
```bash
curl -X POST http://localhost:8080/api/health/check
```

**Expected:**
- Evaluates current miner state vs baselines
- Generates health score
- Returns anomaly reasons (if any)

### Verify Scheduler Logs
```bash
docker-compose logs -f | grep -E "update_miner_baselines|check_miner_health"
```

**Expected output every hour:**
```
apscheduler.executors.default - INFO - Running job "Update miner performance baselines"
```

**Expected output every 5 minutes:**
```
apscheduler.executors.default - INFO - Running job "Check miner health and detect anomalies"
```

---

## Future Enhancements (Phase B)

### Isolation Forest ML Model
- Train one model per miner using historical telemetry
- Generate `anomaly_score` (0.0-1.0) as secondary signal
- Combine with rule-based detection for hybrid approach
- Store models in filesystem or database

### Configuration UI
- Make thresholds configurable per miner type
- Add sensitivity slider (strict/normal/relaxed)
- Allow disabling specific rules per miner

### Degradation Detection
- Linear regression on historical metrics (30d+)
- Detect gradual hashrate decline over weeks
- Predict hardware failure timeline

### Alert Integration
- Connect health events to notification system
- Send alerts for critical health scores (<40)
- Escalate if health doesn't improve within X hours

### Auto-Remediation
- Trigger actions based on health score:
  - Score <60: Reduce mode to prevent damage
  - Score <40: Restart miner
  - Score <20: Disable miner, send critical alert
- Log all automated actions in audit log

---

## Deployment Verification

✅ **Application started successfully**  
✅ **40 scheduled jobs running**  
✅ **Health endpoints registered** (`/api/health/*`)  
✅ **Database tables created** (`miner_baselines`, `health_events`)  
✅ **Scheduler jobs added:**
  - "Update miner performance baselines" (hourly)
  - "Check miner health and detect anomalies" (every 5 minutes)

---

## Known Limitations (Phase A)

1. **No ML yet** - Pure rule-based detection (Phase B will add Isolation Forest)
2. **Hardcoded thresholds** - Not configurable per miner type yet
3. **No UI** - API-only, no dashboard visualization yet
4. **No alerts** - Health events logged but not sent to notifications
5. **No auto-remediation** - Detection only, no automated actions yet

---

## Success Criteria (Phase A)

- [x] Database models created (MinerBaseline, HealthEvent)
- [x] Baseline calculation using median + MAD
- [x] Per-miner, per-mode baseline storage
- [x] Five deterministic anomaly detection rules
- [x] Health scoring (0-100) with weighted metrics
- [x] Explainable reason codes
- [x] Scheduler jobs (hourly baselines, 5-min health checks)
- [x] REST API endpoints for health monitoring
- [x] Application deployed and running

---

**Next Steps:**
1. Wait 1 hour for first baseline calculation
2. Monitor health check logs after 5 minutes
3. Test API endpoints with real miner data
4. Create UI dashboard for health visualization
5. Integrate with notification system

**Developer:** DANVIC.dev  
**Documentation:** January 26, 2026
