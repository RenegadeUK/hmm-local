import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingDown, TrendingUp, DollarSign, Calendar } from 'lucide-react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

interface CostData {
  hours?: Array<{
    hour: string
    actual_cost: number
    baseline_cost: number
    savings: number
    savings_percent: number
  }>
  days?: Array<{
    date: string
    actual_cost: number
    baseline_cost: number
    savings: number
    savings_percent: number
  }>
  months?: Array<{
    year: number
    month: number
    month_name: string
    actual_cost: number
    baseline_cost: number
    savings: number
    savings_percent: number
  }>
  summary: {
    total_actual_cost: number
    total_baseline_cost: number
    total_savings: number
    savings_percent: number
  }
}

export function Costs() {
  const [activeView, setActiveView] = useState<'hourly' | 'daily' | 'monthly'>('daily')

  // Fetch hourly costs (24h)
  const { data: hourlyCosts, isLoading: loadingHourly } = useQuery<CostData>({
    queryKey: ['costs-hourly'],
    queryFn: async () => {
      const response = await fetch('/api/costs/hourly?hours=24')
      if (!response.ok) throw new Error('Failed to fetch hourly costs')
      return response.json()
    },
    refetchInterval: 900000, // 15 minutes
    enabled: activeView === 'hourly'
  })

  // Fetch daily costs (30 days)
  const { data: dailyCosts, isLoading: loadingDaily } = useQuery<CostData>({
    queryKey: ['costs-daily'],
    queryFn: async () => {
      const response = await fetch('/api/costs/daily?days=30')
      if (!response.ok) throw new Error('Failed to fetch daily costs')
      return response.json()
    },
    refetchInterval: 900000, // 15 minutes
    enabled: activeView === 'daily'
  })

  // Fetch monthly costs (12 months)
  const { data: monthlyCosts, isLoading: loadingMonthly } = useQuery<CostData>({
    queryKey: ['costs-monthly'],
    queryFn: async () => {
      const response = await fetch('/api/costs/monthly?months=12')
      if (!response.ok) throw new Error('Failed to fetch monthly costs')
      return response.json()
    },
    refetchInterval: 900000, // 15 minutes
    enabled: activeView === 'monthly'
  })

  const isLoading = loadingHourly || loadingDaily || loadingMonthly

  // Get active data based on view
  const activeData = 
    activeView === 'hourly' ? hourlyCosts :
    activeView === 'daily' ? dailyCosts :
    monthlyCosts

  // Prepare chart data
  const getChartData = () => {
    if (!activeData) return null

    let labels: string[] = []
    let actualCosts: number[] = []
    let baselineCosts: number[] = []
    let savings: number[] = []

    if (activeView === 'hourly' && activeData.hours) {
      labels = activeData.hours.map(h => {
        const date = new Date(h.hour)
        return date.toLocaleDateString('en-GB', { hour: '2-digit', minute: '2-digit' })
      })
      actualCosts = activeData.hours.map(h => h.actual_cost)
      baselineCosts = activeData.hours.map(h => h.baseline_cost)
      savings = activeData.hours.map(h => h.savings)
    } else if (activeView === 'daily' && activeData.days) {
      labels = activeData.days.map(d => {
        const date = new Date(d.date + 'T00:00:00')
        return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      })
      actualCosts = activeData.days.map(d => d.actual_cost)
      baselineCosts = activeData.days.map(d => d.baseline_cost)
      savings = activeData.days.map(d => d.savings)
    } else if (activeView === 'monthly' && activeData.months) {
      labels = activeData.months.map(m => `${m.month_name.substring(0, 3)} ${m.year}`)
      actualCosts = activeData.months.map(m => m.actual_cost)
      baselineCosts = activeData.months.map(m => m.baseline_cost)
      savings = activeData.months.map(m => m.savings)
    }

    return {
      labels,
      datasets: [
        {
          label: 'Actual Cost',
          data: actualCosts,
          borderColor: 'rgb(59, 130, 246)',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          fill: true,
          tension: 0.3
        },
        {
          label: 'Without Automation (24/7)',
          data: baselineCosts,
          borderColor: 'rgb(239, 68, 68)',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          fill: true,
          tension: 0.3,
          borderDash: [5, 5]
        },
        {
          label: 'Savings',
          data: savings,
          borderColor: 'rgb(34, 197, 94)',
          backgroundColor: 'rgba(34, 197, 94, 0.2)',
          fill: true,
          tension: 0.3
        }
      ]
    }
  }

  const chartData = getChartData()

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: false
      },
      tooltip: {
        callbacks: {
          label: function(context: any) {
            return `${context.dataset.label}: £${context.parsed.y.toFixed(2)}`
          }
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          callback: function(value: any) {
            return '£' + value.toFixed(2)
          }
        }
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Energy Costs</h1>
        <p className="text-muted-foreground">
          Track actual costs vs. baseline (if all miners ran 24/7)
        </p>
      </div>

      {/* View Selector */}
      <div className="flex gap-2">
        <button
          onClick={() => setActiveView('hourly')}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            activeView === 'hourly'
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted hover:bg-muted/80'
          }`}
        >
          Last 24 Hours
        </button>
        <button
          onClick={() => setActiveView('daily')}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            activeView === 'daily'
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted hover:bg-muted/80'
          }`}
        >
          Last 30 Days
        </button>
        <button
          onClick={() => setActiveView('monthly')}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            activeView === 'monthly'
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted hover:bg-muted/80'
          }`}
        >
          Last 12 Months
        </button>
      </div>

      {/* Summary Cards */}
      {activeData && (
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-lg border bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <DollarSign className="h-4 w-4" />
              Actual Cost
            </div>
            <div className="mt-2 text-2xl font-bold">
              £{activeData.summary.total_actual_cost.toFixed(2)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Energy consumed
            </div>
          </div>

          <div className="rounded-lg border bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <TrendingUp className="h-4 w-4" />
              Without Automation
            </div>
            <div className="mt-2 text-2xl font-bold">
              £{activeData.summary.total_baseline_cost.toFixed(2)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              If miners ran 24/7
            </div>
          </div>

          <div className="rounded-lg border bg-card p-4 bg-green-500/10 border-green-500/20">
            <div className="flex items-center gap-2 text-sm font-medium text-green-600 dark:text-green-400">
              <TrendingDown className="h-4 w-4" />
              Total Savings
            </div>
            <div className="mt-2 text-2xl font-bold text-green-600 dark:text-green-400">
              £{activeData.summary.total_savings.toFixed(2)}
            </div>
            <div className="mt-1 text-xs text-green-600/80 dark:text-green-400/80">
              From automation
            </div>
          </div>

          <div className="rounded-lg border bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Calendar className="h-4 w-4" />
              Savings %
            </div>
            <div className="mt-2 text-2xl font-bold">
              {activeData.summary.savings_percent.toFixed(1)}%
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Cost reduction
            </div>
          </div>
        </div>
      )}

      {/* Chart */}
      <div className="rounded-lg border bg-card">
        <div className="border-b p-4">
          <h2 className="text-lg font-semibold">
            {activeView === 'hourly' && 'Hourly Costs (Last 24 Hours)'}
            {activeView === 'daily' && 'Daily Costs (Last 30 Days)'}
            {activeView === 'monthly' && 'Monthly Costs (Last 12 Months)'}
          </h2>
          <p className="text-sm text-muted-foreground">
            Blue: Actual costs • Red: Without automation (24/7) • Green: Savings
          </p>
        </div>
        <div className="p-4">
          {isLoading ? (
            <div className="flex h-96 items-center justify-center">
              <div className="text-muted-foreground">Loading cost data...</div>
            </div>
          ) : chartData ? (
            <div className="h-96">
              <Line data={chartData} options={chartOptions} />
            </div>
          ) : (
            <div className="flex h-96 items-center justify-center">
              <div className="text-muted-foreground">No cost data available</div>
            </div>
          )}
        </div>
      </div>

      {/* Info Box */}
      <div className="rounded-lg border bg-blue-500/10 border-blue-500/20 p-4">
        <div className="flex items-start gap-3">
          <div className="rounded-full bg-blue-500/20 p-2">
            <DollarSign className="h-5 w-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-blue-900 dark:text-blue-100">How Costs Are Calculated</h3>
            <p className="mt-1 text-sm text-blue-800 dark:text-blue-200">
              <strong>Actual Cost:</strong> Calculated from telemetry data (power readings × electricity price × runtime).
              When automation turns miners OFF, no power is consumed, so cost is lower.
            </p>
            <p className="mt-2 text-sm text-blue-800 dark:text-blue-200">
              <strong>Baseline (Without Automation):</strong> Estimated cost if all miners ran 24/7 at their average power draw.
              Uses actual electricity prices during downtime periods.
            </p>
            <p className="mt-2 text-sm text-blue-800 dark:text-blue-200">
              <strong>Savings:</strong> The difference between baseline and actual cost - money saved by automation turning miners OFF during expensive electricity periods.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
