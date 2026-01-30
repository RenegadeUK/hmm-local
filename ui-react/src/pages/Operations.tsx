import { useQuery } from '@tanstack/react-query'
import { Activity, AlertCircle, Gauge, Layers, ServerCog, ShieldAlert, Sparkles } from 'lucide-react'

interface OperationsStatus {
  automation_rules: Array<{
    id: number
    name: string
    trigger_type: string
    trigger_config: Record<string, unknown>
    action_type: string
    action_config: Record<string, unknown>
    priority: number
  }>
  strategy: {
    enabled: boolean
    current_price_band: string | null
    last_action_time: string | null
    last_price_checked: number | null
    enrolled_miners: Array<{ id: number; name: string; type: string }>
  }
  ha: {
    unstable: boolean
    detail: {
      enabled: boolean
      last_success?: string | null
      downtime_start?: string | null
      alerts_sent?: number
    }
  }
  telemetry: {
    backlog_current: number
    metrics: {
      last_24h_date: string
      last_24h: {
        peak_concurrency: number
        max_backlog: number
      }
      since_boot: {
        peak_concurrency: number
        max_backlog: number
      }
    }
  }
  db_pool: {
    checked_out: number
    total_capacity: number
    utilization_percent: number
    high_water: {
      last_24h_date: string
      last_24h: {
        db_pool_in_use_peak: number
        db_pool_wait_count: number
        db_pool_wait_seconds_sum: number
        active_queries_peak: number
        slow_query_count: number
      }
      since_boot: {
        db_pool_in_use_peak: number
        db_pool_wait_count: number
        db_pool_wait_seconds_sum: number
        active_queries_peak: number
        slow_query_count: number
      }
    }
  }
  modes: {
    ramp_up: boolean
    throttling_writes: boolean
    ha_unstable: boolean
  }
}

