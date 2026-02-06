# Pool Driver & Config Architecture - Implementation Complete

## 🎉 New Architecture Summary

The pool system has been completely rearchitected to use a **driver + config file** approach where everything lives in `/config/`.

### Architecture Overview

```
/config/
├── config.yaml           # User secrets (wallet addresses, API keys)
├── drivers/              # Python drivers (plugins)
│   └── solopool_driver.py
└── pools/                # YAML pool configurations
    ├── solopool-dgb-eu1.yaml
    ├── solopool-dgb-us1.yaml
    ├── solopool-bch-eu2.yaml
    ├── solopool-bch-us1.yaml
    ├── solopool-btc-eu3.yaml
    └── solopool-bc2-eu3.yaml
```

## What Works Right Now

✅ **Driver loading** - System scans `/config/drivers/` for `*_driver.py` files  
✅ **Pool config loading** - System scans `/config/pools/` for `*.yaml` files  
✅ **Validation** - Pool configs rejected if driver doesn't exist  
✅ **API** - `/api/pool-templates` returns all valid pool configs  
✅ **UI** - React PoolFormDialog fetches and displays pools dynamically  

**Current Status:**
- 1 driver loaded (`solopool`)  
- 6 pool configs loaded (all solopool variants)  
- 2 pool configs rejected (braiins, mmfp - drivers don't exist yet)

## How to Add a New Pool

1. **If driver doesn't exist**, create it in `/config/drivers/`:
   ```bash
   cp /config/drivers/solopool_driver.py /config/drivers/mynewpool_driver.py
   ```
   Edit the file and set `driver_type = "mynewpool"`

2. **Create pool config** in `/config/pools/`:
   ```yaml
   # mynewpool-btc-us.yaml
   driver: mynewpool
   display_name: "My New Pool BTC (US)"
   url: pool.mynewpool.com
   port: 3333
   coin: BTC
   region: US
   mining_model: pool
   fee_percent: 1.5
   requires_auth: true
   supports_shares: true
   supports_earnings: true
   supports_balance: true
   description: "My awesome pool"
   ```

3. **Restart container**:
   ```bash
   docker-compose restart miner-controller
   ```

4. **Verify it loaded**:
   ```bash
   docker logs v0-miner-controller 2>&1 | grep "✅ Loaded pool config"
   ```

5. **Test in UI**: Open http://localhost:8080/app/pools and click "Add Pool"

## Next Steps

###  Copy More Drivers

The existing plugins in `app/integrations/pools/` need to be copied to `/config/drivers/`:

```bash
# Copy Braiins driver
cp app/integrations/pools/braiins_plugin.py config/drivers/braiins_driver.py

# Copy MMFP driver  
cp app/integrations/pools/mmfp_plugin.py config/drivers/mmfp_driver.py
```

Then restart - the braiins and mmfp pool configs will load automatically!

### 2. Update User Secrets

The `config.yaml` should ONLY contain user-specific secrets:

```yaml
# User secrets (NOT in pool configs)
wallets:
  dgb: "your_dgb_address_here"
  bch: "your_bch_address_here"
  btc: "your_btc_address_here"

api_keys:
  braiins: "your_braiins_api_key"
```

Then pool configs reference these via the driver:
- Driver reads from `config.yaml` when needed
- Pool config just defines connection details

### 3. Remove Old System

Once all pools are migrated:
- Delete `app/integrations/pools/` (old hardcoded plugins)
- Delete `app/integrations/pool_registry.py` (old registry system)
- Update documentation

## Benefits of New Architecture

✅ **User-extensible** - Drop in new drivers/configs without code changes  
✅ **Versionable** - Pool configs are text files (easy to share/backup)  
✅ **Modular** - Drivers are independent Python modules  
✅ **Clean separation** - Code (drivers) vs data (configs) vs secrets (config.yaml)  
✅ **Discovery** - System auto-loads everything on startup  
✅ **Validation** - Rejects invalid configs early with clear errors  

## Dashboard Tile Integration

### Overview

Pool drivers can optionally implement `get_dashboard_data()` to provide real-time stats for dashboard tiles. This method returns user-specific mining data (hashrate, shares, workers, etc.) for display on the main dashboard.

### Required Method

```python
async def get_dashboard_data(
    self,
    url: str,
    coin: str,
    username: Optional[str] = None,
    **kwargs
) -> Optional[DashboardTileData]:
    """
    Fetch dashboard tile data for a specific pool/coin/user.
    
    Args:
        url: Pool URL
        coin: Coin symbol (BTC, DGB, BCH, etc.)
        username: User's wallet address or username
        **kwargs: Additional config from pool_config
    
    Returns:
        DashboardTileData with user-specific stats, or None on error
    """
```

### DashboardTileData Fields

The `DashboardTileData` model (from `app/integrations/base_pool.py`) includes:

**Tile 1: Health Status**
- `health_status` (bool) - Pool reachability
- `health_message` (str) - Error message if unhealthy
- `response_time_ms` (float) - API latency

**Tile 2: Network Stats**
- `network_difficulty` (float) - Network difficulty
- `pool_hashrate` (float) - **USER's hashrate in TH/s** (NOT pool-wide!)
- `estimated_time_to_block` (str) - Estimated time to find block
- `pool_percentage` (float) - Pool's network percentage
- `active_workers` (int) - Number of active workers for this user

**Tile 3: Shares**
- `shares_valid` (int) - Valid shares (24h or cumulative)
- `shares_invalid` (int) - Invalid shares
- `shares_stale` (int) - Stale shares
- `reject_rate` (float) - Rejection percentage

**Tile 4: Blocks/Earnings**
- `blocks_found_24h` (int) - Blocks found in 24 hours
- `estimated_earnings_24h` (float) - Estimated 24h earnings
- `currency` (str) - Currency symbol
- `confirmed_balance` (float) - Confirmed balance
- `pending_balance` (float) - Pending balance

### Implementation Example (Solopool)

```python
async def get_dashboard_data(self, url, coin, username=None, **kwargs):
    api_base = self.API_BASES.get(coin.upper())
    
    # Fetch network stats and user stats in parallel
    async with aiohttp.ClientSession() as session:
        tasks = [
            session.get(f"{api_base}/stats"),  # Network stats
            session.get(f"{api_base}/accounts/{username}")  # USER stats
        ]
        responses = await asyncio.gather(*tasks)
        
        stats_data = await responses[0].json()
        worker_data = await responses[1].json()
        
        # Extract USER hashrate (convert H/s to TH/s)
        user_hashrate_hs = worker_data.get("currentHashrate", 0)
        user_hashrate_ths = user_hashrate_hs / 1_000_000_000_000
        
        # Extract shares from workers (note: camelCase field names)
        workers = worker_data.get("workers", {})
        total_valid = sum(w.get("sharesValid", 0) for w in workers.values())
        
        return DashboardTileData(
            health_status=True,
            pool_hashrate=user_hashrate_ths,  # USER's hashrate!
            active_workers=worker_data.get("workersOnline", 0),
            shares_valid=total_valid,
            network_difficulty=stats_data.get("networkDifficulty"),
            currency=coin.upper()
        )
```

### Key Implementation Notes

1. **USER-SPECIFIC DATA**: `pool_hashrate` should be the USER's hashrate, NOT the pool's total hashrate
2. **Unit Conversion**: Most APIs return hashrate in H/s - convert to TH/s by dividing by 1,000,000,000,000
3. **Field Name Variations**: Check API docs for exact field names (e.g., Solopool uses camelCase: `sharesValid` not `shares_valid`)
4. **Active Workers**: Count of online workers for this user (from `workersOnline` or similar field)
5. **Error Handling**: Return `DashboardTileData(health_status=False, health_message="error")` on failure
6. **Caching**: Dashboard service caches results for 30 seconds - no need to implement caching in driver

### Dashboard Integration

Once implemented, pool tiles automatically appear on the dashboard showing:
- **Pool Hashrate**: User's mining hashrate
- **Shares (24h)**: Valid/invalid share counts
- Additional stats as available

The dashboard calls `get_dashboard_data()` every 30 seconds for each configured pool.

## Technical Details

**Core Components:**
- `app/core/pool_loader.py` - Driver/config loader
- `app/api/pool_templates.py` - Updated to use pool_loader
- `app/main.py` - Initializes pool_loader on startup
- `app/core/dashboard_pool_service.py` - Orchestrates dashboard data collection
- `app/api/dashboard.py` - Serves dashboard tile data to UI

**Startup Logs:**
```
🔌 Loading pool drivers and configs...
   Loading pool drivers from /config/drivers
   ✅ Loaded driver: solopool from solopool_driver.py
   Loaded 1 pool drivers: ['solopool']
   Loading pool configs from /config/pools
   ❌ Pool config braiins-btc-eu references unknown driver: braiins
   ✅ Loaded pool config: solopool-dgb-eu1 (driver: solopool)
   ... (6 total)
   Loaded 6 pool configs
✅ Loaded 1 driver(s) and 6 pool config(s)
```

## Testing

**Check API:**
```bash
curl http://localhost:8080/api/pool-templates | jq 'length'
# Should return: 6

curl http://localhost:8080/api/pool-templates | jq '.[0]'
# Should show solopool pool details
```

**Check UI:**
1. Open http://localhost:8080/app/pools
2. Click "Add Pool"  
3. See dropdown with 5 groups (Solopool.org · DGB, etc.)
4. Each group has region options (EU1, US1, etc.)

---

**Status:** ✅ Architecture fully implemented and working  
**Date:** February 5, 2026  
**Next:** Copy remaining drivers (braiins, mmfp) to enable all pool configs
