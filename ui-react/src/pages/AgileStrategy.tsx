import { Fragment, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, AlertCircle, Info, Layers, Plus, RefreshCcw, ShieldCheck, Target, Trash2, Zap } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

const COIN_OPTIONS = [
  { value: 'OFF', label: 'OFF (devices off)' },
  { value: 'DGB', label: 'DGB · DigiByte Solo' },
  { value: 'BC2', label: 'BC2 · DigiByte Turbo' },
  { value: 'BCH', label: 'BCH · Bitcoin Cash Solo' },
  { value: 'BTC', label: 'BTC · Bitcoin Solo' },
  { value: 'BTC_POOLED', label: 'BTC · Braiins Pool' },
]

const MODE_OPTIONS = {
  bitaxe: [
    { value: 'managed_externally', label: 'HA Off / External' },
    { value: 'eco', label: 'Eco' },
    { value: 'standard', label: 'Standard' },
    { value: 'turbo', label: 'Turbo' },
    { value: 'oc', label: 'OC' },
  ],
  nerdqaxe: [
    { value: 'managed_externally', label: 'HA Off / External' },
    { value: 'eco', label: 'Eco' },
    { value: 'standard', label: 'Standard' },
    { value: 'turbo', label: 'Turbo' },
    { value: 'oc', label: 'OC' },
  ],
  avalon_nano: [
    { value: 'managed_externally', label: 'HA Off / External' },
    { value: 'low', label: 'Low' },
    { value: 'med', label: 'Medium' },
    { value: 'high', label: 'High' },
  ],
} as const

type MinerRecord = {
  id: number
  name: string
  type: keyof MinersByType
  enrolled?: boolean
}

type MinersByType = {
  bitaxe: MinerRecord[]
  nerdqaxe: MinerRecord[]
  avalon_nano: MinerRecord[]
  nmminer: MinerRecord[]
}

type StrategySettings = {
  enabled: boolean
  current_price_band: string | null
  last_action_time: string | null
  last_price_checked: number | null
  hysteresis_counter: number
  enrolled_miners: { id: number; name: string; type: string }[]
  miners_by_type: MinersByType
}

type StrategyBand = {
  id: number
  sort_order: number
  min_price: number | null
  max_price: number | null
  target_coin: string
  bitaxe_mode: string
  nerdqaxe_mode: string
  avalon_nano_mode: string
}

type BandsResponse = { bands: StrategyBand[] }

type FetchError = Error & { detail?: string }

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const message = body.detail || body.message || `Request failed (${response.status})`
    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

const MINER_GROUPS: {
  key: keyof MinersByType
  label: string
  icon: React.ComponentType<{ className?: string }>
  helper: string
}[] = [
  { key: 'bitaxe', label: 'Bitaxe 601', icon: Zap, helper: 'Full control (eco/standard/turbo/oc)' },
  { key: 'nerdqaxe', label: 'NerdQaxe++', icon: Target, helper: 'Supports aggressive tuning profiles' },
  { key: 'avalon_nano', label: 'Avalon Nano 3/3S', icon: Layers, helper: 'Uses low / med / high workmodes' },
  { key: 'nmminer', label: 'NMMiner ESP32', icon: Activity, helper: 'Lottery miners for extreme variance plays' },
]

function formatTimestamp(value: string | null) {
  if (!value) return 'Never'
  const date = new Date(value)
  return `${date.toLocaleDateString()} · ${date.toLocaleTimeString()}`
}

