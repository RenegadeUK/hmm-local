import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import annotationPlugin from 'chartjs-plugin-annotation'
import 'chartjs-adapter-date-fns'
import { Activity, ArrowDownRight, ArrowUpRight, CalendarRange, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, TimeScale, annotationPlugin)

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

const DAY_OPTIONS = [
  { value: '3', label: '3 days' },
  { value: '5', label: '5 days' },
  { value: '7', label: '7 days' },
]

type ForecastSlot = {
  start: string
  end: string
  price_pred_pence: number | null
  price_low_pence: number | null
  price_high_pence: number | null
}

type ForecastDay = {
  date: string
  slots: ForecastSlot[]
}

type ForecastSummary = {
  slot_count: number
  average_price_pence: number | null
  cheapest_slot: ForecastSlot | null
  most_expensive_slot: ForecastSlot | null
}

type ForecastResponse = {
  region: string
  forecast_created_at: string | null
  days: ForecastDay[]
  summary: ForecastSummary
}

function formatSlot(slot?: ForecastSlot | null) {
  if (!slot) return '—'
  const start = new Date(slot.start)
  const time = start.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  const day = start.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  const price = slot.price_pred_pence?.toFixed(2)
  return `${price ?? '—'} p/kWh • ${day} ${time}`
}

function formatUpdated(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return date.toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })
}

function averagePrice(slots: ForecastSlot[]) {
  const numeric = slots.map((slot) => slot.price_pred_pence).filter((price): price is number => typeof price === 'number')
  if (!numeric.length) return null
  const total = numeric.reduce((sum, price) => sum + price, 0)
  return Number((total / numeric.length).toFixed(2))
}

