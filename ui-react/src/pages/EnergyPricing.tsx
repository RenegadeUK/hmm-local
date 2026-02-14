import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CalendarDays,
  Gauge,
  Lightbulb,
  Loader2,
  PlugZap,
  RefreshCw,
  type LucideIcon,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'

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

type EnergyConfig = {
  enabled: boolean
  provider_id: string
  provider_config?: Record<string, unknown>
  region: string
}

type EnergyProviderInfo = {
  name: string
  provider_id: string
  display_name: string
  current_version: string | null
  available_version: string
  status: 'up_to_date' | 'update_available' | 'not_installed'
  description?: string | null
  supported_regions?: string[]
}

type EnergyProviderRuntimeStatus = {
  configured_provider_id: string
  available_provider_ids: string[]
  runtime: {
    provider_id?: string | null
    configured_provider_id?: string | null
    region?: string | null
    last_run_at?: string | null
    last_success_at?: string | null
    last_error?: string | null
    last_result?: {
      provider_id: string
      region: string
      fetched: number
      inserted: number
      updated: number
    } | null
  }
}

type EnergyProviderHealthStatus = {
  configured_provider_id: string
  provider_id: string
  region: string
  validation_errors: Record<string, string>
  health: {
    status?: string
    provider_id?: string
    message?: string
  }
  checked_at: string
}

type PriceSummary = {
  price_pence: number | null
  valid_from: string | null
  valid_to: string | null
}

type PriceSlot = {
  valid_from: string
  valid_to: string
  price_pence: number
}

type EnergyTimeline = {
  today?: {
    date: string
    prices: PriceSlot[]
  }
  tomorrow?: {
    date: string
    prices: PriceSlot[]
  }
}

const REGION_OPTIONS = [
  { value: 'A', label: 'A - Eastern England' },
  { value: 'B', label: 'B - East Midlands' },
  { value: 'C', label: 'C - London' },
  { value: 'D', label: 'D - Merseyside and Northern Wales' },
  { value: 'E', label: 'E - West Midlands' },
  { value: 'F', label: 'F - North Eastern England' },
  { value: 'G', label: 'G - North Western England' },
  { value: 'H', label: 'H - Southern England' },
  { value: 'J', label: 'J - South Eastern England' },
  { value: 'K', label: 'K - Southern Wales' },
  { value: 'L', label: 'L - South Western England' },
  { value: 'M', label: 'M - Yorkshire' },
  { value: 'N', label: 'N - Southern Scotland' },
  { value: 'P', label: 'P - Northern Scotland' },
] as const

type BannerState = { type: 'success' | 'error'; message: string } | null

function formatTimeRange(validFrom?: string | null, validTo?: string | null) {
  if (!validFrom || !validTo) return '—'
  const from = new Date(validFrom)
  const to = new Date(validTo)
  return `${from.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })} → ${to.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  })}`
}

function slotTheme(price: number) {
  if (price <= 0) {
    return { background: 'linear-gradient(135deg, #60a5fa, #3b82f6)', color: '#ffffff' }
  }
  if (price < 10) {
    return { background: 'linear-gradient(135deg, #10b981, #059669)', color: '#000000' }
  }
  if (price < 15) {
    return { background: 'linear-gradient(135deg, #34d399, #10b981)', color: '#000000' }
  }
  if (price < 20) {
    return { background: 'linear-gradient(135deg, #6ee7b7, #34d399)', color: '#000000' }
  }
  if (price < 25) {
    return { background: 'linear-gradient(135deg, #fbbf24, #f59e0b)', color: '#ffffff' }
  }
  if (price < 30) {
    return { background: 'linear-gradient(135deg, #fb923c, #f97316)', color: '#ffffff' }
  }
  return { background: 'linear-gradient(135deg, #f87171, #ef4444)', color: '#ffffff' }
}

function StatusBadge({ enabled }: { enabled?: boolean }) {
  if (enabled === undefined) {
    return <span className="rounded-full bg-muted px-3 py-1 text-xs uppercase tracking-wide text-muted-foreground">Loading…</span>
  }

  return (
    <span
      className={cn(
        'rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide',
        enabled ? 'bg-green-500/10 text-green-300' : 'bg-slate-700 text-slate-300'
      )}
    >
      {enabled ? 'Enabled' : 'Disabled'}
    </span>
  )
}

function PriceCard({
  title,
  icon: Icon,
  summary,
}: {
  title: string
  icon: LucideIcon
  summary?: PriceSummary
}) {
  const hasValue = summary?.price_pence !== null && summary?.price_pence !== undefined

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          <CardTitle className="text-3xl font-semibold">
            {hasValue ? `${summary?.price_pence?.toFixed(2)} p/kWh` : 'No data'}
          </CardTitle>
        </div>
        <Icon className="h-10 w-10 text-blue-300" />
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          {hasValue ? formatTimeRange(summary?.valid_from, summary?.valid_to) : 'Waiting for latest slot'}
        </p>
      </CardContent>
    </Card>
  )
}

