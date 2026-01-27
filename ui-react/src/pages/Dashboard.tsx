import { StatsCard } from "@/components/widgets/StatsCard";
import { PoolTile } from "@/components/widgets/PoolTile";
import { BraiinsTile } from "@/components/widgets/BraiinsTile";
import { useQuery } from "@tanstack/react-query";
import { dashboardAPI, poolsAPI } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { formatHashrate } from "@/lib/utils";

export function Dashboard() {
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", "all"],
    queryFn: () => dashboardAPI.getAll("asic"),
    refetchInterval: 5000, // Refresh every 5 seconds
  });

  const { data: solopoolData } = useQuery({
    queryKey: ["pools", "solopool"],
    queryFn: () => poolsAPI.getSolopoolStats(),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  const { data: braiinsData } = useQuery({
    queryKey: ["pools", "braiins"],
    queryFn: () => poolsAPI.getBraiinsStats(),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

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

  const stats = data?.stats || {} as any;
  const bestShare = stats?.best_share_24h || {} as any;

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
              <div>Pool: {formatHashrate(stats.total_pool_hashrate_ghs || 0)}</div>
              <div className="text-xs">
                ⚡ {stats.pool_efficiency_percent 
                  ? `${stats.pool_efficiency_percent.toFixed(1)}%` 
                  : "Unavailable"}
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
            {solopoolData.dgb_miners?.filter((m: any) => 
              solopoolData.strategy_enabled 
                ? m.is_strategy_pool 
                : (m.stats?.workers > 0 && m.stats?.hashrate_raw > 0)
            ).map((miner: any) => (
            <PoolTile
              key={`dgb-${miner.username}`}
              coin="DGB"
              workersOnline={miner.stats?.workers || 0}
              hashrate={miner.stats?.hashrate || ""}
              currentLuck={miner.stats?.current_luck || null}
              ettb={miner.stats?.ettb?.formatted || null}
              lastBlockTime={miner.stats?.lastBlockTimestamp ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastBlockTimestamp) : null}
              blocks24h={miner.stats?.blocks_24h || 0}
              blocks7d={miner.stats?.blocks_7d || 0}
              blocks30d={miner.stats?.blocks_30d || 0}
              shares={miner.stats?.shares || 0}
              lastShare={miner.stats?.lastShare ? formatTimeAgo(miner.stats.lastShare) : null}
              totalPaid={`${(miner.stats?.paid ? miner.stats.paid / 1000000000 : 0).toFixed(8)} DGB`}
              paidValue={`£${miner.stats?.paid_gbp || "0.00"}`}
              accountUrl={`https://dgb-sha.solopool.org/account/${miner.username}`}
              isStrategyActive={miner.is_active_target}
              isStrategyInactive={miner.is_strategy_pool && !miner.is_active_target}
            />
          ))}

          {/* BCH Pools */}
          {solopoolData.bch_miners?.filter((m: any) => 
            solopoolData.strategy_enabled 
              ? m.is_strategy_pool 
              : (m.stats?.workers > 0 && m.stats?.hashrate_raw > 0)
          ).map((miner: any) => (
            <PoolTile
              key={`bch-${miner.username}`}
              coin="BCH"
              workersOnline={miner.stats?.workers || 0}
              hashrate={miner.stats?.hashrate || ""}
              currentLuck={miner.stats?.current_luck || null}
              ettb={miner.stats?.ettb?.formatted || null}
              lastBlockTime={miner.stats?.lastBlockTimestamp ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastBlockTimestamp) : null}
              blocks24h={miner.stats?.blocks_24h || 0}
              blocks7d={miner.stats?.blocks_7d || 0}
              blocks30d={miner.stats?.blocks_30d || 0}
              shares={miner.stats?.shares || 0}
              lastShare={miner.stats?.lastShare ? formatTimeAgo(miner.stats.lastShare) : null}
              totalPaid={`${(miner.stats?.paid ? miner.stats.paid / 100000000 : 0).toFixed(8)} BCH`}
              paidValue={`£${miner.stats?.paid_gbp || "0.00"}`}
              accountUrl={`https://bch.solopool.org/account/${miner.username}`}
              isStrategyActive={miner.is_active_target}
              isStrategyInactive={miner.is_strategy_pool && !miner.is_active_target}
            />
          ))}

          {/* BC2 Pools */}
          {solopoolData.bc2_miners?.filter((m: any) => 
            solopoolData.strategy_enabled 
              ? m.is_strategy_pool 
              : (m.stats?.workers > 0 && m.stats?.hashrate_raw > 0)
          ).map((miner: any) => (
            <PoolTile
              key={`bc2-${miner.username}`}
              coin="BC2"
              workersOnline={miner.stats?.workers || 0}
              hashrate={miner.stats?.hashrate || ""}
              currentLuck={miner.stats?.current_luck || null}
              ettb={miner.stats?.ettb?.formatted || null}
              lastBlockTime={miner.stats?.lastBlockTimestamp ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastBlockTimestamp) : null}
              blocks24h={miner.stats?.blocks_24h || 0}
              blocks7d={miner.stats?.blocks_7d || 0}
              blocks30d={miner.stats?.blocks_30d || 0}
              shares={miner.stats?.shares || 0}
              lastShare={miner.stats?.lastShare ? formatTimeAgo(miner.stats.lastShare) : null}
              totalPaid={`${(miner.stats?.paid ? miner.stats.paid / 100000000 : 0).toFixed(8)} BC2`}
              paidValue={`£${miner.stats?.paid_gbp || "0.00"}`}
              accountUrl={`https://bc2.solopool.org/account/${miner.username}`}
              isStrategyActive={miner.is_active_target}
              isStrategyInactive={miner.is_strategy_pool && !miner.is_active_target}
            />
          ))}

          {/* BTC Pools */}
          {solopoolData.btc_miners?.filter((m: any) => 
            solopoolData.strategy_enabled 
              ? m.is_strategy_pool 
              : (m.stats?.workers > 0 && m.stats?.hashrate_raw > 0)
          ).map((miner: any) => (
            <PoolTile
              key={`btc-${miner.username}`}
              coin="BTC"
              workersOnline={miner.stats?.workers || 0}
              hashrate={miner.stats?.hashrate || ""}
              currentLuck={miner.stats?.current_luck || null}
              ettb={miner.stats?.ettb?.formatted || null}
              lastBlockTime={miner.stats?.lastBlockTimestamp ? formatTimeAgo(Math.floor(Date.now() / 1000) - miner.stats.lastBlockTimestamp) : null}
              blocks24h={miner.stats?.blocks_24h || 0}
              blocks7d={miner.stats?.blocks_7d || 0}
              blocks30d={miner.stats?.blocks_30d || 0}
              shares={miner.stats?.shares || 0}
              lastShare={miner.stats?.lastShare ? formatTimeAgo(miner.stats.lastShare) : null}
              totalPaid={`${(miner.stats?.paid ? miner.stats.paid / 100000000 : 0).toFixed(8)} BTC`}
              paidValue={`£${miner.stats?.paid_gbp || "0.00"}`}
              accountUrl={`https://btc.solopool.org/account/${miner.username}`}
              isStrategyActive={miner.is_active_target}
              isStrategyInactive={miner.is_strategy_pool && !miner.is_active_target}
            />
          ))}
          </>
        )}

        {/* Braiins Pool */}
        {braiinsData && braiinsData.enabled && braiinsData.stats && 
          (solopoolData?.strategy_enabled 
            ? braiinsData.is_strategy_active || braiinsData.show_always
            : (braiinsData.stats.workers_online > 0 && braiinsData.stats.hashrate_raw > 0)
          ) && (
          <BraiinsTile
            workersOnline={braiinsData.stats.workers_online || 0}
            workersOffline={braiinsData.stats.workers_offline || 0}
            hashrate5m={braiinsData.stats.hashrate_5m || null}
            hashrateRaw={braiinsData.stats.hashrate_raw || 0}
            currentBalance={braiinsData.stats.current_balance || 0}
            todayReward={braiinsData.stats.today_reward || 0}
            allTimeReward={braiinsData.stats.all_time_reward || 0}
            username={braiinsData.username || ""}
            btcPriceGBP={braiinsData.btc_price_gbp || 0}
            isStrategyActive={braiinsData.is_strategy_active}
            isStrategyInactive={braiinsData.show_always && !braiinsData.is_strategy_active}
          />
        )}
      </div>
    </div>
  );
}