function formatPrice(value: number | null) {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(2)} p/kWh`
}

export default function AgileStrategy() {
  const queryClient = useQueryClient()
  const [selectedMiners, setSelectedMiners] = useState<Set<number>>(new Set())
  const [strategyEnabled, setStrategyEnabled] = useState(false)
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const {
    data: strategyData,
    isLoading: strategyLoading,
    error: strategyError,
  } = useQuery<StrategySettings>({
    queryKey: ['agile-strategy'],
    queryFn: () => fetchJSON<StrategySettings>('/api/settings/agile-solo-strategy'),
  })

  const {
    data: bandsData,
    isLoading: bandsLoading,
    error: bandsError,
  } = useQuery<BandsResponse>({
    queryKey: ['agile-strategy-bands'],
    queryFn: () => fetchJSON<BandsResponse>('/api/settings/agile-solo-strategy/bands'),
  })

  useEffect(() => {
    if (!strategyData) return
    setStrategyEnabled(strategyData.enabled)
    setSelectedMiners(new Set(strategyData.enrolled_miners.map((miner) => miner.id)))
  }, [strategyData])

  const saveMutation = useMutation({
    mutationFn: (payload: { enabled: boolean; miner_ids: number[] }) =>
      fetchJSON('/api/settings/agile-solo-strategy', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setFeedback({ type: 'success', message: 'Strategy settings saved' })
      queryClient.invalidateQueries({ queryKey: ['agile-strategy'] })
    },
    onError: (error: FetchError) => {
      setFeedback({ type: 'error', message: error.message })
    },
  })

  const updateBandMutation = useMutation({
    mutationFn: ({ bandId, body }: { bandId: number; body: Record<string, number | string | null> }) =>
      fetchJSON(`/api/settings/agile-solo-strategy/bands/${bandId}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agile-strategy-bands'] })
    },
    onError: (error: FetchError) => {
      setFeedback({ type: 'error', message: error.message })
    },
  })

  const resetBandsMutation = useMutation({
    mutationFn: () =>
      fetchJSON('/api/settings/agile-solo-strategy/bands/reset', {
        method: 'POST',
      }),
    onSuccess: () => {
      setFeedback({ type: 'success', message: 'Bands reset to defaults' })
      queryClient.invalidateQueries({ queryKey: ['agile-strategy-bands'] })
    },
    onError: (error: FetchError) => {
      setFeedback({ type: 'error', message: error.message })
    },
  })

  const stats = useMemo(
    () => ({
      status: strategyEnabled ? 'Enabled' : 'Disabled',
      currentBand: strategyData?.current_price_band || '—',
      lastAction: formatTimestamp(strategyData?.last_action_time || null),
      currentPrice: formatPrice(strategyData?.last_price_checked ?? null),
      enrolled: selectedMiners.size,
      hysteresis: strategyData?.hysteresis_counter ?? 0,
    }),
    [strategyData?.current_price_band, strategyData?.hysteresis_counter, strategyData?.last_action_time, strategyData?.last_price_checked, selectedMiners.size, strategyEnabled]
  )

  const toggleMiner = (minerId: number) => {
    setSelectedMiners((prev) => {
      const next = new Set(prev)
      if (next.has(minerId)) {
        next.delete(minerId)
      } else {
        next.add(minerId)
      }
      return next
    })
  }

  const toggleGroup = (minerIds: number[], shouldSelect: boolean) => {
    setSelectedMiners((prev) => {
      const next = new Set(prev)
      minerIds.forEach((id) => {
        if (shouldSelect) {
          next.add(id)
        } else {
          next.delete(id)
        }
      })
      return next
    })
  }

  const handleSave = () => {
    saveMutation.mutate({
      enabled: strategyEnabled,
      miner_ids: Array.from(selectedMiners),
    })
  }

  const handleBandNumberChange = (bandId: number, field: 'min_price' | 'max_price', rawValue: string) => {
    const trimmed = rawValue.trim()
    const value = trimmed === '' ? null : Number(trimmed)

    if (value !== null && Number.isNaN(value)) {
      setFeedback({ type: 'error', message: 'Price thresholds must be numeric' })
      return
    }

    updateBandMutation.mutate({ bandId, body: { [field]: value } })
  }

  const handleBandSelectChange = (bandId: number, field: string, value: string) => {
    updateBandMutation.mutate({ bandId, body: { [field]: value } })
  }

  const deleteBandMutation = useMutation({
    mutationFn: (bandId: number) =>
      fetchJSON(`/api/settings/agile-solo-strategy/bands/${bandId}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      setFeedback({ type: 'success', message: 'Band removed' })
      queryClient.invalidateQueries({ queryKey: ['agile-strategy-bands'] })
    },
    onError: (error: FetchError) => {
      setFeedback({ type: 'error', message: error.message })
    },
  })

  const insertBandMutation = useMutation({
    mutationFn: (body: { insert_after_band_id: number | null }) =>
      fetchJSON('/api/settings/agile-solo-strategy/bands', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setFeedback({ type: 'success', message: 'New band inserted' })
      queryClient.invalidateQueries({ queryKey: ['agile-strategy-bands'] })
    },
    onError: (error: FetchError) => {
      setFeedback({ type: 'error', message: error.message })
    },
  })

  const handleInsertBand = (insertAfterBandId: number | null) => {
    insertBandMutation.mutate({ insert_after_band_id: insertAfterBandId })
  }

  const handleDeleteBand = (bandId: number) => {
    const confirmed = window.confirm('Delete this price band? This cannot be undone (use reset to restore defaults).')
    if (!confirmed) return
    deleteBandMutation.mutate(bandId)
  }

  const renderInsertControl = (key: string, insertAfterBandId: number | null) => (
    <tr key={key} className="border-t border-gray-900/60">
      <td colSpan={6} className="py-2">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-center text-blue-300 hover:text-white"
          disabled={insertBandMutation.isPending}
          onClick={() => handleInsertBand(insertAfterBandId)}
        >
          <Plus className="mr-2 h-4 w-4" /> Add price band here
        </Button>
      </td>
    </tr>
  )

  if (strategyLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-gray-400">
        <div className="flex flex-col items-center gap-2">
          <RefreshCcw className="h-6 w-6 animate-spin" />
          <p>Loading Agile Strategy…</p>
        </div>
      </div>
    )
  }

  if (strategyError) {
    return (
      <div className="p-6">
        <Card className="border-red-500/40 bg-red-500/10">
          <CardContent className="flex items-center gap-3 p-6 text-red-200">
            <AlertCircle className="h-5 w-5" />
            <div>
              <p className="font-semibold">Unable to load strategy settings</p>
              <p className="text-sm opacity-80">
                {strategyError instanceof Error ? strategyError.message : 'Unknown error'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-blue-300">
          <Target className="h-5 w-5" />
          <span>Agile Strategy</span>
        </div>
        <h1 className="text-2xl font-semibold">Octopus Agile Solo Strategy</h1>
        <p className="text-gray-400 text-sm">
          Enroll miners, map Octopus Agile price bands to mining targets, and let HMM orchestrate pool switching,
          tuning, and Home Assistant device control.
        </p>
        <div className="flex flex-wrap gap-3 pt-4">
          <Button
            variant={strategyEnabled ? 'default' : 'outline'}
            onClick={() => setStrategyEnabled((prev) => !prev)}
            className="w-32"
          >
            {strategyEnabled ? 'Enabled' : 'Enable'}
          </Button>
          <Button
            variant="outline"
            disabled={saveMutation.isPending}
            onClick={handleSave}
          >
            Save Settings
          </Button>
        </div>
      </div>

      {feedback && (
        <div
          className={cn(
            'rounded-md border px-4 py-3 text-sm',
            feedback.type === 'success'
              ? 'border-green-500/40 bg-green-500/10 text-green-200'
              : 'border-red-500/40 bg-red-500/10 text-red-200'
          )}
        >
          {feedback.message}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-gray-500">Status</p>
            <p className={cn('mt-2 text-xl font-semibold', strategyEnabled ? 'text-green-300' : 'text-gray-300')}>
              {stats.status}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-gray-500">Current Band</p>
            <p className="mt-2 text-xl font-semibold">{stats.currentBand}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-gray-500">Last Action</p>
            <p className="mt-2 text-sm text-gray-200">{stats.lastAction}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase text-gray-500">Enrolled Miners</p>
            <p className="mt-2 text-xl font-semibold">{stats.enrolled}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-1">
            <h2 className="text-xl font-semibold">Strategy Primer</h2>
            <p className="text-sm text-gray-400">
              Understand how pricing bands, solo vs pooled modes, and hysteresis interact before enabling automation.
            </p>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border border-blue-500/30 bg-blue-500/5 p-4 text-sm text-blue-100">
            <h3 className="flex items-center gap-2 text-base font-semibold text-blue-200">
              <Info className="h-4 w-4" /> What happens when prices spike?
            </h3>
            <p className="mt-2 text-blue-100/80">
              When the OFF band threshold is reached the orchestration layer pauses miner tuning/pool changes and sends
              &quot;off&quot; commands to linked Home Assistant switches. As soon as prices settle into a cheaper band the strategy
              resumes normal operation.
            </p>
          </div>
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-100">
            <h3 className="flex items-center gap-2 text-base font-semibold text-amber-200">
              <AlertCircle className="h-4 w-4" /> Avoid rule conflicts
            </h3>
            <p className="mt-2 text-amber-100/80">
              Automation rules that touch enrolled miners (mode changes, pool overrides, HA commands) may conflict with the
              strategy engine. Disable conflicting rules or scope them to miners not enrolled here.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-1">
            <h2 className="text-xl font-semibold">Enroll Miners</h2>
            <p className="text-sm text-gray-400">Only enabled ASIC miners appear. Use group toggles to speed up selection.</p>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {MINER_GROUPS.map((group) => {
            const miners = strategyData?.miners_by_type?.[group.key] ?? []
            const selectedCount = miners.filter((miner) => selectedMiners.has(miner.id)).length
            const allSelected = miners.length > 0 && selectedCount === miners.length

            return (
              <div key={group.key} className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-base font-semibold">
                      <group.icon className="h-4 w-4 text-blue-300" /> {group.label}
                    </div>
                    <p className="text-sm text-gray-500">{group.helper}</p>
                  </div>
                  {miners.length > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs"
                      onClick={() => toggleGroup(miners.map((m) => m.id), !allSelected)}
                    >
                      {allSelected ? 'Clear' : 'Select all'} ({selectedCount}/{miners.length})
                    </Button>
                  )}
                </div>

                {miners.length === 0 ? (
                  <p className="mt-4 rounded-md border border-dashed border-gray-700 p-3 text-sm text-gray-500">
                    No miners available.
                  </p>
                ) : (
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {miners.map((miner) => (
                      <label
                        key={miner.id}
                        className="flex cursor-pointer items-center gap-3 rounded-md border border-gray-800 bg-gray-950/60 p-3 hover:border-blue-500/40"
                      >
                        <Checkbox
                          checked={selectedMiners.has(miner.id)}
                          onCheckedChange={() => toggleMiner(miner.id)}
                        />
                        <div>
                          <p className="font-medium text-sm text-gray-100">{miner.name}</p>
                          <p className="text-xs text-gray-500">ID #{miner.id}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold">Price Band Strategy</h2>
                <p className="text-sm text-gray-400">Map Agile price windows to coins and tuning modes.</p>
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={resetBandsMutation.isPending}
                onClick={() => resetBandsMutation.mutate()}
                className="gap-2"
              >
                <RefreshCcw className="h-4 w-4" /> Reset to defaults
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {bandsLoading ? (
            <div className="flex min-h-[200px] items-center justify-center text-gray-400">Loading bands…</div>
          ) : bandsError ? (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200">
              {(bandsError as FetchError).message || 'Failed to load price bands'}
            </div>
          ) : (
            <table className="w-full min-w-[800px] text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-gray-500">
                  <th className="py-3 pr-4 font-medium">Price band (p/kWh)</th>
                  <th className="py-3 pr-4 font-medium">Coin</th>
                  <th className="py-3 pr-4 font-medium">Bitaxe Mode</th>
                  <th className="py-3 pr-4 font-medium">NerdQaxe Mode</th>
                  <th className="py-3 pr-4 font-medium">Avalon Nano Mode</th>
                  <th className="py-3 font-medium">Notes</th>
                  <th className="py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {renderInsertControl('insert-top', null)}
                {bandsData?.bands.map((band) => {
                  const isOffBand = band.target_coin === 'OFF'
                  return (
                    <Fragment key={band.id}>
                      <tr className="border-t border-gray-800">
                        <td className="py-3 pr-4">
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              defaultValue={band.min_price ?? ''}
                              placeholder="min"
                              className="w-24 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                              onBlur={(event) =>
                                handleBandNumberChange(band.id, 'min_price', event.target.value)
                              }
                            />
                            <span className="text-gray-500">–</span>
                            <input
                              type="number"
                              defaultValue={band.max_price ?? ''}
                              placeholder="max"
                              className="w-24 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                              onBlur={(event) =>
                                handleBandNumberChange(band.id, 'max_price', event.target.value)
                              }
                            />
                          </div>
                        </td>
                        <td className="py-3 pr-4">
                          <Select
                            value={band.target_coin}
                            onValueChange={(value) => handleBandSelectChange(band.id, 'target_coin', value)}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select coin" />
                            </SelectTrigger>
                            <SelectContent>
                              {COIN_OPTIONS.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-3 pr-4">
                          <Select
                            disabled={isOffBand}
                            value={band.bitaxe_mode}
                            onValueChange={(value) => handleBandSelectChange(band.id, 'bitaxe_mode', value)}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Bitaxe mode" />
                            </SelectTrigger>
                            <SelectContent>
                              {MODE_OPTIONS.bitaxe.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-3 pr-4">
                          <Select
                            disabled={isOffBand}
                            value={band.nerdqaxe_mode}
                            onValueChange={(value) => handleBandSelectChange(band.id, 'nerdqaxe_mode', value)}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="NerdQaxe mode" />
                            </SelectTrigger>
                            <SelectContent>
                              {MODE_OPTIONS.nerdqaxe.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-3 pr-4">
                          <Select
                            disabled={isOffBand}
                            value={band.avalon_nano_mode}
                            onValueChange={(value) => handleBandSelectChange(band.id, 'avalon_nano_mode', value)}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Avalon mode" />
                            </SelectTrigger>
                            <SelectContent>
                              {MODE_OPTIONS.avalon_nano.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-3 text-gray-500">
                          {isOffBand
                            ? 'Turns off all linked HA devices'
                            : 'Applies pool + mode changes (or HA off if selected)'}
                        </td>
                        <td className="py-3">
                          <div className="flex justify-end">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-gray-400 hover:text-red-300"
                              disabled={deleteBandMutation.isPending}
                              onClick={() => handleDeleteBand(band.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                      {renderInsertControl(`insert-after-${band.id}`, band.id)}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-base font-semibold">
            <ShieldCheck className="h-5 w-5 text-green-300" /> Hysteresis & Recovery
          </div>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-2 pl-5 text-sm text-gray-300">
            <li>Upgrades into cheaper bands require the next 30-minute slot to confirm the same or better price.</li>
            <li>Downgrades into expensive bands happen immediately to avoid negative profitability.</li>
            <li>The scheduler executes every 30 minutes plus an additional reconciliation run when prices change suddenly.</li>
            <li>Current hysteresis counter: <span className="font-semibold text-white">{stats.hysteresis}</span></li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
