# Monero Solo Mining Feature - Implementation Roadmap

## Overview
Add comprehensive solo Monero mining support with effort tracking, wallet reward monitoring, and detailed analytics dashboard.

**Key Features:**
- XMRig worker tracking and hashrate aggregation
- Network difficulty and effort calculation
- Wallet RPC integration for reward tracking
- Dashboard tiles (4 summary stats)
- Detailed analytics page (comprehensive metrics and charts)

---

## Phase 1: Database & Core Infrastructure

### Objective
Build the foundation for Monero solo mining data storage and RPC communication.

### Tasks

#### 1.1 Database Models
- [ ] Create `MoneroSoloSettings` table
  - `enabled: bool` - Feature toggle
  - `wallet_rpc_ip: str` - Wallet RPC IP address
  - `wallet_rpc_port: int` - Wallet RPC port (default: 18083)
  - `wallet_rpc_user: Optional[str]` - Optional auth username
  - `wallet_rpc_pass: Optional[str]` - Optional auth password
  - `wallet_address: Optional[str]` - Cached wallet address
  - `last_sync: datetime` - Last successful wallet sync
  - `created_at: datetime`
  - `updated_at: datetime`

- [ ] Create `MoneroSoloEffort` table
  - `id: int` - Primary key
  - `pool_id: int` - Foreign key to pools table
  - `total_hashes: bigint` - Accumulated hashes this round
  - `round_start_time: datetime` - When round started
  - `last_block_height: int` - Last known network block
  - `last_reset: datetime` - When effort counter last reset
  - `created_at: datetime`
  - `updated_at: datetime`

- [ ] Create `MoneroBlock` table
  - `id: int` - Primary key
  - `block_height: int` - Network block height
  - `block_hash: str` - Block hash
  - `timestamp: datetime` - When block was found
  - `reward_atomic: bigint` - Reward in atomic units
  - `reward_xmr: float` - Reward in XMR (for display)
  - `effort_percent: float` - Luck percentage when found
  - `total_hashes: bigint` - Hashes attempted in round
  - `difficulty: bigint` - Network difficulty at time
  - `pool_id: int` - Which pool found it
  - `created_at: datetime`

- [ ] Create `MoneroWalletTransaction` table
  - `id: int` - Primary key
  - `tx_hash: str` - Transaction hash (unique)
  - `block_height: int` - Block height
  - `amount_atomic: bigint` - Amount in atomic units
  - `amount_xmr: float` - Amount in XMR
  - `timestamp: datetime` - Transaction timestamp
  - `tx_type: str` - Transaction type ("in")
  - `is_block_reward: bool` - If this is a mining reward
  - `created_at: datetime`

- [ ] Add database migration in `app/core/migrations.py`

#### 1.2 Monero Node RPC Service
- [ ] Create `app/core/monero_node.py`
  - `MoneroNodeRPC` class
  - `async def get_info()` - Network height, difficulty, target
  - `async def get_last_block_header()` - Latest block info
  - `async def get_block_header_by_height(height)` - Specific block
  - `async def json_rpc_request(method, params)` - Base RPC method
  - Error handling and retry logic
  - Connection timeout configuration

#### 1.3 Monero Wallet RPC Service
- [ ] Create `app/core/monero_wallet.py`
  - `MoneroWalletRPC` class
  - `async def get_address()` - Get primary wallet address
  - `async def get_balance()` - Get current balance
  - `async def get_transfers(filter_by_time)` - Get incoming transactions
  - `async def get_transfer_by_txid(txid)` - Get specific transaction
  - `async def json_rpc_request(method, params)` - Base RPC method
  - Error handling for locked wallet, connection issues
  - Authentication support (user/pass)

#### 1.4 Core Logic Service
- [ ] Create `app/core/monero_solo.py`
  - `MoneroSoloService` class
  - `async def update_effort()` - Calculate current round effort
  - `async def detect_new_blocks()` - Check for blocks found
  - `async def sync_wallet_transactions()` - Pull latest transactions
  - `async def get_active_workers()` - Find XMRig miners on solo pools
  - `async def aggregate_hashrate()` - Sum hashrate from all miners
  - `async def calculate_expected_time()` - Time to block estimate
  - `async def reset_effort_counter()` - Reset on block found

### Outcomes
- ✅ Complete database schema for all Monero solo mining data
- ✅ Working RPC communication with Monero node
- ✅ Working RPC communication with wallet
- ✅ Core service methods for data processing
- ✅ Migrations applied successfully

### Testing

