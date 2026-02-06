# First Run Deployment Strategy

**Date:** 6 February 2026  
**Status:** ✅ Implemented

## Overview

The container now includes **bundled drivers and example pool configs** that deploy automatically to `/config` on first run. This ensures users have a working system out of the box without needing to manually create pool configurations.

## Architecture

### Bundled Config Structure

```
/app/bundled_config/
├── drivers/              # Complete, ready-to-use drivers
│   ├── README.md
│   ├── TEMPLATE_driver.py
│   ├── solopool_driver.py
│   ├── braiins_driver.py
│   └── mmfp_driver.py
└── pools/                # Example pool configurations
    ├── README.md
    ├── solopool-dgb-eu1.yaml.example
    ├── solopool-btc-eu3.yaml.example
    ├── solopool-bch-eu2.yaml.example
    ├── braiins-btc-eu.yaml.example
    └── ... (more examples)
```

### Deployment Flow

**On First Run:**
```bash
1. Container starts
2. Entrypoint checks: if [ ! -d "/config/drivers" ]
3. If missing: cp -r /app/bundled_config/drivers /config/
4. Same for pools directory
5. App loads drivers from /config/drivers
6. User activates pools by renaming .example files
```

**On Subsequent Runs:**
```bash
1. Container starts
2. Directories exist, skip deployment
3. Load drivers and pools from /config
4. User configurations preserved
```

## Implementation Details

### 1. Dockerfile Changes

```dockerfile
# Copy bundled drivers and example pool configs
COPY bundled_config/ /app/bundled_config/
```

**Result:** Bundled configs become part of the Docker image (immutable).

### 2. Entrypoint.sh Changes

```bash
# Deploy bundled drivers and example pool configs on first run
if [ ! -d "/config/drivers" ]; then
    echo "📦 Deploying bundled pool drivers..."
    cp -r /app/bundled_config/drivers /config/
    echo "✅ Drivers deployed to /config/drivers"
fi

if [ ! -d "/config/pools" ]; then
    echo "📦 Deploying example pool configurations..."
    cp -r /app/bundled_config/pools /config/
    echo "✅ Example pool configs deployed to /config/pools"
    echo "ℹ️  Rename .yaml.example files to .yaml to activate pools"
fi
```

**Result:** Automatic deployment only if directories don't exist.

### 3. Pool Loader (No Changes)

```python
# Already loads from /config only
pool_loader = init_pool_loader("/config")
```

**Result:** Single source of truth for pool configurations.

## User Workflow

### Fresh Install

1. **Start Container:**
   ```bash
   docker-compose up -d
   ```

2. **System Deploys Configs:**
   ```
   📦 Deploying bundled pool drivers...
   ✅ Drivers deployed to /config/drivers
   📦 Deploying example pool configurations...
   ✅ Example pool configs deployed to /config/pools
   ```

3. **Activate Pools:**
   ```bash
   cd /config/pools
   cp solopool-dgb-eu1.yaml.example solopool-dgb-eu1.yaml
   # Edit with your wallet address
   nano solopool-dgb-eu1.yaml
   ```

4. **Restart to Load:**
   ```bash
   docker-compose restart
   ```

### Adding Custom Pools

1. **Copy Template:**
   ```bash
   cd /config/pools
   cp solopool-dgb-eu1.yaml.example my-custom-pool.yaml
   ```

2. **Edit Configuration:**
   ```yaml
   driver: solopool
   display_name: "My Custom Pool"
   url: pool.example.com
   port: 3333
   coin: DGB
   # ... etc
   ```

3. **Restart Container:**
   ```bash
   docker-compose restart
   ```

### Creating Custom Drivers

1. **Copy Template:**
   ```bash
   cd /config/drivers
   cp TEMPLATE_driver.py my_pool_driver.py
   ```

2. **Implement Driver:**
   ```python
   class MyPoolDriver(BasePoolIntegration):
       driver_type = "mypool"
       # ... implement methods
   ```

