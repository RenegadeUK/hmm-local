import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  type TooltipItem,
} from 'chart.js'
import 'chartjs-adapter-date-fns'
import { AlertTriangle, Clock, Info, Loader2, PlayCircle, TrendingUp, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'

// Register Chart.js components inside useEffect

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    ...init,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail || body.message || `Request failed (${response.status})`
    throw new Error(detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

type AutoOptimizationStatus = {
  enabled: boolean
  price_threshold: number
}

type Recommendation = {
  band: string
  mode: string
  current_price_pence: number
  cheap_threshold: number
  expensive_threshold: number
  recommendation: string
  valid_until: string
}

type MinerProfitability = {
  miner_id: number
  miner_name: string
  coin?: string
  avg_hashrate_ghs?: number | { display: string; value: number; unit: string }
  energy_cost_gbp: number
  revenue_gbp: number
  profit_gbp: number
  roi_percent?: number
  note?: string
}

type EnergyOverview = {
  total_miners: number
  total_energy_cost_24h: number
  total_profit_24h: number
  miners: MinerProfitability[]
  current_recommendation?: Recommendation
}

type PricePoint = {
  timestamp: string
  price_pence: number
  is_cheap: boolean
  is_expensive: boolean
}

type PriceForecast = {
  hours_ahead: number
  forecast: PricePoint[]
}

type MinerSummary = {
  id: number
  name: string
}

type ScheduleRecommendation = {
  miner_id: number
  target_hours: number
  recommended_slots: { timestamp: string; price_pence: number }[]
  avg_price_pence: number
  vs_random_avg: number
  savings_percent: number
}

function formatCurrencyGBP(value: number | undefined | null) {
  if (value === null || value === undefined) return '£0.00'
  return new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(value)
}

function formatPricePence(value: number | undefined) {
  if (value === undefined || value === null) return '—'
  return `${value.toFixed(1)} p/kWh`
}

function bandTone(band?: string) {
  switch (band) {
    case 'CHEAP':
      return 'text-green-300'
    case 'MODERATE':
      return 'text-amber-300'
    case 'EXPENSIVE':
      return 'text-red-300'
    default:
      return 'text-gray-300'
  }
}

function bandChipClasses(band?: string) {
  switch (band) {
    case 'CHEAP':
      return 'bg-green-500/10 text-green-300'
    case 'MODERATE':
      return 'bg-amber-500/10 text-amber-300'
    case 'EXPENSIVE':
      return 'bg-red-500/10 text-red-300'
    default:
      return 'bg-gray-600/20 text-gray-300'
  }
}

export default function EnergyOptimization() {
  // Register Chart.js components on component mount
  useEffect(() => {
    ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, TimeScale)
  }, [])

  const queryClient = useQueryClient()
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const [targetHours, setTargetHours] = useState('12')
  const [scheduleMinerId, setScheduleMinerId] = useState<number | ''>('')
  const [scheduleResult, setScheduleResult] = useState<ScheduleRecommendation | null>(null)

  const {
    data: autoStatus,
    isLoading: autoStatusLoading,
    error: autoStatusError,
  } = useQuery<AutoOptimizationStatus>({
    queryKey: ['auto-optimization-status'],
    queryFn: () => fetchJSON('/api/energy/auto-optimization/status'),
  })

  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
  } = useQuery<EnergyOverview>({
    queryKey: ['energy-overview'],
    queryFn: () => fetchJSON('/api/energy/overview'),
    refetchInterval: 60000,
  })

  const {
    data: forecast,
    isLoading: forecastLoading,
    error: forecastError,
  } = useQuery<PriceForecast>({
    queryKey: ['energy-forecast'],
    queryFn: () => fetchJSON('/api/energy/price-forecast?hours=24'),
    refetchInterval: 300000,
  })

  const {
    data: miners,
    isLoading: minersLoading,
  } = useQuery<MinerSummary[]>({
    queryKey: ['miners'],
    queryFn: () => fetchJSON('/api/miners/'),
  })

  const minerOptions = useMemo(() => (Array.isArray(miners) ? miners : []), [miners])
  const forecastPoints = useMemo(() => (Array.isArray(forecast?.forecast) ? forecast.forecast : []), [forecast])
  const scheduleSlots = Array.isArray(scheduleResult?.recommended_slots) ? scheduleResult?.recommended_slots : []

  useEffect(() => {
    if (minerOptions.length > 0 && scheduleMinerId === '') {
      setScheduleMinerId(minerOptions[0].id)
    }
  }, [minerOptions, scheduleMinerId])

  const toggleAutoMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      fetchJSON('/api/energy/auto-optimization/toggle', {
        method: 'POST',
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: (_, enabled) => {
      setBanner({ type: 'success', message: enabled ? 'Auto optimization enabled' : 'Auto optimization disabled' })
      queryClient.invalidateQueries({ queryKey: ['auto-optimization-status'] })
    },
    onError: (error: Error) => {
      setBanner({ type: 'error', message: error.message })
    },
  })

  const triggerAutoMutation = useMutation({
    mutationFn: () =>
      fetchJSON('/api/energy/auto-optimization/trigger', {
        method: 'POST',
      }),
    onSuccess: () => {
      setBanner({ type: 'success', message: 'Auto optimization job triggered. Check miner modes shortly.' })
      queryClient.invalidateQueries({ queryKey: ['energy-overview'] })
    },
    onError: (error: Error) => setBanner({ type: 'error', message: error.message }),
  })

  const scheduleMutation = useMutation({
    mutationFn: ({ minerId, hours }: { minerId: number; hours: number }) =>
      fetchJSON<ScheduleRecommendation>(
        `/api/energy/miners/${minerId}/schedule-recommendation?target_hours=${hours}`
      ),
    onSuccess: (data: ScheduleRecommendation) => {
      setScheduleResult(data)
    },
    onError: (error: Error) => {
      setScheduleResult(null)
      setBanner({ type: 'error', message: error.message })
    },
  })

  const chartData = useMemo(() => {
    if (!forecastPoints.length) {
      return null
    }

    return {
      labels: forecastPoints.map((point) => new Date(point.timestamp)),
      datasets: [
        {
          label: 'Price (p/kWh)',
          data: forecastPoints.map((point) => point.price_pence),
          borderColor: 'rgba(59, 130, 246, 1)',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          tension: 0.3,
          pointRadius: 0,
        },
      ],
    }
  }, [forecastPoints])

  const chartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (context: TooltipItem<'line'>) => {
            const yValue = typeof context.parsed?.y === 'number' ? context.parsed.y : 0
            return `${yValue.toFixed(2)} p/kWh`
          },
        },
      },
    },
    scales: {
      x: {
        type: 'time' as const,
        time: { unit: 'hour' as const },
        ticks: { maxRotation: 0 },
        grid: { color: 'rgba(255,255,255,0.05)' },
      },
      y: {
        beginAtZero: true,
        title: { display: true, text: 'p/kWh' },
        grid: { color: 'rgba(255,255,255,0.05)' },
      },
    },
  }), [])

  const handleToggle = () => {
    if (autoStatusLoading || !autoStatus) return
    toggleAutoMutation.mutate(!autoStatus.enabled)
  }

  const handleTrigger = () => {
    triggerAutoMutation.mutate()
  }

  const handleScheduleGenerate = () => {
    if (!scheduleMinerId || !targetHours.trim()) {
      setBanner({ type: 'error', message: 'Select a miner and number of hours first.' })
      return
    }

    const hoursValue = Number(targetHours)
    if (Number.isNaN(hoursValue) || hoursValue < 1 || hoursValue > 24) {
      setBanner({ type: 'error', message: 'Target hours must be between 1 and 24.' })
      return
    }

    scheduleMutation.mutate({ minerId: scheduleMinerId, hours: hoursValue })
  }

  const recommendation = overview?.current_recommendation

  const errors = [autoStatusError, overviewError, forecastError].filter(Boolean)

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-blue-300">
          <Zap className="h-5 w-5" />
          <span>Energy Optimization</span>
        </div>
        <h1 className="text-2xl font-semibold">Energy Optimization</h1>
        <p className="text-sm text-gray-400">
          Combine Octopus Agile pricing with real-time miner telemetry to keep profitability positive and power usage smart.
        </p>
        <div className="flex flex-wrap gap-3 pt-4">
          <Button
            onClick={handleToggle}
            disabled={autoStatusLoading || toggleAutoMutation.isPending}
            variant={autoStatus?.enabled ? 'default' : 'outline'}
            className="min-w-[190px]"
          >
            {autoStatus?.enabled ? 'Disable Auto Optimization' : 'Enable Auto Optimization'}
          </Button>
          <Button
            variant="secondary"
            onClick={handleTrigger}
            disabled={!autoStatus?.enabled || triggerAutoMutation.isPending}
            className="flex items-center gap-2"
          >
            {triggerAutoMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <PlayCircle className="h-4 w-4" />
            )}
            Run Now
          </Button>
        </div>
      </div>

      {banner && (
        <div
          className={cn(
            'rounded-md border px-4 py-3 text-sm',
            banner.type === 'success'
              ? 'border-green-500/40 bg-green-500/10 text-green-200'
              : 'border-red-500/40 bg-red-500/10 text-red-200'
          )}
        >
          {banner.message}
        </div>
      )}

      {errors.length > 0 && (
        <div className="flex items-center gap-3 rounded-md border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          <AlertTriangle className="h-4 w-4" />
          <span>{errors.map((err) => (err instanceof Error ? err.message : 'Unknown error')).join(' • ')}</span>
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-1">
            <h2 className="text-xl font-semibold">Automation Bands</h2>
            <p className="text-sm text-gray-400">
              CHEAP (&lt;15p) runs miners in High/OC mode, MODERATE (15-25p) shifts to Low/Eco, EXPENSIVE (≥25p) powers down
              linked Home Assistant devices to avoid negative ROI.
            </p>
          </div>
        </CardHeader>
        <CardContent>
          {autoStatus?.enabled ? (
            <div className="space-y-3 text-sm text-gray-300">
              <p>
                <strong className="text-green-300">Enabled:</strong> Scheduler reconciles miners every 5 minutes, applying band
                logic to Bitaxe, NerdQaxe++, and Avalon Nano devices plus their associated switches.
              </p>
              <p>
                <strong className="text-amber-300">Tip:</strong> Disable conflicting automation rules that also touch miner modes or HA devices.
              </p>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-gray-700 bg-gray-900/40 px-4 py-3 text-sm text-gray-400">
              Enable automatic optimization to orchestrate miners based on live Agile pricing.
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-gray-500">24h Energy Cost</p>
            <p className="mt-2 text-2xl font-semibold">{formatCurrencyGBP(overview?.total_energy_cost_24h)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-gray-500">24h Net Profit</p>
            <p
              className={cn(
                'mt-2 text-2xl font-semibold',
                (overview?.total_profit_24h ?? 0) >= 0 ? 'text-green-300' : 'text-red-300'
              )}
            >
              {formatCurrencyGBP(overview?.total_profit_24h)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-gray-500">Current Price</p>
            <p className={cn('mt-2 text-2xl font-semibold', bandTone(recommendation?.band))}>
              {formatPricePence(recommendation?.current_price_pence)}
            </p>
            <p className="text-xs text-gray-500">Valid until {recommendation?.valid_until && new Date(recommendation.valid_until).toLocaleTimeString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-gray-500">Recommendation</p>
            <div className="mt-2 flex items-center gap-2">
              <span className={cn('rounded-full px-2 py-0.5 text-xs font-semibold', bandChipClasses(recommendation?.band))}>
                {recommendation?.band || '—'}
              </span>
              <span className="text-sm text-gray-300">{recommendation?.recommendation || 'Waiting for data…'}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3 text-base font-semibold">
              <TrendingUp className="h-5 w-5 text-blue-300" /> 24-Hour Price Forecast
            </div>
          </CardHeader>
          <CardContent>
            {forecastLoading ? (
              <div className="flex min-h-[240px] items-center justify-center text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            ) : chartData ? (
              <div className="h-[260px]">
                <Line data={chartData} options={chartOptions} />
              </div>
            ) : (
              <p className="text-sm text-gray-500">No forecast data available.</p>
            )}
            <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-500">
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-green-400" /> Cheap &lt; 15p</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-400" /> Moderate 15-25p</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-400" /> Expensive ≥ 25p</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-3 text-base font-semibold">
              <Clock className="h-5 w-5 text-blue-300" /> Smart Schedule
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <p className="text-xs text-gray-400 uppercase">Target Miner</p>
                <Select
                  disabled={minersLoading || minerOptions.length === 0}
                  value={scheduleMinerId ? String(scheduleMinerId) : ''}
                  onValueChange={(value) => setScheduleMinerId(Number(value))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={minersLoading ? 'Loading miners…' : 'Select miner'} />
                  </SelectTrigger>
                  <SelectContent>
                    {minerOptions.map((miner) => (
                      <SelectItem key={miner.id} value={String(miner.id)}>
                        {miner.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <p className="text-xs text-gray-400 uppercase">Target Hours</p>
                <input
                  type="number"
                  min={1}
                  max={24}
                  value={targetHours}
                  onChange={(event) => setTargetHours(event.target.value)}
                  className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={handleScheduleGenerate}
                disabled={scheduleMutation.isPending || !scheduleMinerId}
                className="flex items-center gap-2"
              >
                {scheduleMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
                Generate Schedule
              </Button>
              <Button
                variant="outline"
                disabled={!scheduleResult}
                onClick={() => setScheduleResult(null)}
              >
                Clear
              </Button>
            </div>

            {scheduleResult && (
              <div className="space-y-3 rounded-md border border-blue-500/30 bg-blue-500/5 p-4 text-sm text-blue-100">
                <p>
                  Expected savings: <strong>{scheduleResult.savings_percent.toFixed(1)}%</strong> vs random schedule · Avg price
                  {` ${scheduleResult.avg_price_pence.toFixed(2)}p`}
                </p>
                <div className="max-h-[200px] space-y-2 overflow-y-auto pr-2">
                  {scheduleSlots.map((slot) => (
                    <div key={slot.timestamp} className="flex items-center justify-between rounded bg-gray-900/40 px-3 py-2 text-xs">
                      <span>{new Date(slot.timestamp).toLocaleString(undefined, { hour: '2-digit', minute: '2-digit', weekday: 'short' })}</span>
                      <span className="font-semibold">{slot.price_pence.toFixed(2)}p</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!scheduleResult && (
              <div className="rounded-md border border-dashed border-gray-700 bg-gray-900/40 px-4 py-3 text-sm text-gray-400">
                Pick a miner and desired runtime to see the cheapest 30-minute slots for the next 24 hours.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-3 text-base font-semibold">
            <Info className="h-5 w-5 text-blue-300" /> Per-Miner Profitability
          </div>
        </CardHeader>
        <CardContent>
          {overviewLoading ? (
            <div className="flex min-h-[200px] items-center justify-center text-gray-400">Loading profitability…</div>
          ) : overview?.miners?.length ? (
            <div className="max-h-[420px] overflow-auto rounded-lg border border-gray-800">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-gray-950/80">
                  <tr className="text-left text-xs uppercase text-gray-500">
                    <th className="px-4 py-3">Miner</th>
                    <th className="px-4 py-3">Coin</th>
                    <th className="px-4 py-3">Energy Cost</th>
                    <th className="px-4 py-3">Profit</th>
                    <th className="px-4 py-3">ROI</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.miners.map((miner) => (
                    <tr key={miner.miner_id} className="border-t border-gray-900/60">
                      <td className="px-4 py-3 text-gray-200">{miner.miner_name}</td>
                      <td className="px-4 py-3 text-gray-400">{miner.coin || '—'}</td>
                      <td className="px-4 py-3 text-gray-200">{formatCurrencyGBP(miner.energy_cost_gbp)}</td>
                      <td
                        className={cn(
                          'px-4 py-3 font-semibold',
                          miner.profit_gbp >= 0 ? 'text-green-300' : 'text-red-300'
                        )}
                      >
                        {formatCurrencyGBP(miner.profit_gbp)}
                      </td>
                      <td className="px-4 py-3 text-gray-400">{miner.roi_percent != null ? `${miner.roi_percent.toFixed(1)}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-gray-700 p-6 text-center text-sm text-gray-500">
              No profitability records yet. Ensure telemetry is flowing for each enrolled miner.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