#### Unit Tests
- [ ] Test `MoneroNodeRPC` methods with mock responses
- [ ] Test `MoneroWalletRPC` methods with mock responses
- [ ] Test effort calculation formulas
- [ ] Test expected time calculations
- [ ] Test hashrate aggregation logic

#### Integration Tests
- [ ] Test database models create/read/update
- [ ] Test RPC connection with real test node
- [ ] Test RPC connection with real test wallet
- [ ] Test transaction parsing and storage
- [ ] Test effort tracking across rounds

#### Manual Testing
- [ ] Verify migration runs without errors
- [ ] Verify RPC connections to local node
- [ ] Verify RPC connections to local wallet
- [ ] Check database tables created correctly
- [ ] Validate data types and constraints

---

## Phase 2: Settings UI & Configuration

### Objective
Create user interface for configuring Monero solo mining settings.

### Tasks

#### 2.1 Settings API Endpoints
- [ ] Create `app/api/monero_solo.py`
  - `GET /api/settings/monero-solo` - Get current settings
  - `PUT /api/settings/monero-solo` - Update settings
  - `POST /api/settings/monero-solo/test-node` - Test node connection
  - `POST /api/settings/monero-solo/test-wallet` - Test wallet connection
  - `GET /api/settings/monero-solo/stats` - Get dashboard stats
  - Response models with Pydantic validation

#### 2.2 Settings UI Routes
- [ ] Add route in `app/ui/routes.py`
  - `@router.get("/settings/monero-solo")` - Settings page
  - Breadcrumbs navigation
  - Pass current settings to template

#### 2.3 Settings Template
- [ ] Create `app/ui/templates/settings/monero_solo.html`
  - Enable/disable toggle
  - Wallet RPC configuration form
    - IP address input
    - Port input (default 18083)
    - Username input (optional)
    - Password input (optional)
  - Test connection buttons (Node + Wallet)
  - Status indicators (connected/failed)
  - Wallet address display (fetched after connection)
  - Save button
  - Help text and documentation links

#### 2.4 Settings Navigation
- [ ] Update `app/ui/templates/base.html`
  - Add "Monero Solo" link under Settings section
  - Add icon (Monero logo or mining icon)

### Outcomes
- ✅ Fully functional settings page
- ✅ User can enable/disable feature
- ✅ User can configure wallet RPC
- ✅ Test buttons validate connectivity
- ✅ Settings persist to database
- ✅ Clear error messages on failures

### Testing

#### Unit Tests
- [ ] Test API endpoint request/response schemas
- [ ] Test settings validation logic
- [ ] Test connection test endpoints

#### Integration Tests
- [ ] Test settings save/retrieve flow
- [ ] Test connection tests with real RPC
- [ ] Test error handling for invalid settings

#### Manual Testing
- [ ] Navigate to settings page
- [ ] Enable Monero solo mining
- [ ] Enter wallet RPC details
- [ ] Click "Test Wallet Connection"
  - Should show success/failure status
  - Should fetch and display wallet address
- [ ] Save settings
- [ ] Reload page - settings should persist
- [ ] Test with invalid credentials - should show errors
- [ ] Disable feature - dashboard tiles should not appear

---

## Phase 3: Dashboard Integration (Main Dashboard Tiles)

### Objective
Add 4-tile summary on main dashboard showing solo mining stats.

### Tasks

#### 3.1 Dashboard API Endpoints
- [ ] Update `app/api/monero_solo.py`
  - `GET /api/settings/monero-solo/stats` implementation
    - Return: enabled status
    - Return: total workers count
    - Return: combined hashrate
    - Return: current effort percentage
    - Return: today's reward (XMR + GBP)
    - Return: all-time reward (XMR + GBP)
    - Return: shares submitted
    - Return: last block time
    - Return: expected time to block

#### 3.2 Dashboard Template Updates
- [ ] Update `app/ui/templates/dashboard.html`
  - Add `<div id="monero-solo-stats">` section
  - Add 4 stat tiles:
    1. Workers & Hashrate tile
    2. Current Round Effort tile (with luck color coding)
    3. Today's Reward tile (XMR + GBP)
    4. All-time Reward tile (XMR + GBP)
  - Add Monero logo/icon styling
  - Add time since last share indicator
  - Add expected time to block display
  - Hide section if disabled or no workers

