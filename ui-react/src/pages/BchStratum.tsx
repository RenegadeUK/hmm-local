import { useQuery } from '@tanstack/react-query'
import { StatsCard } from '@/components/widgets/StatsCard'
import { stratumAPI, type StratumStatusResponse } from '@/lib/api'

function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return 'N/A'
  const s = Math.max(0, Math.floor(seconds))
  const mins = Math.floor(s / 60)
  const hrs = Math.floor(mins / 60)
  const remMins = mins % 60
  if (hrs > 0) return `${hrs}h ${remMins}m`
  return `${mins}m`
}

export default function BchStratum() {
  const { data, isLoading, isError, error } = useQuery<StratumStatusResponse>({
    queryKey: ['stratum', 'BCH'],
    queryFn: () => stratumAPI.getStatus('BCH'),
    refetchInterval: 10000,
    refetchOnWindowFocus: false,
    staleTime: 8000,
  })

  if (isLoading) {
    return <div className="w-full py-10 text-center text-sm text-muted-foreground">Loading BCH Stratum…</div>
  }

  if (isError || !data) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return <div className="rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-200">Failed to load BCH Stratum: {message}</div>
  }

  const ready = data.ready?.ready === true
  const workers = data.computed.workers_online
  const hashrate = data.computed.hashrate
  const shares15m = data.computed.shares_15m
  const shares24h = data.computed.shares_24h
  const sharesTotal = data.computed.shares_total

  const lastBlock = data.computed.last_block_event

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">BCH Stratum</h1>
        <div className="text-sm text-muted-foreground">
          {data.pool.stratum.host}:{data.pool.stratum.port} • Manager: {data.pool.manager.base_url}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          label="Status"
          value={ready ? 'Ready' : 'Not Ready'}
          subtext={
            data.ready?.reasons && data.ready.reasons.length > 0
              ? data.ready.reasons.join(' • ')
              : undefined
          }
        />
        <StatsCard
          label="Workers"
          value={workers ?? 'N/A'}
          subtext={
            data.computed.workers_down_for_s && Number(data.computed.workers_down_for_s) > 0
              ? `Down for ${formatSeconds(Number(data.computed.workers_down_for_s))}`
              : (data.computed.workers_min_15m !== null && data.computed.workers_min_15m !== undefined)
                ? `15m min/max: ${data.computed.workers_min_15m}/${data.computed.workers_max_15m ?? data.computed.workers_min_15m}`
                : undefined
          }
        />
        <StatsCard
          label="Hashrate"
          value={hashrate && typeof hashrate === 'object' && 'display' in hashrate ? String(hashrate.display) : 'N/A'}
        />
        <StatsCard
          label="Shares"
          value={shares15m !== null && shares15m !== undefined ? `${Number(shares15m).toLocaleString()} (15m)` : 'N/A'}
          subtext={
            shares24h !== null && shares24h !== undefined
              ? `24h: ${Number(shares24h).toLocaleString()} • Total: ${Number(sharesTotal || 0).toLocaleString()}`
              : `Total: ${Number(sharesTotal || 0).toLocaleString()}`
          }
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <StatsCard
          label="Last Block Event"
          value={lastBlock?.timestamp ? new Date(String(lastBlock.timestamp)).toLocaleString() : 'None'}
          subtext={lastBlock?.message ? String(lastBlock.message) : undefined}
        />
        <StatsCard
          label="Node Cache"
          value={
            data.node?.mining?.age_seconds !== null && data.node?.mining?.age_seconds !== undefined
              ? `${Number(data.node.mining.age_seconds).toFixed(1)}s old`
              : 'N/A'
          }
          subtext={data.node?.mining?.error ? String(data.node.mining.error) : undefined}
        />
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="text-sm font-medium">Recent Events</div>
        <div className="mt-2 space-y-1 text-xs">
          {data.ckpool.events.length === 0 ? (
            <div className="text-muted-foreground">No recent events</div>
          ) : (
            data.ckpool.events.slice(0, 30).map((e, idx) => (
              <div key={idx} className="flex flex-wrap gap-x-2 gap-y-0.5">
                <span className="text-muted-foreground">{e.timestamp ? new Date(String(e.timestamp)).toLocaleTimeString() : ''}</span>
                <span className="font-semibold">{String(e.event_type || '')}</span>
                <span className="text-muted-foreground">{String(e.severity || '')}</span>
                <span>{String(e.message || '')}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
