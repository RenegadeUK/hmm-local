import { StatsCard } from "@/components/widgets/StatsCard";
import { PoolTile } from "@/components/widgets/PoolTile";
import { NerdMinersTile } from "@/components/widgets/NerdMinersTile";
import { BraiinsTile } from "@/components/widgets/BraiinsTile";
import { useQuery } from "@tanstack/react-query";
import { dashboardAPI, poolsAPI, type BraiinsStatsResponse, type DashboardData, type SolopoolStats, type NerdMinersStats, type PoolTilesResponse } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { formatPoolHashrate } from "@/lib/utils";
import { useEffect, useState } from "react";

// Coin-specific colors
const getCoinColor = (coin: string): string => {
  const colors: Record<string, string> = {
    BTC: "bg-orange-500",
    BCH: "bg-green-500",
    DGB: "bg-blue-500",
    BC2: "bg-purple-500",
    LTC: "bg-gray-500",
  };
  return colors[coin.toUpperCase()] || "bg-orange-500";
};

interface CryptoPricesResponse {
  success: boolean;
  [symbol: string]: number | boolean | undefined;
}

interface StrategyBandSummary {
  target_coin?: string;
}

interface StrategyBandsResponse {
  bands?: StrategyBandSummary[];
}

interface PoolChartPoint {
  x: number;
  y: number;
}

interface PoolChartsResponse {
  charts?: {
    dgb?: PoolChartPoint[];
    bc2?: PoolChartPoint[];
    btc?: PoolChartPoint[];
    bch?: PoolChartPoint[];
    [key: string]: PoolChartPoint[] | undefined;
  };
}