#### 3.3 Dashboard JavaScript
- [ ] Add `loadMoneroSoloStats()` function
  - Fetch stats from API
  - Check if enabled and has workers
  - Render tiles dynamically
  - Format hashrate (H/s, KH/s, MH/s)
  - Format XMR values (6 decimals)
  - Format GBP values (2 decimals)
  - Color code effort (green <100%, orange 100-150%, red >150%)
  - Handle errors gracefully
- [ ] Call on page load
- [ ] Add to refresh cycle

#### 3.4 Scheduler Integration
- [ ] Update `app/core/scheduler.py`
  - Add job: Update Monero solo effort (every 1 minute)
  - Add job: Sync wallet transactions (every 5 minutes)
  - Add job: Detect new blocks (every 2 minutes)
  - Add job: Update XMRig hashrate (every 30 seconds)

### Outcomes
- ✅ Dashboard shows 4 Monero solo mining tiles
- ✅ Tiles only appear when feature enabled and workers active
- ✅ Real-time data updates automatically
- ✅ Proper formatting and visual polish
- ✅ Background jobs keep data current

### Testing

#### Unit Tests
- [ ] Test stats API response structure
- [ ] Test worker detection logic
- [ ] Test hashrate aggregation
- [ ] Test effort calculation

#### Integration Tests
- [ ] Test scheduler jobs execute correctly
- [ ] Test data flows from RPC to database to API
- [ ] Test wallet transaction syncing

#### Manual Testing
- [ ] Start with feature disabled - tiles should not appear
- [ ] Enable feature - tiles should appear (if workers active)
- [ ] Stop all XMRig miners - tiles should disappear
- [ ] Start XMRig miner pointing to solo pool
  - Workers tile should show 1 worker + hashrate
  - Effort should start accumulating
- [ ] Check today's reward updates after wallet sync
- [ ] Verify all-time reward shows correct total
- [ ] Check effort percentage color coding
- [ ] Verify expected time calculation is reasonable
- [ ] Test with multiple XMRig miners - hashrate should sum

---

## Phase 4: Analytics Page (Detailed View)

### Objective
Create comprehensive analytics page similar to CKPool with charts, tables, and detailed metrics.

### Tasks

#### 4.1 Analytics API Endpoints
- [ ] Update `app/api/monero_solo.py`
  - `GET /api/monero-solo/analytics` - Main analytics data
    - Summary stats (workers, network stats, effort, balance)
    - Time range parameter support
  - `GET /api/monero-solo/hashrate-chart` - Hashrate over time
    - Time series data (timestamp, hashrate)
    - Network difficulty overlay
    - Time range filter (6h/24h/3d/7d/30d)
  - `GET /api/monero-solo/effort-chart` - Effort timeline
    - Current effort history
    - Block found markers
    - Average luck indicator
  - `GET /api/monero-solo/blocks` - Block history table
    - Paginated results
    - Columns: date, height, reward, effort, GBP value
  - `GET /api/monero-solo/workers` - Active workers table
    - Miner name, hashrate, uptime, shares
  - `GET /api/monero-solo/transactions` - Recent wallet transactions
    - Last 20 incoming transactions
    - Block reward filtering
  - `GET /api/monero-solo/export-csv` - CSV export
    - Time range parameter
    - All metrics included

#### 4.2 Analytics UI Route
- [ ] Update `app/ui/routes.py`
  - `@router.get("/analytics/monero-solo")` - Analytics page
  - Breadcrumbs: Dashboard → Analytics → Monero Solo
  - Pass initial data to template

#### 4.3 Analytics Template
- [ ] Create `app/ui/templates/analytics/monero_solo.html`
  - **Top Stats Section** (8 cards):
    - Total Workers
    - Network Hashrate
    - Network Difficulty
    - Current Block Height
    - Current Effort %
    - Expected Time to Block
    - Wallet Balance
    - Total Blocks Found
  
  - **Charts Section**:
    - Hashrate Over Time (Chart.js line chart)
      - Combined miner hashrate
      - Network difficulty (secondary axis)
      - Time range selector
    - Effort Timeline (Chart.js line chart)
      - Current round effort
      - Historical effort with block markers
      - Lucky/unlucky indicator line
    - Balance Growth (Chart.js line chart)
      - Wallet balance over time
      - Block reward spikes visible
    - Shares Submitted (Chart.js bar chart)
      - Accepted vs rejected shares
      - Time-based grouping
    - Profitability Chart (Chart.js line chart)
      - Daily XMR earnings
      - Daily GBP value
      - Energy cost overlay
      - Net profit/loss line
  
  - **Tables Section**:
    - Active Miners Table
      - Columns: Name, Hashrate, Uptime, Shares, Status
      - Real-time updates
    - Block History Table
      - Columns: Date, Height, Reward (XMR), Reward (GBP), Effort %, Duration
      - Pagination (20 per page)
      - Color coding for luck
      - CSV export button
    - Recent Transactions Table
      - Columns: Date, Block Height, Amount (XMR), Amount (GBP), TX Hash
      - Last 20 transactions
      - Link to block explorer
    - Block Statistics Summary
      - Total blocks found
      - Average effort
      - Best luck (lowest effort)
      - Worst luck (highest effort)
      - Average time between blocks

  - **Filters & Controls**:
    - Time range selector (6h/24h/3d/7d/30d/all)
    - Auto-refresh toggle
    - Export to CSV button
    - Refresh button