export default function Operations() {
  const { data, isLoading, isError } = useQuery<OperationsStatus>({
    queryKey: ['operations-status'],
    queryFn: async () => {
      const response = await fetch('/api/operations/status')
      if (!response.ok) {
        throw new Error('Failed to load operations status')
      }
      return response.json()
    },
    refetchInterval: 5000
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Activity className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-200">
        Failed to load operations status.
      </div>
    )
  }

  const { automation_rules, strategy, ha, telemetry, db_pool, modes } = data

  const MiniSparkBars = ({
    values,
    labels,
    color = 'bg-blue-500'
  }: {
    values: number[]
    labels: string[]
    color?: string
  }) => {
    const max = Math.max(...values, 1)

    return (
      <div className="flex items-end gap-2">
        {values.map((value, index) => (
          <div key={`${labels[index]}-${index}`} className="flex flex-col items-center gap-1">
            <div className={`w-3 rounded-full ${color}`} style={{ height: `${(value / max) * 36 + 6}px` }} />
            <span className="text-[10px] text-gray-400">{labels[index]}</span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-800 bg-gradient-to-r from-blue-950/60 via-slate-900/80 to-gray-900/60 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <ServerCog className="h-7 w-7 text-blue-300" />
            <div>
              <h1 className="text-2xl font-bold text-white">Operations</h1>
              <p className="text-sm text-gray-400">Real-time system posture & decision trace</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${modes.ramp_up ? 'bg-yellow-900/40 text-yellow-300 border border-yellow-700/60' : 'bg-emerald-900/30 text-emerald-300 border border-emerald-700/40'}`}>
              {modes.ramp_up ? 'Ramp-up' : 'Stable'}
            </span>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${modes.throttling_writes ? 'bg-red-900/40 text-red-300 border border-red-700/60' : 'bg-slate-800/60 text-slate-300 border border-slate-700/40'}`}>
              {modes.throttling_writes ? 'Write Throttling' : 'Writes OK'}
            </span>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${modes.ha_unstable ? 'bg-orange-900/40 text-orange-300 border border-orange-700/60' : 'bg-slate-800/60 text-slate-300 border border-slate-700/40'}`}>
              {modes.ha_unstable ? 'HA Degraded' : 'HA Stable'}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-gray-900/80 rounded-xl p-5 border border-gray-800 shadow-lg shadow-blue-500/5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-400">Active automation rules</h3>
            <Layers className="h-4 w-4 text-blue-400" />
          </div>
          {automation_rules.length === 0 ? (
            <div className="text-sm text-gray-500">No active rules.</div>
          ) : (
            <ul className="space-y-2 text-sm">
              {automation_rules.map((rule) => (
                <li key={rule.id} className="rounded-md border border-gray-700 bg-gray-900/50 p-2">
                  <div className="text-white font-semibold">{rule.name}</div>
                  <div className="text-xs text-gray-400">
                    Trigger: {rule.trigger_type} • Action: {rule.action_type}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-gray-900/80 rounded-xl p-5 border border-gray-800 shadow-lg shadow-purple-500/5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-400">Current strategy per miner</h3>
            <Gauge className="h-4 w-4 text-purple-400" />
          </div>
          {strategy.enrolled_miners.length === 0 ? (
            <div className="text-sm text-gray-500">No miners enrolled.</div>
          ) : (
            <ul className="space-y-2 text-sm">
              {strategy.enrolled_miners.map((miner) => (
                <li key={miner.id} className="flex items-center justify-between rounded-md border border-gray-700 bg-gray-900/50 p-2">
                  <span className="text-white">{miner.name}</span>
                  <span className="text-xs text-gray-400">Agile Solo</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-gray-900/80 rounded-xl p-5 border border-gray-800 shadow-lg shadow-emerald-500/5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-400">Last decision</h3>
            <Activity className="h-4 w-4 text-green-400" />
          </div>
          <div className="space-y-2 text-sm">
            <div className="text-white">
              Band: {strategy.current_price_band ?? 'N/A'}
            </div>
            <div className="text-gray-400">
              Last action: {strategy.last_action_time ?? 'N/A'}
            </div>
            <div className="text-gray-400">
              Last price: {strategy.last_price_checked ?? 'N/A'}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className={`rounded-xl border p-4 ${modes.ramp_up ? 'border-yellow-700 bg-yellow-900/20' : 'border-gray-700 bg-gray-900/70'}`}>
          <div className="flex items-center gap-2">
            <AlertCircle className={`h-4 w-4 ${modes.ramp_up ? 'text-yellow-400' : 'text-gray-500'}`} />
            <span className="text-sm font-medium text-gray-200">System ramp-up</span>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {modes.ramp_up ? 'Telemetry backlog detected; system may be catching up.' : 'Normal telemetry cadence.'}
          </p>
        </div>

        <div className={`rounded-xl border p-4 ${modes.throttling_writes ? 'border-red-700 bg-red-900/20' : 'border-gray-700 bg-gray-900/70'}`}>
          <div className="flex items-center gap-2">
            <ShieldAlert className={`h-4 w-4 ${modes.throttling_writes ? 'text-red-400' : 'text-gray-500'}`} />
            <span className="text-sm font-medium text-gray-200">Write throttling</span>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {modes.throttling_writes ? 'DB pool usage is high; writes may be constrained.' : 'DB pool healthy.'}
          </p>
        </div>

        <div className={`rounded-xl border p-4 ${modes.ha_unstable ? 'border-orange-700 bg-orange-900/20' : 'border-gray-700 bg-gray-900/70'}`}>
          <div className="flex items-center gap-2">
            <AlertCircle className={`h-4 w-4 ${modes.ha_unstable ? 'text-orange-400' : 'text-gray-500'}`} />
            <span className="text-sm font-medium text-gray-200">HA unstable</span>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {modes.ha_unstable ? 'Home Assistant keepalive is unstable.' : 'Home Assistant stable.'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900/80 rounded-xl p-5 border border-gray-800">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-400">DB connections</h3>
            <Sparkles className="h-4 w-4 text-blue-400" />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold text-white">{db_pool.high_water.last_24h.db_pool_in_use_peak}</div>
              <p className="text-xs text-gray-500">24h peak • since {db_pool.high_water.last_24h_date}</p>
            </div>
            <MiniSparkBars
              values={[db_pool.checked_out, db_pool.high_water.last_24h.db_pool_in_use_peak, db_pool.high_water.since_boot.db_pool_in_use_peak]}
              labels={["Now", "24h", "Boot"]}
              color="bg-blue-500"
            />
          </div>
        </div>
        <div className="bg-gray-900/80 rounded-xl p-5 border border-gray-800">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-400">Miner concurrency</h3>
            <Sparkles className="h-4 w-4 text-purple-400" />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold text-white">{telemetry.metrics.last_24h.peak_concurrency}</div>
              <p className="text-xs text-gray-500">24h peak • since {telemetry.metrics.last_24h_date}</p>
            </div>
            <MiniSparkBars
              values={[telemetry.metrics.last_24h.peak_concurrency, telemetry.metrics.since_boot.peak_concurrency]}
              labels={["24h", "Boot"]}
              color="bg-purple-500"
            />
          </div>
        </div>
        <div className="bg-gray-900/80 rounded-xl p-5 border border-gray-800">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-400">Telemetry backlog</h3>
            <Sparkles className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold text-white">{telemetry.metrics.last_24h.max_backlog}</div>
              <p className="text-xs text-gray-500">24h peak • current {telemetry.backlog_current}</p>
            </div>
            <MiniSparkBars
              values={[telemetry.backlog_current, telemetry.metrics.last_24h.max_backlog, telemetry.metrics.since_boot.max_backlog]}
              labels={["Now", "24h", "Boot"]}
              color="bg-emerald-500"
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900/70 rounded-xl p-4 border border-gray-800">
          <h3 className="text-xs font-medium text-gray-400 mb-1">DB connections (since boot)</h3>
          <div className="text-xl font-bold text-white">
            {db_pool.high_water.since_boot.db_pool_in_use_peak}
          </div>
        </div>
        <div className="bg-gray-900/70 rounded-xl p-4 border border-gray-800">
          <h3 className="text-xs font-medium text-gray-400 mb-1">Miner concurrency (since boot)</h3>
          <div className="text-xl font-bold text-white">
            {telemetry.metrics.since_boot.peak_concurrency}
          </div>
        </div>
        <div className="bg-gray-900/70 rounded-xl p-4 border border-gray-800">
          <h3 className="text-xs font-medium text-gray-400 mb-1">Telemetry backlog (since boot)</h3>
          <div className="text-xl font-bold text-white">
            {telemetry.metrics.since_boot.max_backlog}
          </div>
        </div>
      </div>

      {ha.detail?.enabled && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 text-xs text-gray-500">
          HA last success: {ha.detail.last_success ?? 'N/A'} · Downtime start: {ha.detail.downtime_start ?? 'N/A'} · Alerts: {ha.detail.alerts_sent ?? 0}
        </div>
      )}
    </div>
  )
}