function TimelineSection({ title, data }: { title: string; data?: { date?: string; prices?: PriceSlot[] } }) {
  const now = new Date()
  const slots = (data?.prices || []).filter((slot) => new Date(slot.valid_to) > now)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="space-y-1 border-b border-border/50 bg-muted/10">
        <p className="text-xs uppercase tracking-widest text-blue-300">{title}</p>
        <CardTitle className="text-lg">{data?.date ?? 'Waiting for pricing data'}</CardTitle>
      </CardHeader>
      <CardContent className="p-6">
        {slots.length === 0 ? (
          <div className="text-sm text-muted-foreground">No upcoming half-hour slots yet.</div>
        ) : (
          <div className="grid gap-2 md:grid-cols-3 lg:grid-cols-4">
            {slots.map((slot) => {
              const theme = slotTheme(slot.price_pence)
              const start = new Date(slot.valid_from)
              const day = start.toLocaleDateString('en-GB', { weekday: 'short' })
              const time = start.toLocaleTimeString('en-GB', {
                hour: '2-digit',
                minute: '2-digit',
              })
              return (
                <div
                  key={slot.valid_from}
                  className="rounded-lg p-3 text-center shadow-sm"
                  style={{ background: theme.background, color: theme.color }}
                >
                  <p className="text-xs opacity-80">{`${day} ${time}`}</p>
                  <p className="text-lg font-semibold">{slot.price_pence.toFixed(2)}p</p>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function EnergyPricing() {
  const queryClient = useQueryClient()
  const [banner, setBanner] = useState<BannerState>(null)
  const [selectedProviderId, setSelectedProviderId] = useState('octopus_agile')
  const [selectedRegion, setSelectedRegion] = useState('H')

  const {
    data: config,
    isLoading: configLoading,
    error: configError,
  } = useQuery<EnergyConfig>({
    queryKey: ['energy-config'],
    queryFn: () => fetchJSON('/api/dashboard/energy/config'),
    refetchInterval: 60000,
  })

  const { data: providers = [], error: providersError } = useQuery<EnergyProviderInfo[]>({
    queryKey: ['energy-providers-status'],
    queryFn: () => fetchJSON('/api/drivers/energy-providers/status'),
    refetchInterval: 60000,
  })

  const { data: providerRuntime, error: providerRuntimeError } = useQuery<EnergyProviderRuntimeStatus>({
    queryKey: ['energy-provider-runtime'],
    queryFn: () => fetchJSON('/api/dashboard/energy/provider-status'),
    refetchInterval: 30000,
  })

  const { data: providerHealth, error: providerHealthError } = useQuery<EnergyProviderHealthStatus>({
    queryKey: ['energy-provider-health', selectedProviderId],
    queryFn: () => fetchJSON(`/api/dashboard/energy/provider-health?provider_id=${selectedProviderId}`),
    refetchInterval: 30000,
  })

  const { data: currentPrice, error: currentPriceError } = useQuery<PriceSummary>({
    queryKey: ['energy-current'],
    queryFn: () => fetchJSON('/api/dashboard/energy/current'),
    refetchInterval: 60000,
  })

  const { data: nextPrice, error: nextPriceError } = useQuery<PriceSummary>({
    queryKey: ['energy-next'],
    queryFn: () => fetchJSON('/api/dashboard/energy/next'),
    refetchInterval: 60000,
  })

  const { data: timeline, error: timelineError } = useQuery<EnergyTimeline>({
    queryKey: ['energy-timeline'],
    queryFn: () => fetchJSON('/api/dashboard/energy/timeline'),
    refetchInterval: 60000,
  })

  useEffect(() => {
    if (config?.provider_id) {
      setSelectedProviderId(config.provider_id)
    }
    if (config?.region) {
      setSelectedRegion(config.region)
    }
  }, [config?.provider_id, config?.region])

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.provider_id === selectedProviderId),
    [providers, selectedProviderId]
  )

  const selectableRegions = useMemo(() => {
    const supported = selectedProvider?.supported_regions || []
    if (supported.length === 0) {
      return REGION_OPTIONS
    }
    return REGION_OPTIONS.filter((region) => supported.includes(region.value))
  }, [selectedProvider?.supported_regions])

  const setProviderMutation = useMutation({
    mutationFn: (providerId: string) =>
      fetchJSON(`/api/dashboard/energy/provider?provider_id=${providerId}`, {
        method: 'POST',
      }),
    onSuccess: (_, providerId) => {
      setBanner({ type: 'success', message: `Provider switched to ${providerId}.` })
      queryClient.invalidateQueries({ queryKey: ['energy-config'] })
      queryClient.invalidateQueries({ queryKey: ['energy-provider-runtime'] })
      queryClient.invalidateQueries({ queryKey: ['energy-current'] })
      queryClient.invalidateQueries({ queryKey: ['energy-next'] })
      queryClient.invalidateQueries({ queryKey: ['energy-timeline'] })
    },
    onError: (error: Error) => setBanner({ type: 'error', message: error.message }),
  })

  const saveRegionMutation = useMutation({
    mutationFn: (region: string) =>
      fetchJSON(`/api/dashboard/energy/region?region=${region}`, {
        method: 'POST',
      }),
    onSuccess: (_, region) => {
      setBanner({ type: 'success', message: `Region saved: ${region}. Fetching latest slots…` })
      queryClient.invalidateQueries({ queryKey: ['energy-config'] })
      queryClient.invalidateQueries({ queryKey: ['energy-provider-runtime'] })
      queryClient.invalidateQueries({ queryKey: ['energy-current'] })
      queryClient.invalidateQueries({ queryKey: ['energy-next'] })
      queryClient.invalidateQueries({ queryKey: ['energy-timeline'] })
    },
    onError: (error: Error) => setBanner({ type: 'error', message: error.message }),
  })

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      fetchJSON(`/api/dashboard/energy/toggle?enabled=${String(enabled)}`, {
        method: 'POST',
      }),
    onSuccess: (_, enabled) => {
      setBanner({ type: 'success', message: enabled ? 'Energy pricing enabled.' : 'Energy pricing disabled.' })
      queryClient.invalidateQueries({ queryKey: ['energy-config'] })
    },
    onError: (error: Error) => setBanner({ type: 'error', message: error.message }),
  })

  const updateProviderMutation = useMutation({
    mutationFn: (providerName: string) =>
      fetchJSON(`/api/drivers/energy-providers/update/${providerName}`, {
        method: 'POST',
      }),
    onSuccess: () => {
      setBanner({ type: 'success', message: 'Provider updated successfully.' })
      queryClient.invalidateQueries({ queryKey: ['energy-providers-status'] })
    },
    onError: (error: Error) => setBanner({ type: 'error', message: error.message }),
  })

  const errors = [
    configError,
    providersError,
    providerRuntimeError,
    providerHealthError,
    currentPriceError,
    nextPriceError,
    timelineError,
  ].filter(Boolean)

  const isSavingRegion = saveRegionMutation.isPending
  const isToggling = toggleMutation.isPending
  const isSwitchingProvider = setProviderMutation.isPending
  const isUpdatingProvider = updateProviderMutation.isPending
  const regionChanged = selectedRegion !== config?.region
  const providerChanged = selectedProviderId !== config?.provider_id
  const providerCanUpdate = selectedProvider?.status === 'update_available'

  const handleSaveRegion = () => {
    if (!selectedRegion) return
    saveRegionMutation.mutate(selectedRegion)
  }

  const handleProviderSwitch = () => {
    if (!selectedProviderId) return
    setProviderMutation.mutate(selectedProviderId)
  }

  const handleToggle = () => {
    if (configLoading || config === undefined) return
    toggleMutation.mutate(!config.enabled)
  }

  const handleUpdateProvider = () => {
    if (!selectedProvider?.name) return
    updateProviderMutation.mutate(selectedProvider.name)
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-blue-300">
          <PlugZap className="h-5 w-5" />
          <span>Energy Pricing</span>
        </div>
        <h1 className="text-2xl font-semibold">Energy Provider Pricing</h1>
        <p className="text-sm text-gray-400">
          Select provider, configure provider settings, and monitor synchronization status while keeping the current and upcoming
          slot views live.
        </p>
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
          <span>{errors.map((err) => (err instanceof Error ? err.message : 'Unable to load energy pricing')).join(' • ')}</span>
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-col gap-4 border-b border-border/50 bg-muted/10 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-widest text-blue-300">Configuration</p>
            <CardTitle className="text-xl">Provider Configuration</CardTitle>
            <p className="text-sm text-muted-foreground">Half-hourly prices refresh every 30 minutes.</p>
          </div>
          <StatusBadge enabled={config?.enabled} />
        </CardHeader>
        <CardContent className="space-y-6 py-6">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground" htmlFor="provider-select">
                Select Provider
              </label>
              <Select value={selectedProviderId} onValueChange={setSelectedProviderId}>
                <SelectTrigger id="provider-select" className="h-12 text-left">
                  <SelectValue placeholder="Choose provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.provider_id} value={provider.provider_id}>
                      {provider.display_name} ({provider.provider_id})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {selectableRegions.length > 0 && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-muted-foreground" htmlFor="region-select">
                  Select Region
                </label>
                <Select value={selectedRegion} onValueChange={setSelectedRegion}>
                  <SelectTrigger id="region-select" className="h-12 text-left">
                    <SelectValue placeholder="Choose region" />
                  </SelectTrigger>
                  <SelectContent>
                    {selectableRegions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Button
              onClick={handleProviderSwitch}
              disabled={isSwitchingProvider || !providerChanged || configLoading}
              className="w-full"
            >
              {isSwitchingProvider ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save Provider'}
            </Button>

            <Button
              onClick={handleSaveRegion}
              disabled={isSavingRegion || !regionChanged || configLoading}
              variant="secondary"
              className="w-full"
            >
              {isSavingRegion ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save Region'}
            </Button>

            <Button
              onClick={handleUpdateProvider}
              disabled={isUpdatingProvider || !providerCanUpdate}
              variant="outline"
              className="w-full"
            >
              {isUpdatingProvider ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Update Provider'}
            </Button>

            <Button
              onClick={handleToggle}
              variant={config?.enabled ? 'destructive' : 'secondary'}
              disabled={isToggling || configLoading}
              className="w-full"
            >
              {isToggling ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : config?.enabled ? (
                'Disable Pricing'
              ) : (
                'Enable Pricing'
              )}
            </Button>
          </div>

          <div className="rounded-md border border-border/60 bg-muted/20 p-4 text-sm text-muted-foreground space-y-1">
            <div>
              <span className="font-medium text-foreground">Active:</span>{' '}
              {providerRuntime?.runtime?.provider_id || providerRuntime?.configured_provider_id || '—'}
            </div>
            <div>
              <span className="font-medium text-foreground">Last Success:</span>{' '}
              {providerRuntime?.runtime?.last_success_at
                ? new Date(providerRuntime.runtime.last_success_at).toLocaleString('en-GB')
                : '—'}
            </div>
            <div>
              <span className="font-medium text-foreground">Last Result:</span>{' '}
              {providerRuntime?.runtime?.last_result
                ? `${providerRuntime.runtime.last_result.fetched} fetched / ${providerRuntime.runtime.last_result.inserted} inserted / ${providerRuntime.runtime.last_result.updated} updated`
                : '—'}
            </div>
            {providerRuntime?.runtime?.last_error && (
              <div className="text-red-300">
                <span className="font-medium">Last Error:</span> {providerRuntime.runtime.last_error}
              </div>
            )}
            <div>
              <span className="font-medium text-foreground">Provider Health:</span>{' '}
              <span
                className={cn(
                  providerHealth?.health?.status === 'ok' ? 'text-green-300' : 'text-red-300'
                )}
              >
                {providerHealth?.health?.status || 'unknown'}
              </span>
              {providerHealth?.health?.message ? ` — ${providerHealth.health.message}` : ''}
            </div>
            {providerHealth && Object.keys(providerHealth.validation_errors || {}).length > 0 && (
              <div className="text-amber-300">
                <span className="font-medium">Validation:</span>{' '}
                {Object.entries(providerHealth.validation_errors)
                  .map(([key, value]) => `${key}: ${value}`)
                  .join(' • ')}
              </div>
            )}
            <div className="pt-1">
              <Button
                onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ['energy-provider-runtime'] })
                  queryClient.invalidateQueries({ queryKey: ['energy-provider-health'] })
                  queryClient.invalidateQueries({ queryKey: ['energy-current'] })
                  queryClient.invalidateQueries({ queryKey: ['energy-next'] })
                  queryClient.invalidateQueries({ queryKey: ['energy-timeline'] })
                }}
                size="sm"
                variant="ghost"
                className="px-0"
              >
                <RefreshCw className="mr-2 h-4 w-4" /> Refresh runtime status
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <PriceCard title="Current Slot" icon={Lightbulb} summary={currentPrice} />
        <PriceCard title="Next Slot" icon={Gauge} summary={nextPrice} />
      </div>

      <div className="space-y-4">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-blue-300">
          <CalendarDays className="h-5 w-5" />
          <span>Upcoming Timeline</span>
        </div>
        <TimelineSection title="Today" data={{ date: timeline?.today?.date, prices: timeline?.today?.prices }} />
        <TimelineSection title="Tomorrow" data={{ date: timeline?.tomorrow?.date, prices: timeline?.tomorrow?.prices }} />
      </div>
    </div>
  )
}
