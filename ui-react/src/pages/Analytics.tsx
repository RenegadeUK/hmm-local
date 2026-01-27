import { useQuery } from '@tanstack/react-query'
import { AlertCircle, TrendingDown, TrendingUp, Zap, DollarSign } from 'lucide-react'

interface MinerData {
  id: number
  name: string
  miner_type: string
  enabled: boolean
  is_offline: boolean
  hashrate: number
  hashrate_unit: string
  power: number
  cost_24h: number
  health_score: number | null
  efficiency_wth?: number | null
}

interface DashboardAllResponse {
  miners: MinerData[]
  stats: {
    total_miners: number
    active_miners: number
    online_miners: number
    total_power_watts: number
    total_cost_24h_pence: number
    total_cost_24h_pounds: number
    avg_efficiency_wth: number | null
  }
}

interface HealthMiner {
  miner_id: number
  miner_name: string
  miner_type: string
  timestamp: string
  health_score: number
  anomaly_score: number | null
  has_issues: boolean
  reasons: Array<{
    code: string
    severity: string
    metric?: string
    actual?: number
    expected_min?: number
    expected_max?: number
    unit?: string
  }>
}

interface HealthAllResponse {
  miners: HealthMiner[]
}

export function Analytics() {
  // Fetch power/cost summary from dashboard all (ASIC miners only, consistent with main dashboard)
  const { data: dashboardAll } = useQuery<DashboardAllResponse>({
    queryKey: ['dashboard-all-asic'],
    queryFn: async () => {
      const response = await fetch('/api/dashboard/all?dashboard_type=asic')
      if (!response.ok) throw new Error('Failed to fetch dashboard data')
      return response.json()
    },
    refetchInterval: 10000,
  })

  // Fetch health alerts (all miners with issues)
  const { data: healthAll } = useQuery<HealthAllResponse>({
    queryKey: ['health-all-analytics'],
    queryFn: async () => {
      const response = await fetch('/api/health/all')
      if (!response.ok) throw new Error('Failed to fetch health data')
      return response.json()
    },
    refetchInterval: 30000,
  })

  // Use stats from dashboardAll instead of separate call
  const stats = dashboardAll?.stats

  const getEfficiencyColor = (efficiency: number): string => {
    if (efficiency < 50) return 'text-green-600'
    if (efficiency < 100) return 'text-yellow-600'
    return 'text-red-600'
  }

  const getEfficiencyBg = (efficiency: number): string => {
    if (efficiency < 50) return 'bg-green-100'
    if (efficiency < 100) return 'bg-yellow-100'
    return 'bg-red-100'
  }

  const getSeverityColor = (severity: string): string => {
    switch (severity) {
      case 'critical':
        return 'bg-red-100 text-red-800'
      case 'warning':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-blue-100 text-blue-800'
    }
  }

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp)
    return date.toLocaleString('en-GB', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  // Calculate efficiency and sort miners (show all miners with valid data, including last known values)
  const sortedMiners = dashboardAll?.miners
    ? [...dashboardAll.miners]
        .filter((m) => m.hashrate > 0 && m.power > 0) // Show offline miners if they have last known data
        .map((m) => ({
          ...m,
          efficiency_wth: (m.power / (m.hashrate / 1000.0)), // W / TH
        }))
        .sort((a, b) => (a.efficiency_wth || 0) - (b.efficiency_wth || 0))
    : []

  // Filter alerts to only show miners with health issues
  const alertMiners = healthAll?.miners?.filter((m) => m.has_issues) || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
      </div>

      {/* Power/Cost Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Zap className="h-4 w-4" />
            Total Power
          </div>
          <div className="mt-2 text-2xl font-bold">
            {stats?.total_power_watts.toFixed(0) ?? '-'} W
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {stats?.online_miners ?? 0} / {stats?.total_miners ?? 0} miners online{stats?.online_miners === 0 ? ' (OFF due to pricing)' : ''}
          </div>
        </div>

        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <DollarSign className="h-4 w-4" />
            24h Cost
          </div>
          <div className="mt-2 text-2xl font-bold">
            £{stats?.total_cost_24h_pounds.toFixed(2) ?? '-'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            ASIC miners only
          </div>
        </div>

        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <TrendingDown className="h-4 w-4" />
            Avg Efficiency
          </div>
          <div className="mt-2 text-2xl font-bold">
            {stats?.avg_efficiency_wth ? stats.avg_efficiency_wth.toFixed(1) : '-'} W/TH
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Fleet average
          </div>
        </div>

        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <AlertCircle className="h-4 w-4" />
            Alerts
          </div>
          <div className="mt-2 text-2xl font-bold">
            {alertMiners.length}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Miners with issues
          </div>
        </div>
      </div>

      {/* Efficiency Leaderboard */}
      <div className="rounded-lg border bg-card">
        <div className="border-b p-4">
          <h2 className="text-lg font-semibold">Efficiency Leaderboard (W/TH)</h2>
          <p className="text-sm text-muted-foreground">Lower is better - ordered by efficiency</p>
        </div>
        <div className="p-4">
          {sortedMiners.length > 0 ? (
            <div className="space-y-3">
              {sortedMiners.map((miner, index) => (
                <div
                  key={miner.id}
                  className="flex items-center justify-between rounded-lg border p-4"
                >
                  <div className="flex items-center gap-4">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted font-bold text-muted-foreground">
                      {index + 1}
                    </div>
                    <div>
                      <div className="font-medium">{miner.name}</div>
                      <div className="text-sm text-muted-foreground">
                        {miner.hashrate.toFixed(2)} {miner.hashrate_unit} · {miner.power.toFixed(0)}W
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div
                      className={`rounded-full px-3 py-1 text-sm font-semibold ${getEfficiencyBg(
                        miner.efficiency_wth!
                      )} ${getEfficiencyColor(miner.efficiency_wth!)}`}
                    >
                      {miner.efficiency_wth!.toFixed(1)} W/TH
                    </div>
                    {index === 0 && <TrendingUp className="h-5 w-5 text-green-600" />}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center">
              <div className="text-muted-foreground mb-2">
                No efficiency data available
              </div>
              <div className="text-sm text-muted-foreground">
                Miners are currently OFF due to Agile pricing (£{(stats?.current_energy_price_pence ?? 0) / 100}\nper kWh)
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                They will automatically turn ON when electricity is cheaper
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Alerts/Anomalies Timeline */}
      <div className="rounded-lg border bg-card">
        <div className="border-b p-4">
          <h2 className="text-lg font-semibold">Current Health Issues</h2>
          <p className="text-sm text-muted-foreground">Miners with detected anomalies</p>
        </div>
        <div className="p-4">
          {alertMiners.length > 0 ? (
            <div className="space-y-3">
              {alertMiners.map((alert, index) => (
                <div key={`${alert.miner_id}-${index}`} className="rounded-lg border p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{alert.miner_name}</span>
                        <span className="text-sm text-muted-foreground">
                          {formatTimestamp(alert.timestamp)}
                        </span>
                      </div>
                      <div className="mt-2 flex items-center gap-3">
                        <span className="text-sm">
                          Health: <span className="font-semibold">{alert.health_score}</span>
                        </span>
                        {alert.anomaly_score !== null && (
                          <span className="text-sm">
                            Anomaly: <span className="font-semibold">{alert.anomaly_score.toFixed(2)}</span>
                          </span>
                        )}
                      </div>
                      {alert.reasons && alert.reasons.length > 0 && (
                        <div className="mt-3 space-y-2">
                          {alert.reasons.map((reason, idx) => (
                            <div
                              key={idx}
                              className={`inline-flex items-center gap-2 rounded px-2 py-1 text-sm ${getSeverityColor(
                                reason.severity
                              )} mr-2`}
                            >
                              <AlertCircle className="h-3 w-3" />
                              <span className="font-medium">{reason.code.replace(/_/g, ' ')}</span>
                              {reason.metric && reason.actual !== undefined && (
                                <span className="text-xs">
                                  {reason.metric}: {reason.actual}
                                  {reason.expected_min !== undefined && reason.expected_max !== undefined &&
                                    ` (expected: ${reason.expected_min}-${reason.expected_max})`}
                                  {reason.unit && ` ${reason.unit}`}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center">
              <div className="text-muted-foreground">
                {stats?.online_miners === 0 
                  ? 'All miners are OFF due to high electricity prices (no telemetry available)'
                  : 'All systems healthy! 🎉'
                }
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