#### 4.4 Analytics JavaScript
- [ ] Create analytics.js functions
  - `loadMoneroSoloAnalytics()` - Main data loader
  - `renderHashrateChart()` - Chart.js implementation
  - `renderEffortChart()` - Chart.js implementation
  - `renderBalanceChart()` - Chart.js implementation
  - `renderSharesChart()` - Chart.js implementation
  - `renderProfitabilityChart()` - Chart.js implementation
  - `loadWorkersTable()` - Dynamic table population
  - `loadBlocksTable()` - Dynamic table with pagination
  - `loadTransactionsTable()` - Dynamic table
  - `updateTimeRange()` - Handle time filter changes
  - `exportToCsv()` - CSV download handler
  - Auto-refresh logic (30 second interval)
  - Real-time data updates

#### 4.5 Telemetry Storage
- [ ] Update `app/core/monero_solo.py`
  - Store hashrate snapshots for charts
  - Store effort history for timeline
  - Store balance snapshots for growth chart
  - Implement data retention (30 days)
  - Auto-purge old data

### Outcomes
- ✅ Comprehensive analytics page with 5+ charts
- ✅ Real-time worker monitoring
- ✅ Complete block history with effort tracking
- ✅ Wallet transaction history
- ✅ CSV export functionality
- ✅ Professional UI matching CKPool analytics quality
- ✅ Time range filtering works correctly
- ✅ Auto-refresh keeps data current

### Testing

#### Unit Tests
- [ ] Test analytics API response schemas
- [ ] Test time range filtering logic
- [ ] Test CSV export formatting
- [ ] Test pagination logic

#### Integration Tests
- [ ] Test chart data retrieval and formatting
- [ ] Test real-time updates
- [ ] Test data retention and purging
- [ ] Test export with various time ranges

#### Manual Testing
- [ ] Navigate to analytics page
- [ ] Verify all 8 stat cards display correct data
- [ ] Test each chart:
  - Hashrate chart shows data, time range selector works
  - Effort chart shows current round and history
  - Balance chart shows growth over time
  - Shares chart shows accepted/rejected breakdown
  - Profitability chart shows earnings vs costs
- [ ] Test tables:
  - Active miners table shows all XMRig miners
  - Block history table shows found blocks with correct effort
  - Transactions table shows wallet incoming transfers
  - Block statistics show accurate aggregates
- [ ] Test time range filtering:
  - Change to 6h - data updates
  - Change to 30d - data updates
  - Change to "all" - data updates
- [ ] Test CSV export:
  - Click export button
  - Verify CSV downloads
  - Check data accuracy and formatting
- [ ] Test auto-refresh:
  - Enable auto-refresh
  - Wait 30 seconds
  - Verify data updates automatically
- [ ] Test with no blocks found - should handle gracefully
- [ ] Test with wallet RPC offline - should show errors

---

## Phase 5: Testing & Refinement

### Objective
Comprehensive system testing, bug fixes, performance optimization, and documentation.

### Tasks

#### 5.1 End-to-End Testing
- [ ] Full workflow test: Setup to block finding
  - Install and configure Monero node
  - Install and configure wallet RPC
  - Enable feature in settings
  - Configure XMRig to point to node
  - Start mining
  - Verify dashboard tiles appear
  - Verify effort accumulates correctly
  - Simulate block found (or wait for real block)
  - Verify effort resets
  - Verify transaction appears in wallet
  - Verify analytics page shows block
  - Verify all charts update correctly

#### 5.2 Error Handling
- [ ] Test all failure scenarios:
  - Node RPC offline - show error, don't crash
  - Wallet RPC offline - show error, don't crash
  - Invalid credentials - clear error message
  - Network timeout - retry logic works
  - Wallet locked - helpful error message
  - No XMRig miners - tiles hidden gracefully
  - Database connection lost - graceful degradation
  - Invalid configuration - validation catches it