3. **Create Pool Config:**
   ```yaml
   driver: mypool  # References my_pool_driver.py
   display_name: "My Pool"
   # ... etc
   ```

## Benefits

✅ **Zero Configuration Required:** System works out of the box  
✅ **User Configs Preserved:** Never overwrites existing configurations  
✅ **Clear Examples:** All major pool types pre-configured  
✅ **Extensible:** Users can add drivers and pools without rebuilding image  
✅ **Git-Safe:** Dev configs excluded via `.gitignore`, examples bundled  

## Security Considerations

### What's Bundled (Safe)

✅ **Pool drivers** - Pure Python code, no secrets  
✅ **Example pool configs** - Generic connection details only  
✅ **READMEs** - Documentation

### What's NOT Bundled (User-Provided)

❌ **Wallet addresses** - Configured by user in activated `.yaml` files  
❌ **API tokens** - Stored in `/config/config.yaml`  
❌ **Personal data** - Never included in image

### .gitignore Protection

```gitignore
# Excludes user configs from git
config/
```

**Result:** Dev configs with real wallet addresses never committed.

## File Naming Convention

| Pattern | Purpose | Loaded by App? |
|---------|---------|----------------|
| `*.yaml` | Active pool config | ✅ Yes |
| `*.yaml.example` | Example/template | ❌ No |
| `README.md` | Documentation | ❌ No |
| `*_driver.py` | Pool driver | ✅ Yes |
| `TEMPLATE_*.py` | Template code | ❌ No |

## Logging Examples

### First Run (Fresh Install)

```
🐘 Setting up PostgreSQL...
📁 Initializing PostgreSQL data directory...
📦 Deploying bundled pool drivers...
✅ Drivers deployed to /config/drivers
📦 Deploying example pool configurations...
✅ Example pool configs deployed to /config/pools
ℹ️  Rename .yaml.example files to .yaml to activate pools
🚀 Starting Home Miner Manager...
🔌 Loading pool drivers and configs...
Loading pool drivers from /config/drivers
✅ Loaded driver: solopool from solopool_driver.py
✅ Loaded driver: braiins from braiins_driver.py
✅ Loaded driver: mmfp from mmfp_driver.py
Loaded 3 pool drivers: ['solopool', 'braiins', 'mmfp']
Loading pool configs from /config/pools
Loaded 0 pool configs
```

### Subsequent Runs (Existing Config)

```
🐘 Setting up PostgreSQL...
✅ PostgreSQL data directory exists
🚀 Starting PostgreSQL...
✅ PostgreSQL is ready
🚀 Starting Home Miner Manager...
🔌 Loading pool drivers and configs...
Loading pool drivers from /config/drivers
✅ Loaded driver: solopool from solopool_driver.py
✅ Loaded driver: braiins from braiins_driver.py
✅ Loaded driver: mmfp from mmfp_driver.py
Loaded 3 pool drivers: ['solopool', 'braiins', 'mmfp']
Loading pool configs from /config/pools
✅ Loaded pool config: solopool-dgb-eu1 (driver: solopool)
✅ Loaded pool config: braiins-btc-eu (driver: braiins)
Loaded 2 pool configs
```

## Related Files

- [bundled_config/drivers/](../bundled_config/drivers/) - Bundled pool drivers
- [bundled_config/pools/](../bundled_config/pools/) - Example pool configs
- [Dockerfile](../Dockerfile) - Image build with bundled configs
- [entrypoint.sh](../entrypoint.sh) - First-run deployment logic
- [app/core/pool_loader.py](../app/core/pool_loader.py) - Runtime loader

## Future Enhancements

- **Version Updates:** Auto-update bundled drivers from `/app/bundled_config` on new releases
- **Web UI:** Pool activation interface (no SSH needed)
- **Validation:** Pre-check pool configs before activation
- **Marketplace:** Community driver repository

---

**Status:** Production Ready  
**Breaking Changes:** None  
**Migration Required:** None
