import { StatsCard } from "@/components/widgets/StatsCard";
import { PoolTile } from "@/components/widgets/PoolTile";
import { BraiinsTile } from "@/components/widgets/BraiinsTile";
import { useQuery } from "@tanstack/react-query";
import { dashboardAPI, poolsAPI, type BraiinsStatsResponse, type DashboardData, type SolopoolStats } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { formatHashrate } from "@/lib/utils";

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
  timestamp: number;
  value: number;
}

interface PoolChartsResponse {
  charts?: {
    dgb?: PoolChartPoint[];
    bc2?: PoolChartPoint[];
    btc?: PoolChartPoint[];
    [key: string]: PoolChartPoint[] | undefined;
  };
}

const formatChartData = (points?: PoolChartPoint[]) =>
  (points ?? []).map((point) => ({ x: point.timestamp, y: point.value }));

export function Dashboard() {
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery<DashboardData>({
    queryKey: ["dashboard", "all"],
    queryFn: () => dashboardAPI.getAll("asic"),
    refetchInterval: 5000, // Refresh every 5 seconds
  });

  const { data: solopoolData } = useQuery<SolopoolStats>({
    queryKey: ["pools", "solopool"],
    queryFn: () => poolsAPI.getSolopoolStats(),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  const { data: braiinsData } = useQuery<BraiinsStatsResponse>({
    queryKey: ["pools", "braiins"],
    queryFn: () => poolsAPI.getBraiinsStats(),
    refetchInterval: 10000, // Refresh every 10 seconds
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

  const sumSolopoolHashrate = (miners?: SolopoolStats["dgb_miners"]) => {
    if (!miners) return 0;
    return miners.reduce((total, miner) => {
      const rawHashrate = miner.stats?.hashrate_raw ?? 0;
      return total + rawHashrate / 1e9;
    }, 0);
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
  const braiinsHashrate5mDisplay = typeof braiinsData?.stats?.hashrate_5m === "number"
    ? `${braiinsData.stats.hashrate_5m.toFixed(2)} TH/s`
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          label="Workers Online"
          value={stats.online_miners || 0}
          onClick={() => navigate("/miners")}
          subtext={
            <>
              <div>
                Pool: {(() => {
                  // Aggregate hashrate from all active pools
                  let totalPoolHashrateGH = 0;
                  
                  // Solopool miners (hashrate_raw in H/s, need to convert)
                  totalPoolHashrateGH += sumSolopoolHashrate(solopoolData?.dgb_miners);
                  totalPoolHashrateGH += sumSolopoolHashrate(solopoolData?.bch_miners);
                  totalPoolHashrateGH += sumSolopoolHashrate(solopoolData?.bc2_miners);
                  totalPoolHashrateGH += sumSolopoolHashrate(solopoolData?.btc_miners);
                  
                  // Braiins (hashrate_raw in TH/s, convert to GH/s)
                  if (braiinsData?.stats?.hashrate_raw) {
                    totalPoolHashrateGH += braiinsData.stats.hashrate_raw * 1000;
                  }
                  
                  // formatHashrate expects H/s, convert from GH/s
                  return formatHashrate(totalPoolHashrateGH * 1e9);
                })()}
              </div>
              <div className="text-xs">
                ⚡ {(() => {
                  const minerHashrate = stats.total_hashrate_ghs || 0; // GH/s
                  
                  // Calculate total pool hashrate
                  let totalPoolHashrateGH = 0;
                  totalPoolHashrateGH += sumSolopoolHashrate(solopoolData?.dgb_miners);
                  totalPoolHashrateGH += sumSolopoolHashrate(solopoolData?.bch_miners);
                  totalPoolHashrateGH += sumSolopoolHashrate(solopoolData?.bc2_miners);
                  totalPoolHashrateGH += sumSolopoolHashrate(solopoolData?.btc_miners);
                  if (braiinsData?.stats?.hashrate_raw) {
                    totalPoolHashrateGH += braiinsData.stats.hashrate_raw * 1000;
                  }
                  
                  if (minerHashrate > 0 && totalPoolHashrateGH > 0) {
                    const efficiency = (totalPoolHashrateGH / minerHashrate) * 100;
                    
                    // Determine color based on efficiency thresholds
                    let color = '';
                    if (efficiency >= 95) {
                      color = 'text-green-500';
                    } else if (efficiency >= 85) {
                      color = 'text-yellow-500';
                    } else {
                      color = 'text-red-500';
                    }
                    
                    return <span className={color}>{efficiency.toFixed(0)}% of expected</span>;
                  }
                  return "Unavailable";
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
          subtext={
            <>
              <div>
                {bestShare.coin && (
                  <span className={`inline-block px-1.5 py-0.5 text-xs font-semibold rounded mr-2 ${
                    bestShare.coin === "BTC" ? "bg-orange-500 text-white" :
                    bestShare.coin === "BCH" ? "bg-green-500 text-white" :
                    bestShare.coin === "DGB" ? "bg-blue-500 text-white" :
                    bestShare.coin === "BC2" ? "bg-purple-500 text-white" :
                    "bg-gray-500 text-white"
                  }`}>
                    {bestShare.coin}
                  </span>
                )}
                Network diff: {formatNetworkDiff(bestShare.network_difficulty)}
              </div>
              <div className="text-xs">
                {formatTimeAgo(bestShare.time_ago_seconds)}
              </div>
            </>
          }
        />
      </div>

      {/* Pool Tiles */}
      <div className="space-y-3">
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
              chartData={formatChartData(chartsData?.charts?.dgb)}
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
              chartData={formatChartData(chartsData?.charts?.bc2)}
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
              chartData={formatChartData(chartsData?.charts?.btc)}
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
      </div>
    </div>
  );
}