#### 5.3 Performance Testing
- [ ] Test with multiple XMRig miners (10+)
  - Hashrate aggregation performs well
  - Dashboard loads quickly
  - Analytics page loads quickly
- [ ] Test with large wallet history (1000+ transactions)
  - Transaction sync performs well
  - Pagination works correctly
  - No memory leaks
- [ ] Test with long mining session (24+ hours)
  - Effort calculation remains accurate
  - No data accumulation issues
  - Scheduler jobs remain stable

#### 5.4 UI/UX Polish
- [ ] Visual consistency
  - Monero logo/branding consistent
  - Color scheme matches existing design
  - Responsive design on mobile
  - Dark/light theme support
- [ ] User feedback
  - Loading indicators during API calls
  - Toast notifications for errors
  - Success messages for saves
  - Helpful tooltips and hints
- [ ] Accessibility
  - Keyboard navigation works
  - Screen reader compatibility
  - WCAG AA compliance

#### 5.5 Documentation
- [ ] Create user documentation
  - `docs/MONERO_SOLO_SETUP.md`
    - Prerequisites (node, wallet RPC)
    - Installation steps
    - Configuration guide
    - Troubleshooting section
  - Update README.md with feature mention
  - Add FAQ entries
  - Add screenshots

#### 5.6 Code Quality
- [ ] Code review
  - Follow existing patterns
  - Type hints complete
  - Error handling consistent
  - Logging appropriate
- [ ] Linting and formatting
  - Pass all linters
  - Consistent code style
- [ ] Comments and docstrings
  - All functions documented
  - Complex logic explained
  - API endpoints documented

### Outcomes
- ✅ Feature works reliably in all scenarios
- ✅ Performance is acceptable with realistic loads
- ✅ UI is polished and professional
- ✅ Error messages are helpful
- ✅ Documentation is complete and accurate
- ✅ Code is maintainable and follows project standards

### Testing

#### Regression Testing
- [ ] Run all existing tests - nothing broken
- [ ] Test other features still work:
  - P2Pool integration unaffected
  - CKPool integration unaffected
  - SupportXMR integration unaffected
  - Other dashboards unaffected

#### User Acceptance Testing
- [ ] Fresh install test
  - Start with clean database
  - Follow documentation to set up
  - User can complete setup without issues
- [ ] Real-world mining test
  - Mine to solo pool for 24 hours
  - Verify all metrics accurate
  - Compare to actual node/wallet data
  - Verify rewards match wallet RPC

#### Final Checklist
- [ ] All automated tests pass
- [ ] No console errors in browser
- [ ] No Python exceptions in logs
- [ ] Documentation complete
- [ ] Code reviewed and merged
- [ ] Feature flag enabled by default
- [ ] Changelog updated
- [ ] Release notes written

---

## Dependencies & Prerequisites

### External Services Required
- Monero node with RPC enabled (`monerod --rpc-bind-ip=0.0.0.0 --rpc-bind-port=18081`)
- Monero wallet RPC (`monero-wallet-rpc --rpc-bind-ip=0.0.0.0 --rpc-bind-port=18083`)
- XMRig miners configured to point to solo pool

### Python Packages
- `aiohttp` - Already in requirements (for RPC calls)
- No new dependencies needed

### Database Changes
- 4 new tables (migrations included)
- Backward compatible

---

## Timeline Estimates

- **Phase 1**: 2-3 days (Core infrastructure)
- **Phase 2**: 1-2 days (Settings UI)
- **Phase 3**: 2-3 days (Dashboard tiles)
- **Phase 4**: 3-4 days (Analytics page)
- **Phase 5**: 2-3 days (Testing & polish)

**Total**: 10-15 days development time

---

## Success Criteria

✅ **Feature Complete When:**
1. User can configure Monero solo mining in settings
2. Dashboard shows 4 tiles with accurate real-time data
3. Analytics page provides comprehensive insights
4. System correctly tracks effort and resets on block found
5. Wallet rewards are accurately reported
6. All tests pass
7. Documentation is complete
8. No known bugs

---

## Future Enhancements (Post-MVP)

- Notification when block is found (Telegram/Discord)
- Historical performance comparison (this month vs last month)
- Multiple wallet support
- Solo pool templates/presets
- Block explorer integration (clickable block links)
- Estimated earnings calculator
- Mining profitability alerts
- Mobile app view optimization