export function Dashboard() {
  const navigate = useNavigate();
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    const initial = (window as unknown as { __realtimeConnected?: boolean }).__realtimeConnected;
    setIsLive(Boolean(initial));

    const handleStatus = (event: Event) => {
      const detail = (event as CustomEvent).detail as { connected?: boolean } | undefined;
      if (typeof detail?.connected === "boolean") {
        setIsLive(detail.connected);
      }
    };

    window.addEventListener("realtime-status", handleStatus as EventListener);
    return () => window.removeEventListener("realtime-status", handleStatus as EventListener);
  }, []);

  const LiveBadge = () => (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold border ${
        isLive
          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
          : "bg-gray-500/10 text-gray-400 border-gray-500/30"
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${isLive ? "bg-emerald-400" : "bg-gray-500"}`} />
      {isLive ? "Live" : "Polling"}
    </span>
  );

  const { data, isLoading, error } = useQuery<DashboardData>({
    queryKey: ["dashboard", "all"],
    queryFn: () => dashboardAPI.getAll("asic"),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  // Fetch per-pool tiles
  const { data: poolTiles } = useQuery<PoolTilesResponse>({
    queryKey: ["pools", "tiles"],
    queryFn: () => poolsAPI.getPoolTiles(),
    refetchInterval: 30000, // Match backend cache (30 seconds)
  });

  const { data: solopoolData } = useQuery<SolopoolStats>({
    queryKey: ["pools", "solopool"],
    queryFn: () => poolsAPI.getSolopoolStats(),
    refetchInterval: 20000, // Refresh every 20 seconds
  });

  const { data: nerdminersData } = useQuery<NerdMinersStats>({
    queryKey: ["pools", "nerdminers"],
    queryFn: () => poolsAPI.getNerdMinersStats(),
    refetchInterval: 20000, // Refresh every 20 seconds
  });

  const { data: braiinsData } = useQuery<BraiinsStatsResponse>({
    queryKey: ["pools", "braiins"],
    queryFn: () => poolsAPI.getBraiinsStats(),
    refetchInterval: 20000, // Refresh every 20 seconds
  });

  const { data: pricesData } = useQuery<CryptoPricesResponse>({
    queryKey: ["crypto-prices"],
    queryFn: async () => {
      const response = await fetch("/api/settings/crypto-prices");
      if (!response.ok) {
        throw new Error("Failed to fetch crypto prices");
      }
      return response.json() as Promise<CryptoPricesResponse>;
    },
    refetchInterval: 60000, // Refresh every minute
  });

  // Fetch strategy bands to determine which coins are in the strategy
  const { data: bandsData } = useQuery<StrategyBandsResponse>({
    queryKey: ["agile-bands"],
    queryFn: async () => {
      const response = await fetch("/api/settings/agile-solo-strategy/bands");
      if (!response.ok) {
        throw new Error("Failed to fetch strategy bands");
      }
      return response.json() as Promise<StrategyBandsResponse>;
    },
    refetchInterval: 60000,
    enabled: !!solopoolData?.strategy_enabled,
  });

  // Fetch chart data for sparklines
  const { data: chartsData } = useQuery<PoolChartsResponse>({
    queryKey: ["solopool-charts"],
    queryFn: async () => {
      const response = await fetch("/api/settings/solopool/charts");
      if (!response.ok) {
        throw new Error("Failed to fetch pool charts");
      }
      return response.json() as Promise<PoolChartsResponse>;
    },
    refetchInterval: 60000, // Refresh every minute
  });

  // Extract coins from strategy bands (exclude "OFF")
  const strategyCoins = new Set<string>();
  if (solopoolData?.strategy_enabled && bandsData?.bands) {
    bandsData.bands.forEach((band) => {
      if (band?.target_coin && band.target_coin !== 'OFF') {
        strategyCoins.add(band.target_coin);
      }
    });
  }

  const getCoinPrice = (coinKey: string): number => {
    if (!pricesData?.success) return 0;
    const rawPrice = pricesData[coinKey];
    return typeof rawPrice === "number" ? rawPrice : 0;
  };

  // Helper to calculate GBP value
  const calculateGBP = (amount: number, coinKey: string): string => {
    const price = getCoinPrice(coinKey);
    return price > 0 ? (amount * price).toFixed(2) : "0.00";
  };

  const defaultBestShare: DashboardData["stats"]["best_share_24h"] = {
    difficulty: 0,
    coin: "",
    network_difficulty: 0,
    percentage: 0,
    timestamp: "",
    time_ago_seconds: 0,
  };

  const defaultStats: DashboardData["stats"] = {
    online_miners: 0,
    total_hashrate_ghs: 0,
    total_pool_hashrate_ghs: 0,
    pool_efficiency_percent: 0,
    total_power_watts: 0,
    avg_efficiency_wth: 0,
    total_cost_24h_pounds: 0,
    avg_price_per_kwh_pence: 0,
    current_energy_price_pence: 0,
    best_share_24h: defaultBestShare,
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <LiveBadge />
        </div>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted-foreground">Loading dashboard...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <LiveBadge />
        </div>
        <div className="flex items-center justify-center h-64">
          <div className="text-destructive">
            Error loading dashboard: {error.message}
          </div>
        </div>
      </div>
    );
  }

  const stats = data?.stats ?? defaultStats;
  const bestShare = stats.best_share_24h ?? defaultBestShare;
  const braiinsWorkersOnline = braiinsData?.stats?.workers_online ?? 0;
  const braiinsHashrate5mDisplay = typeof braiinsData?.stats?.hashrate_5m === "string"
    ? braiinsData.stats.hashrate_5m
    : braiinsData?.stats?.hashrate_5m != null
      ? String(braiinsData.stats.hashrate_5m)
      : null;

  // Format network difficulty
  const formatNetworkDiff = (diff: number | null) => {
    if (!diff) return "Unavailable";
    if (diff >= 1_000_000_000) {
      return `${(diff / 1_000_000_000).toFixed(1)}B`;
    } else if (diff >= 1_000_000) {
      return `${(diff / 1_000_000).toFixed(0)}M`;
    }
    return diff.toFixed(0);
  };

  // Format time ago
  const formatTimeAgo = (seconds: number | null) => {
    if (seconds === null) return "Unavailable";
    if (seconds < 60) {
      return `${seconds}s ago`;
    } else if (seconds < 3600) {
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `${mins}m ${secs}s ago`;
    } else if (seconds < 86400) {
      const hours = Math.floor(seconds / 3600);
      const mins = Math.floor((seconds % 3600) / 60);
      return `${hours}h ${mins}m ago`;
    } else {
      const days = Math.floor(seconds / 86400);
      return `${days}d ago`;
    }
  };

  const poolHashrateGhs = stats.total_pool_hashrate_ghs ?? 0;

  const poolHashrateDisplay = poolHashrateGhs > 0
    ? formatPoolHashrate(poolHashrateGhs)
    : "Unavailable";

  const resolvedEfficiency = (stats.pool_efficiency_percent && stats.pool_efficiency_percent > 0)
    ? stats.pool_efficiency_percent
    : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <LiveBadge />
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          label="Workers Online"
          value={stats.online_miners || 0}
          onClick={() => navigate("/miners")}
          subtext={
            <>
              <div>
                Pool: {poolHashrateDisplay}
              </div>
              <div className="text-xs">
                ⚡ {(() => {
                  if (!resolvedEfficiency || resolvedEfficiency <= 0) {
                    return "Unavailable";
                  }
                  let color = "";
                  if (resolvedEfficiency >= 95) {
                    color = "text-green-500";
                  } else if (resolvedEfficiency >= 85) {
                    color = "text-yellow-500";
                  } else {
                    color = "text-red-500";
                  }
                  return <span className={color}>{resolvedEfficiency.toFixed(0)}% of expected</span>;
                })()}
              </div>
            </>
          }
        />

        <StatsCard
          label="Power Use"
          value={`${Math.round(stats.total_power_watts || 0)} W`}
          onClick={() => navigate("/miners")}
          subtext={
            <div>
              Efficiency: {stats.avg_efficiency_wth 
                ? `${stats.avg_efficiency_wth.toFixed(1)} J/TH` 
                : "Unavailable"}
            </div>
          }
        />

        <StatsCard
          label="Cost (24h)"
          value={`£${(stats.total_cost_24h_pounds || 0).toFixed(2)}`}
          subtext={
            <div>
              Avg: {stats.avg_price_per_kwh_pence 
                ? `${stats.avg_price_per_kwh_pence.toFixed(1)}p / kWh` 
                : "Unavailable"}
            </div>
          }
        />

        <StatsCard
          label="Best Share (24h)"
          value={`${bestShare.percentage || 0}%`}
          badge={
            bestShare.coin ? (
              <span className={`inline-block px-1.5 py-0.5 text-xs font-semibold rounded ${
                bestShare.coin === "BTC" ? "bg-orange-500 text-white" :
                bestShare.coin === "BCH" ? "bg-green-500 text-white" :
                bestShare.coin === "DGB" ? "bg-blue-500 text-white" :
                bestShare.coin === "BC2" ? "bg-purple-500 text-white" :
                "bg-gray-500 text-white"
              }`}>
                {bestShare.coin}
              </span>
            ) : null
          }
          subtext={
            <>
              <div>
                Network diff: {formatNetworkDiff(bestShare.network_difficulty)}
              </div>
              <div className="text-xs">
                {formatTimeAgo(bestShare.time_ago_seconds)}
              </div>
            </>
          }
        />
      </div>

      {/* NEW: Per-Pool Tiles - Plugin-Based Architecture */}
      <div className="space-y-4 border-t pt-4 mt-4">
        {poolTiles && Object.entries(poolTiles).map(([poolId, pool]) => (
          <div key={poolId}>
            <div className="flex items-center gap-2 mb-3">
              <h2 className="text-xl font-semibold">{pool.display_name}</h2>
              <span className="text-sm text-muted-foreground">({pool.pool_type})</span>
              {pool.supports_coins && pool.supports_coins.length > 0 && (
                <span className="inline-block px-2 py-0.5 text-xs font-semibold rounded bg-blue-500 text-white">
                  {pool.supports_coins.join(", ")}
                </span>
              )}
            </div>
            
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {/* Tile 1: Health */}
              <StatsCard
                label="Pool Health"
                value={pool.tile_1_health?.health_status ? "Healthy" : "Unhealthy"}
                badge={
                  <span className={`inline-block px-1.5 py-0.5 text-xs font-semibold rounded ${
                    pool.tile_1_health?.health_status ? "bg-green-500 text-white" : "bg-red-500 text-white"
                  }`}>
                    {pool.tile_1_health?.health_status ? "OK" : "ERROR"}
                  </span>
                }
                subtext={
                  <>
                    {pool.tile_1_health?.health_message && (
                      <div>{pool.tile_1_health.health_message}</div>
                    )}
                    {pool.tile_1_health?.latency_ms !== null && pool.tile_1_health?.latency_ms !== undefined && (
                      <div className="text-xs">Latency: {pool.tile_1_health.latency_ms.toFixed(0)}ms</div>
                    )}
                  </>
                }
              />

              {/* Tile 2: Network */}
              <StatsCard
                label="Pool Hashrate"
                value={pool.tile_2_network?.pool_hashrate ? formatPoolHashrate(pool.tile_2_network.pool_hashrate) : "N/A"}
                subtext={
                  <>
                    {pool.tile_2_network?.network_difficulty && (
                      <div>Network: {formatNetworkDiff(pool.tile_2_network.network_difficulty)}</div>
                    )}
                    {pool.tile_2_network?.pool_percentage !== null && pool.tile_2_network?.pool_percentage !== undefined && (
                      <div className="text-xs">Pool: {pool.tile_2_network.pool_percentage.toFixed(4)}%</div>
                    )}
                    {pool.tile_2_network?.estimated_time_to_block && (
                      <div className="text-xs">ETTB: {pool.tile_2_network.estimated_time_to_block}</div>
                    )}
                  </>
                }
              />

              {/* Tile 3: Shares */}
              <StatsCard
                label="Shares (24h)"
                value={pool.tile_3_shares?.shares_valid !== null && pool.tile_3_shares?.shares_valid !== undefined ? pool.tile_3_shares.shares_valid.toLocaleString() : "N/A"}
                subtext={
                  <>
                    {pool.tile_3_shares?.shares_invalid !== null && pool.tile_3_shares?.shares_invalid !== undefined && pool.tile_3_shares.shares_invalid > 0 && (
                      <div className="text-red-500">Invalid: {pool.tile_3_shares.shares_invalid.toLocaleString()}</div>
                    )}
                    {pool.tile_3_shares?.shares_stale !== null && pool.tile_3_shares?.shares_stale !== undefined && pool.tile_3_shares.shares_stale > 0 && (
                      <div className="text-yellow-500">Stale: {pool.tile_3_shares.shares_stale.toLocaleString()}</div>
                    )}
                    {pool.tile_3_shares?.reject_rate !== null && pool.tile_3_shares?.reject_rate !== undefined && (
                      <div className="text-xs">Reject: {pool.tile_3_shares.reject_rate.toFixed(2)}%</div>
                    )}
                  </>
                }
              />

              {/* Tile 4: Blocks/Earnings */}
              <StatsCard
                label={pool.supports_earnings ? "Earnings (24h)" : "Blocks (24h)"}
                value={
                  pool.supports_earnings && pool.tile_4_blocks?.estimated_earnings_24h !== null && pool.tile_4_blocks?.estimated_earnings_24h !== undefined
                    ? `${pool.tile_4_blocks.estimated_earnings_24h.toFixed(8)} ${pool.tile_4_blocks.currency || "BTC"}`
                    : pool.tile_4_blocks?.blocks_found_24h !== null && pool.tile_4_blocks?.blocks_found_24h !== undefined
                    ? `${pool.tile_4_blocks.blocks_found_24h} blocks`
                    : "N/A"
                }
                badge={
                  pool.tile_4_blocks?.currency ? (
                    <span className={`inline-block px-1.5 py-0.5 text-xs font-semibold rounded ${getCoinColor(pool.tile_4_blocks.currency)} text-white`}>
                      {pool.tile_4_blocks.currency}
                    </span>
                  ) : null
                }
                subtext={
                  <>
                    {pool.supports_balance && (
                      <>
                        {pool.tile_4_blocks?.confirmed_balance !== null && pool.tile_4_blocks?.confirmed_balance !== undefined && (
                          <div>Confirmed: {pool.tile_4_blocks.confirmed_balance.toFixed(8)} {pool.tile_4_blocks.currency}</div>
                        )}
                        {pool.tile_4_blocks?.pending_balance !== null && pool.tile_4_blocks?.pending_balance !== undefined && (
                          <div className="text-xs">Pending: {pool.tile_4_blocks.pending_balance.toFixed(8)} {pool.tile_4_blocks.currency}</div>
                        )}
                      </>
                    )}
                  </>
                }
              />
            </div>
          </div>
        ))}
      </div>

      {/* LEGACY Pool Tiles (Keep temporarily for comparison) */}
      <div className="space-y-3 border-t pt-4 mt-4">
        <h2 className="text-lg font-semibold text-muted-foreground">Legacy Pool Tiles (Will be removed)</h2>
        {/* Solopool */}
        {solopoolData && solopoolData.enabled && (
          <>
            {/* DGB Pools */}
            {(strategyCoins.size === 0 || strategyCoins.has('DGB')) && solopoolData.dgb_miners?.filter((miner) => {
              if (miner.is_strategy_pool) return true;
              return (miner.stats?.workers || 0) > 0;
            }).map((miner) => (
            <PoolTile
              key={`dgb-${miner.username}`}
              coin="DGB"
              workersOnline={miner.stats?.workers || 0}
              hashrate={miner.stats?.hashrate || ""}
              currentLuck={miner.stats?.current_luck || null}
              ettb={miner.stats?.ettb?.formatted || null}
              lastBlockTime={miner.stats?.lastBlockTimestamp ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastBlockTimestamp) : null}
              lastBlockTimestamp={miner.stats?.lastBlockTimestamp || null}
              blocks24h={miner.stats?.blocks_24h || 0}
              blocks7d={miner.stats?.blocks_7d || 0}
              blocks30d={miner.stats?.blocks_30d || 0}
              shares={miner.stats?.shares || 0}
              lastShare={miner.stats?.lastShare ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastShare) : null}
              lastShareTimestamp={miner.stats?.lastShare || null}
              totalPaid={`${(miner.stats?.paid ? miner.stats.paid / 1000000000 : 0).toFixed(8)} DGB`}
              paidValue={`£${calculateGBP(miner.stats?.paid ? miner.stats.paid / 1000000000 : 0, 'digibyte')}`}
              accountUrl={`https://dgb-sha.solopool.org/account/${miner.username}`}
              isStrategyActive={miner.is_active_target}
              isStrategyInactive={miner.is_strategy_pool && !miner.is_active_target}
              chartData={chartsData?.charts?.dgb}
            />
          ))}

          {/* BCH Pools */}
          {(strategyCoins.size === 0 || strategyCoins.has('BCH')) && solopoolData.bch_miners?.filter((miner) => {
            if (miner.is_strategy_pool) return true;
            return (miner.stats?.workers || 0) > 0;
          }).map((miner) => (
            <PoolTile
              key={`bch-${miner.username}`}
              coin="BCH"
              workersOnline={miner.stats?.workers || 0}
              hashrate={miner.stats?.hashrate || ""}
              currentLuck={miner.stats?.current_luck || null}
              ettb={miner.stats?.ettb?.formatted || null}
              lastBlockTime={miner.stats?.lastBlockTimestamp ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastBlockTimestamp) : null}
              lastBlockTimestamp={miner.stats?.lastBlockTimestamp || null}
              blocks24h={miner.stats?.blocks_24h || 0}
              blocks7d={miner.stats?.blocks_7d || 0}
              blocks30d={miner.stats?.blocks_30d || 0}
              shares={miner.stats?.shares || 0}
              lastShare={miner.stats?.lastShare ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastShare) : null}
              lastShareTimestamp={miner.stats?.lastShare || null}
              totalPaid={`${(miner.stats?.paid ? miner.stats.paid / 100000000 : 0).toFixed(8)} BCH`}
              paidValue={`£${calculateGBP(miner.stats?.paid ? miner.stats.paid / 100000000 : 0, 'bitcoin-cash')}`}
              accountUrl={`https://bch.solopool.org/account/${miner.username}`}
              isStrategyActive={miner.is_active_target}
              isStrategyInactive={miner.is_strategy_pool && !miner.is_active_target}
              chartData={chartsData?.charts?.bch}
            />
          ))}

          {/* BC2 Pools */}
          {(strategyCoins.size === 0 || strategyCoins.has('BC2')) && solopoolData.bc2_miners?.filter((miner) => {
            if (miner.is_strategy_pool) return true;
            return (miner.stats?.workers || 0) > 0;
          }).map((miner) => (
            <PoolTile
              key={`bc2-${miner.username}`}
              coin="BC2"
              workersOnline={miner.stats?.workers || 0}
              hashrate={miner.stats?.hashrate || ""}
              currentLuck={miner.stats?.current_luck || null}
              ettb={miner.stats?.ettb?.formatted || null}
              lastBlockTime={miner.stats?.lastBlockTimestamp ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastBlockTimestamp) : null}
              lastBlockTimestamp={miner.stats?.lastBlockTimestamp || null}
              blocks24h={miner.stats?.blocks_24h || 0}
              blocks7d={miner.stats?.blocks_7d || 0}
              blocks30d={miner.stats?.blocks_30d || 0}
              shares={miner.stats?.shares || 0}
              lastShare={miner.stats?.lastShare ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastShare) : null}
              lastShareTimestamp={miner.stats?.lastShare || null}
              totalPaid={`${(miner.stats?.paid ? miner.stats.paid / 100000000 : 0).toFixed(8)} BC2`}
              paidValue={`£${calculateGBP(miner.stats?.paid ? miner.stats.paid / 100000000 : 0, 'bellscoin')}`}
              accountUrl={`https://bc2.solopool.org/account/${miner.username}`}
              isStrategyActive={miner.is_active_target}
              isStrategyInactive={miner.is_strategy_pool && !miner.is_active_target}
              chartData={chartsData?.charts?.bc2}
            />
          ))}

          {/* BTC Pools */}
          {(strategyCoins.size === 0 || strategyCoins.has('BTC')) && solopoolData.btc_miners?.filter((miner) => {
            if (miner.is_strategy_pool) return true;
            return (miner.stats?.workers || 0) > 0;
          }).map((miner) => (
            <PoolTile
              key={`btc-${miner.username}`}
              coin="BTC"
              workersOnline={miner.stats?.workers || 0}
              hashrate={miner.stats?.hashrate || ""}
              currentLuck={miner.stats?.current_luck || null}
              ettb={miner.stats?.ettb?.formatted || null}
              lastBlockTime={miner.stats?.lastBlockTimestamp ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastBlockTimestamp) : null}
              lastBlockTimestamp={miner.stats?.lastBlockTimestamp || null}
              blocks24h={miner.stats?.blocks_24h || 0}
              blocks7d={miner.stats?.blocks_7d || 0}
              blocks30d={miner.stats?.blocks_30d || 0}
              shares={miner.stats?.shares || 0}
              lastShare={miner.stats?.lastShare ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastShare) : null}
              lastShareTimestamp={miner.stats?.lastShare || null}
              totalPaid={`${(miner.stats?.paid ? miner.stats.paid / 100000000 : 0).toFixed(8)} BTC`}
              paidValue={`£${calculateGBP(miner.stats?.paid ? miner.stats.paid / 100000000 : 0, 'bitcoin')}`}
              accountUrl={`https://btc.solopool.org/account/${miner.username}`}
              isStrategyActive={miner.is_active_target}
              isStrategyInactive={miner.is_strategy_pool && !miner.is_active_target}
              chartData={chartsData?.charts?.btc}
            />
          ))}
          </>
        )}

        {/* Braiins Pool */}
        {(strategyCoins.size === 0 || strategyCoins.has('BTC_POOLED')) && braiinsData && braiinsData.enabled && braiinsData.stats && 
          (braiinsData.show_always || braiinsWorkersOnline > 0) && (
          <BraiinsTile
            workersOnline={braiinsWorkersOnline}
            hashrate5m={braiinsHashrate5mDisplay}
            hashrateRaw={braiinsData.stats.hashrate_raw || 0}
            currentBalance={braiinsData.stats.current_balance || 0}
            todayReward={braiinsData.stats.today_reward || 0}
            allTimeReward={braiinsData.stats.all_time_reward || 0}
            username={braiinsData.username || ""}
            btcPriceGBP={getCoinPrice('bitcoin')}
            isStrategyActive={braiinsData.is_strategy_active}
            isStrategyInactive={braiinsData.show_always && !braiinsData.is_strategy_active}
          />
        )}
        
        {/* NerdMiners Pool */}
        {nerdminersData && nerdminersData.enabled && nerdminersData.btc_miners && nerdminersData.btc_miners.length > 0 && (
          <>
            {nerdminersData.btc_miners.filter((miner) => {
              // Only show if miners are actively mining (workers > 0)
              return (miner.stats?.workers || 0) > 0;
            }).map((miner) => (
              <NerdMinersTile
                key={`nerdminers-${miner.username}`}
                workersOnline={miner.stats?.workers || 0}
                hashrate={miner.stats?.hashrate || "0 H/s"}
                shares={miner.stats?.shares || 0}
                lastShare={miner.stats?.lastShare ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastShare) : null}
                lastShareTimestamp={miner.stats?.lastShare || null}
                bestShare={miner.stats?.bestShare || 0}
                bestEver={miner.stats?.bestEver || 0}
                poolTotalWorkers={miner.stats?.poolTotalWorkers || 0}
                poolDifficulty={miner.stats?.poolDifficulty || 0}
                walletAddress={miner.username}
                isStrategyActive={false}
                isStrategyInactive={false}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
