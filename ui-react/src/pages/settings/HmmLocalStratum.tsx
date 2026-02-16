import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, CheckCircle2, RefreshCw, Waves } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { poolsAPI, type PoolRecoveryStatusPool, type PoolTileSet, type PoolTilesResponse } from '@/lib/api'

const STRATUM_POOL_TYPE = 'hmm_local_stratum'

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 'N/A'
  }
  return `${value.toFixed(2)}%`
}

function formatHashrate(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 'N/A'
  }

  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)} EH/s`
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)} PH/s`
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)} TH/s`
  }
  return `${value.toFixed(2)} GH/s`
}

function formatTimeAgo(iso: string | null): string {
  if (!iso) {
    return 'Unknown'
  }

  const timestamp = new Date(iso).getTime()
  if (Number.isNaN(timestamp)) {
    return iso
  }

  const deltaSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (deltaSeconds < 60) {
    return `${deltaSeconds}s ago`
  }

  const deltaMinutes = Math.floor(deltaSeconds / 60)
  if (deltaMinutes < 60) {
    return `${deltaMinutes}m ago`
  }

  const deltaHours = Math.floor(deltaMinutes / 60)
  if (deltaHours < 24) {
    return `${deltaHours}h ago`
  }

  const deltaDays = Math.floor(deltaHours / 24)
  return `${deltaDays}d ago`
}

export default function HmmLocalStratum() {
  const tilesQuery = useQuery<PoolTilesResponse>({
    queryKey: ['integrations', 'hmm-local-stratum', 'tiles'],
    queryFn: () => poolsAPI.getPoolTiles(),
    refetchInterval: 30000,
    refetchOnWindowFocus: false,
    staleTime: 25000,
  })

  const recoveryQuery = useQuery({
    queryKey: ['integrations', 'hmm-local-stratum', 'recovery-status'],
    queryFn: () => poolsAPI.getRecoveryStatus(24),
    refetchInterval: 30000,
    refetchOnWindowFocus: false,
    staleTime: 25000,
  })

  const stratumPools = useMemo(() => {
    return Object.values(tilesQuery.data || {}).filter(
      (tile): tile is PoolTileSet => tile.pool_type === STRATUM_POOL_TYPE
    )
  }, [tilesQuery.data])

  const recoveryByPoolId = useMemo(() => {
    const map = new Map<number, PoolRecoveryStatusPool>()
    for (const pool of recoveryQuery.data?.pools || []) {
      map.set(pool.pool_id, pool)
    }
    return map
  }, [recoveryQuery.data?.pools])

  const summary = useMemo(() => {
    const workersOnline = stratumPools.reduce((total, pool) => {
      return total + (pool.tile_2_network.active_workers || 0)
    }, 0)

    const rejectRates = stratumPools
      .map((pool) => pool.tile_3_shares.reject_rate)
      .filter((rate): rate is number => typeof rate === 'number' && Number.isFinite(rate))

    const maxRejectRate = rejectRates.length > 0 ? Math.max(...rejectRates) : null
    const unhealthyPools = stratumPools.filter((pool) => pool.tile_1_health.health_status === false).length

    const recoveryTotals = stratumPools.reduce(
      (acc, pool) => {
        const poolId = Number.parseInt(pool.pool_id, 10)
        const recovery = Number.isNaN(poolId) ? undefined : recoveryByPoolId.get(poolId)
        acc.recovered += recovery?.recovered_count || 0
        acc.unresolved += recovery?.unresolved_count || 0
        return acc
      },
      { recovered: 0, unresolved: 0 }
    )

    return {
      workersOnline,
      maxRejectRate,
      unhealthyPools,
      recovered: recoveryTotals.recovered,
      unresolved: recoveryTotals.unresolved,
    }
  }, [recoveryByPoolId, stratumPools])

  if (tilesQuery.isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Activity className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    )
  }

  if (tilesQuery.isError) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3 text-3xl font-semibold text-foreground">
          <Waves className="h-8 w-8 text-blue-400" />
          <span>HMM-Local Stratum</span>
        </div>
        <div className="rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-200">
          Failed to load Stratum operational data.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 text-3xl font-semibold text-foreground">
          <Waves className="h-8 w-8 text-blue-400" />
          <span>HMM-Local Stratum</span>
        </div>
        <p className="text-base text-muted-foreground">
          Dedicated operational view for local Stratum integration pools.
        </p>
      </div>

      {stratumPools.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>No HMM-Local Stratum pool configured</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              Add or update a pool with driver <span className="font-semibold text-foreground">hmm_local_stratum</span> to populate this page.
            </p>
            <div>
              <Link className="text-blue-400 hover:text-blue-300 underline" to="/pools">
                Go to Pools
              </Link>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Configured pools</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold">{stratumPools.length}</div>
                <p className="mt-1 text-xs text-muted-foreground">{summary.unhealthyPools} degraded</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Workers online</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold">{summary.workersOnline}</div>
                <p className="mt-1 text-xs text-muted-foreground">Across all Stratum pools</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Max reject rate</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold">{formatPercent(summary.maxRejectRate)}</div>
                <p className="mt-1 text-xs text-muted-foreground">24h tile feed</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Driver recoveries (24h)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold">{summary.recovered}</div>
                <p className="mt-1 text-xs text-muted-foreground">{summary.unresolved} unresolved</p>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            {stratumPools.map((pool) => {
              const poolId = Number.parseInt(pool.pool_id, 10)
              const recovery = Number.isNaN(poolId) ? undefined : recoveryByPoolId.get(poolId)

              return (
                <Card key={pool.pool_id}>
                  <CardHeader className="space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <CardTitle className="text-lg">{pool.display_name}</CardTitle>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900/60 px-2 py-1 text-slate-300">
                          <RefreshCw className="h-3 w-3" /> Updated {formatTimeAgo(pool.last_updated)}
                        </span>
                        {pool.tile_1_health.health_status ? (
                          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-700/50 bg-emerald-900/30 px-2 py-1 text-emerald-300">
                            <CheckCircle2 className="h-3 w-3" /> Healthy
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full border border-amber-700/60 bg-amber-900/30 px-2 py-1 text-amber-300">
                            <AlertTriangle className="h-3 w-3" /> Degraded
                          </span>
                        )}
                      </div>
                    </div>
                    {(pool.warnings || []).length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {(pool.warnings || []).map((warning) => (
                          <span
                            key={`${pool.pool_id}-${warning}`}
                            className="inline-flex rounded-full border border-amber-700/60 bg-amber-900/30 px-2 py-1 text-xs text-amber-300"
                          >
                            {warning}
                          </span>
                        ))}
                      </div>
                    )}
                  </CardHeader>

                  <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 p-3">
                      <div className="text-xs uppercase tracking-wide text-slate-400">Tile 1 · Health</div>
                      <div className="mt-1 text-sm text-slate-100">{pool.tile_1_health.health_message || 'No message'}</div>
                      <div className="mt-1 text-xs text-slate-400">Latency: {pool.tile_1_health.latency_ms ?? 'N/A'} ms</div>
                    </div>

                    <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 p-3">
                      <div className="text-xs uppercase tracking-wide text-slate-400">Tile 2 · Network</div>
                      <div className="mt-1 text-sm text-slate-100">Workers: {pool.tile_2_network.active_workers ?? 'N/A'}</div>
                      <div className="mt-1 text-xs text-slate-400">Hashrate: {formatHashrate(pool.tile_2_network.pool_hashrate)}</div>
                      <div className="text-xs text-slate-400">Pool share: {formatPercent(pool.tile_2_network.pool_percentage)}</div>
                    </div>

                    <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 p-3">
                      <div className="text-xs uppercase tracking-wide text-slate-400">Tile 3 · Shares</div>
                      <div className="mt-1 text-sm text-slate-100">Reject rate: {formatPercent(pool.tile_3_shares.reject_rate)}</div>
                      <div className="mt-1 text-xs text-slate-400">
                        Valid {pool.tile_3_shares.shares_valid ?? 'N/A'} · Invalid {pool.tile_3_shares.shares_invalid ?? 'N/A'}
                      </div>
                    </div>

                    <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 p-3">
                      <div className="text-xs uppercase tracking-wide text-slate-400">Tile 4 · Blocks</div>
                      <div className="mt-1 text-sm text-slate-100">Blocks 24h: {pool.tile_4_blocks.blocks_found_24h ?? 'N/A'}</div>
                      <div className="mt-1 text-xs text-slate-400">Currency: {pool.tile_4_blocks.currency || 'N/A'}</div>
                      <div className="text-xs text-slate-400">
                        Recovery: +{recovery?.recovered_count || 0} / unresolved {recovery?.unresolved_count || 0}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