export default function AgilePredict() {
  const [dayRange, setDayRange] = useState('7')
  const {
    data,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useQuery<ForecastResponse>({
    queryKey: ['agile-forecast', dayRange],
    queryFn: () => fetchJSON(`/api/energy/agile-forecast?days=${dayRange}`),
    refetchInterval: 300000,
  })

  const slotPoints = useMemo(() => {
    if (!data?.days?.length) return []
    return data.days.flatMap((day) =>
      day.slots
        .filter((slot) => typeof slot.price_pred_pence === 'number')
        .map((slot) => ({
          timestamp: slot.start,
          price: slot.price_pred_pence as number,
        }))
    )
  }, [data])

  const chartData = useMemo(() => {
    if (!slotPoints.length) return null
    return {
      labels: slotPoints.map((slot) => new Date(slot.timestamp)),
      datasets: [
        {
          label: 'Predicted price',
          data: slotPoints.map((slot) => slot.price),
          borderColor: 'rgba(59, 130, 246, 1)',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          tension: 0.35,
          pointRadius: 0,
        },
      ],
    }
  }, [slotPoints])

  const chartOptions = useMemo(
    () => ({
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
        annotation: {
          annotations: {
            line19p: {
              type: 'line' as const,
              yMin: 19,
              yMax: 19,
              borderColor: 'rgba(234, 179, 8, 0.7)',
              borderWidth: 2,
              borderDash: [6, 6],
              label: {
                display: true,
                content: '19p/kWh',
                position: 'end' as const,
                backgroundColor: 'rgba(234, 179, 8, 0.2)',
                color: 'rgba(234, 179, 8, 1)',
                font: { size: 11 },
                padding: 4,
              },
            },
            line30p: {
              type: 'line' as const,
              yMin: 30,
              yMax: 30,
              borderColor: 'rgba(239, 68, 68, 0.7)',
              borderWidth: 2,
              borderDash: [6, 6],
              label: {
                display: true,
                content: '30p/kWh',
                position: 'end' as const,
                backgroundColor: 'rgba(239, 68, 68, 0.2)',
                color: 'rgba(239, 68, 68, 1)',
                font: { size: 11 },
                padding: 4,
              },
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
          beginAtZero: false,
          title: { display: true, text: 'p/kWh' },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
      },
    }),
    []
  )

  const dayCards = data?.days ?? []
  const summary = data?.summary

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-blue-300">
          <Sparkles className="h-5 w-5" />
          <span>Agile Predict</span>
        </div>
        <h1 className="text-2xl font-semibold">7-Day Agile Forecast</h1>
        <p className="text-sm text-gray-400">
          Ingested directly from AgilePredict.com with daily refresh windows at 04:30. Use the forecast to pre-stage automation rules, power plans, and miner bands.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-4 border-b border-border/50 bg-muted/10 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-widest text-blue-300">Forecast Controls</p>
            <CardTitle className="text-xl">Region {data?.region ?? '—'}</CardTitle>
            <p className="text-sm text-muted-foreground">Last updated {formatUpdated(data?.forecast_created_at)}</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Select value={dayRange} onValueChange={setDayRange}>
              <SelectTrigger className="w-full sm:w-32">
                <SelectValue placeholder="Days" />
              </SelectTrigger>
              <SelectContent>
                {DAY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={() => refetch()} variant="secondary" disabled={isFetching} className="gap-2">
              {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="py-6">
          {error && (
            <div className="flex items-center gap-3 rounded-md border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              <Activity className="h-4 w-4" />
              <span>{error instanceof Error ? error.message : 'Unable to load Agile Predict forecast.'}</span>
            </div>
          )}
          {isLoading ? (
            <div className="flex items-center gap-3 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading forecast…
            </div>
          ) : null}
        </CardContent>
      </Card>

      {summary && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="p-5">
              <p className="text-xs uppercase text-gray-500">Average price</p>
              <p className="mt-2 text-3xl font-semibold">
                {summary.average_price_pence ? `${summary.average_price_pence.toFixed(2)} p/kWh` : '—'}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs uppercase text-gray-500">Total slots</p>
              <p className="mt-2 text-3xl font-semibold">{summary.slot_count}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs uppercase text-gray-500">Cheapest slot</p>
              <p className="mt-2 text-sm text-muted-foreground">{formatSlot(summary.cheapest_slot)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs uppercase text-gray-500">Most expensive</p>
              <p className="mt-2 text-sm text-muted-foreground">{formatSlot(summary.most_expensive_slot)}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {chartData && (
        <Card>
          <CardHeader>
            <CardTitle>Price trajectory</CardTitle>
            <p className="text-sm text-muted-foreground">Predicted half-hour slots over the selected window.</p>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <Line data={chartData} options={chartOptions} aria-label="Agile forecast chart" />
            </div>
          </CardContent>
        </Card>
      )}

      {chartData && dayCards.length > 0 && (
        <div className="rounded-md border border-border/40 bg-muted/5 p-4">
          <div className="flex divide-x divide-border/30">
            {dayCards.map((day) => {
              const weekday = new Date(day.date).toLocaleDateString('en-GB', { weekday: 'long' })
              return (
                <div key={day.date} className="flex-1 px-3 text-center text-sm">
                  <div className="mb-2 h-4 w-px bg-blue-500/70 mx-auto" />
                  <p className="font-medium text-gray-200">{weekday}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(day.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="space-y-4">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-blue-300">
          <CalendarRange className="h-5 w-5" />
          <span>Daily breakdown</span>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {dayCards.map((day) => {
            const dayAverage = averagePrice(day.slots)
            const cheapest = [...day.slots].sort((a, b) => (a.price_pred_pence ?? Infinity) - (b.price_pred_pence ?? Infinity))[0]
            const expensive = [...day.slots].sort((a, b) => (b.price_pred_pence ?? -Infinity) - (a.price_pred_pence ?? -Infinity))[0]

            return (
              <Card key={day.date} className="border-border/60">
                <CardHeader>
                  <CardTitle className="text-lg">{new Date(day.date).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}</CardTitle>
                  <p className="text-sm text-muted-foreground">Average {dayAverage ? `${dayAverage.toFixed(2)} p/kWh` : '—'}</p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
                      <div className="flex items-center gap-2 text-emerald-300">
                        <ArrowDownRight className="h-4 w-4" />
                        Cheapest
                      </div>
                      <p className="mt-1 text-muted-foreground">{formatSlot(cheapest)}</p>
                    </div>
                    <div className="rounded-md border border-rose-500/40 bg-rose-500/5 p-3 text-sm">
                      <div className="flex items-center gap-2 text-rose-300">
                        <ArrowUpRight className="h-4 w-4" />
                        Expensive
                      </div>
                      <p className="mt-1 text-muted-foreground">{formatSlot(expensive)}</p>
                    </div>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {day.slots.slice(0, 8).map((slot) => (
                      <div
                        key={slot.start}
                        className={cn(
                          'flex items-center justify-between rounded-md border px-3 py-2 text-sm',
                          (slot.price_pred_pence ?? 0) <= (dayAverage ?? 0)
                            ? 'border-emerald-500/40 bg-emerald-500/5'
                            : 'border-amber-500/40 bg-amber-500/5'
                        )}
                      >
                        <span>
                          {new Date(slot.start).toLocaleTimeString('en-GB', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                        <span className="font-medium">{slot.price_pred_pence?.toFixed(2)}p</span>
                      </div>
                    ))}
                  </div>
                  {day.slots.length > 8 && (
                    <p className="text-xs text-muted-foreground">+{day.slots.length - 8} more half-hour slots</p>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}
