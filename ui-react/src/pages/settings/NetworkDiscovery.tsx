import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  Globe2,
  Loader2,
  Network,
  Plus,
  Radar,
  RefreshCw,
  Save,
  ScanSearch,
  Trash2,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  APIError,
  AutoScanResponse,
  CreateMinerPayload,
  discoveryAPI,
  DiscoveryConfigResponse,
  DiscoveryScanResponse,
  DiscoveredMiner,
  minersAPI,
  NetworkInfoResponse,
  NetworkRange,
} from '@/lib/api'
import { cn } from '@/lib/utils'

type BannerTone = 'success' | 'error' | 'info'

interface BannerState {
  tone: BannerTone
  message: string
}

interface DiscoveryFormState {
  enabled: boolean
  autoAdd: boolean
  scanIntervalHours: number
  networks: NetworkRange[]
}

const initialFormState: DiscoveryFormState = {
  enabled: false,
  autoAdd: false,
  scanIntervalHours: 24,
  networks: [],
}

const CIDR_PATTERN = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/

export default function NetworkDiscovery() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<DiscoveryFormState>(initialFormState)
  const [manualNetwork, setManualNetwork] = useState('')
  const [banner, setBanner] = useState<BannerState | null>(null)
  const [scanResult, setScanResult] = useState<DiscoveryScanResponse | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [addingMinerKey, setAddingMinerKey] = useState<string | null>(null)

  const configQuery = useQuery<DiscoveryConfigResponse>({
    queryKey: ['discovery-config'],
    queryFn: discoveryAPI.getConfig,
  })

  const networkInfoQuery = useQuery<NetworkInfoResponse>({
    queryKey: ['discovery-network-info'],
    queryFn: discoveryAPI.getNetworkInfo,
    retry: false,
  })

  useEffect(() => {
    if (configQuery.data) {
      setForm({
        enabled: configQuery.data.enabled,
        autoAdd: configQuery.data.auto_add,
        scanIntervalHours: configQuery.data.scan_interval_hours,
        networks: configQuery.data.networks ?? [],
      })
    }
  }, [configQuery.data])

  const sanitizedNetworks = useMemo(() => sanitizeNetworks(form.networks), [form.networks])

  const statusBadge = useMemo(() => {
    if (!configQuery.data) return null
    const enabled = configQuery.data.enabled
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold',
          enabled ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-200'
        )}
      >
        {enabled ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
        {enabled ? 'Enabled' : 'Disabled'}
      </span>
    )
  }, [configQuery.data])

  const showBanner = (tone: BannerTone, message: string) => {
    setBanner({ tone, message })
    window.setTimeout(() => setBanner(null), 5000)
  }

  const extractError = (error: unknown) => {
    if (error instanceof APIError) {
      if (error.data && typeof error.data === 'object') {
        const detail = (error.data as { detail?: unknown }).detail
        if (typeof detail === 'string') {
          return detail
        }
      }
      return error.message
    }
    if (error instanceof Error) return error.message
    return 'Something went wrong'
  }

  const saveConfigMutation = useMutation({
    mutationFn: (payload: DiscoveryConfigResponse) => discoveryAPI.updateConfig(payload),
    onSuccess: () => {
      showBanner('success', 'Discovery configuration saved')
      queryClient.invalidateQueries({ queryKey: ['discovery-config'] })
    },
    onError: (error) => showBanner('error', extractError(error)),
  })

  const autoScanMutation = useMutation({
    mutationFn: () => discoveryAPI.triggerAutoScan(),
    onSuccess: (response: AutoScanResponse) => {
      const addedText = response.auto_add_enabled
        ? `, ${response.total_added} auto-added`
        : ''
      showBanner('info', `Auto-scan completed – ${response.total_found} miners detected${addedText}`)
    },
    onError: (error) => showBanner('error', extractError(error)),
  })

  const manualScanMutation = useMutation({
    mutationFn: (payload: { network_cidr: string }) =>
      discoveryAPI.scanNetwork({ network_cidr: payload.network_cidr, timeout: 5 }),
    onMutate: () => setScanError(null),
    onSuccess: (response) => {
      setScanResult(response)
      showBanner('info', `Scan complete – ${response.total_found} miner${response.total_found === 1 ? '' : 's'} found`)
    },
    onError: (error) => setScanError(extractError(error)),
  })

  const addMinerMutation = useMutation({
    mutationFn: (payload: CreateMinerPayload) => minersAPI.create(payload),
    onSuccess: (_, variables) => {
      showBanner('success', `${variables.name} added to your fleet`)
      setScanResult((current) => {
        if (!current) return current
        const updatedMiners = current.miners.map((miner) =>
          miner.ip === variables.ip_address && miner.port === (variables.port ?? miner.port)
            ? { ...miner, already_added: true }
            : miner
        )
        return {
          ...current,
          miners: updatedMiners,
          new_miners: Math.max(0, current.new_miners - 1),
          existing_miners: current.existing_miners + 1,
        }
      })
      queryClient.invalidateQueries({ queryKey: ['miners'] })
    },
    onError: (error) => showBanner('error', extractError(error)),
  })

  const handleToggle = (field: keyof Pick<DiscoveryFormState, 'enabled' | 'autoAdd'>) => {
    setForm((current) => ({
      ...current,
      [field]: field === 'enabled' ? !current.enabled : !current.autoAdd,
    }))
  }

  const handleNetworkField = (index: number, field: keyof NetworkRange, value: string) => {
    setForm((current) => {
      const next = [...current.networks]
      next[index] = {
        ...next[index],
        [field]: value,
      }
      return { ...current, networks: next }
    })
  }

  const handleAddNetwork = () => {
    setForm((current) => ({
      ...current,
      networks: [...current.networks, { cidr: '', name: '' }],
    }))
  }

  const handleRemoveNetwork = (index: number) => {
    setForm((current) => ({
      ...current,
      networks: current.networks.filter((_, idx) => idx !== index),
    }))
  }

  const handleUseSuggested = () => {
    if (!networkInfoQuery.data?.network_cidr) return
    if (form.networks.some((network) => network.cidr === networkInfoQuery.data?.network_cidr)) {
      showBanner('info', 'Suggested network already added')
      return
    }
    setForm((current) => ({
      ...current,
      networks: [
        ...current.networks,
        { cidr: networkInfoQuery.data!.network_cidr, name: 'Auto-detected' },
      ],
    }))
  }

  const handleSaveConfig = () => {
    if (form.scanIntervalHours < 1 || form.scanIntervalHours > 168) {
      showBanner('error', 'Scan interval must be between 1 and 168 hours')
      return
    }

    const payload: DiscoveryConfigResponse = {
      enabled: form.enabled,
      auto_add: form.autoAdd,
      scan_interval_hours: form.scanIntervalHours,
      networks: sanitizedNetworks,
    }

    saveConfigMutation.mutate(payload)
  }

  const triggerManualScan = (cidr?: string) => {
    const target = (cidr ?? manualNetwork).trim()
    setManualNetwork(target)

    if (!target) {
      setScanError('Enter a network CIDR to scan (e.g., 192.168.1.0/24)')
      return
    }

    if (!CIDR_PATTERN.test(target)) {
      setScanError('CIDR format is invalid. Use notation like 192.168.1.0/24')
      return
    }

    manualScanMutation.mutate({ network_cidr: target })
  }

  const handleDetectLocal = async () => {
    if (networkInfoQuery.data?.network_cidr) {
      setManualNetwork(networkInfoQuery.data.network_cidr)
      return
    }
    const refreshed = await networkInfoQuery.refetch()
    if (refreshed.data?.network_cidr) {
      setManualNetwork(refreshed.data.network_cidr)
    } else if (refreshed.error) {
      setScanError('Unable to auto-detect your local network')
    }
  }

  const handleAddMiner = (miner: DiscoveredMiner) => {
    const defaultName = `${miner.type.replace('_', '-')}-${miner.ip.split('.').pop()}`
    const chosenName = window.prompt(`Name for ${miner.type} at ${miner.ip}`, defaultName)
    if (!chosenName) return

    const payload: CreateMinerPayload = {
      name: chosenName.trim(),
      miner_type: miner.type,
      ip_address: miner.ip,
      port: miner.port,
    }

    const key = `${miner.ip}:${miner.port}`
    setAddingMinerKey(key)
    addMinerMutation.mutate(payload, {
      onSettled: () => setAddingMinerKey(null),
    })
  }

  if (configQuery.isLoading) {
    return <NetworkDiscoverySkeleton />
  }

  if (configQuery.isError) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3 text-2xl font-semibold">
          <Radar className="h-8 w-8 text-blue-400" />
          Network Discovery
        </div>
        <ErrorState message={extractError(configQuery.error)} onRetry={() => configQuery.refetch()} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 text-3xl font-semibold text-foreground">
          <Radar className="h-8 w-8 text-blue-400" />
          <span>Network Discovery</span>
          {statusBadge}
        </div>
        <p className="text-base text-muted-foreground">
          Automatically scan your home networks for Avalon Nanos, Bitaxe/NerdQaxe rigs. Configure auto-add rules or run ad-hoc scans when new hardware comes online.
        </p>
      </div>

      {banner && (
        <div
          className={cn(
            'rounded-xl border px-4 py-3 text-sm',
            banner.tone === 'success' && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100',
            banner.tone === 'error' && 'border-red-500/40 bg-red-500/10 text-red-100',
            banner.tone === 'info' && 'border-blue-500/40 bg-blue-500/10 text-blue-100'
          )}
        >
          {banner.message}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.4fr,1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <RefreshCw className="h-5 w-5 text-blue-300" /> Auto-discovery controls
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center justify-between gap-4 rounded-xl border border-border/60 bg-muted/5 px-4 py-3">
              <div>
                <p className="text-sm font-semibold text-foreground">Enable automatic discovery</p>
                <p className="text-xs text-muted-foreground">
                  When enabled, the scheduler scans every configured network on the defined interval.
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleToggle('enabled')}
                className={cn(
                  'flex h-6 w-12 items-center rounded-full border border-border px-0.5 transition-colors',
                  form.enabled ? 'bg-blue-500/80 border-blue-400' : 'bg-gray-800'
                )}
                aria-pressed={form.enabled}
              >
                <span
                  className={cn(
                    'h-5 w-5 rounded-full bg-white shadow transition-transform',
                    form.enabled ? 'translate-x-6' : 'translate-x-0'
                  )}
                />
              </button>
            </div>

            <div className="flex items-center justify-between gap-4 rounded-xl border border-border/60 bg-muted/5 px-4 py-3">
              <div>
                <p className="text-sm font-semibold text-foreground">Auto-add discovered miners</p>
                <p className="text-xs text-muted-foreground">
                  Automatically enroll anything new that responds on your network ranges.
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleToggle('autoAdd')}
                className={cn(
                  'flex h-6 w-12 items-center rounded-full border border-border px-0.5 transition-colors',
                  form.autoAdd ? 'bg-emerald-500/80 border-emerald-400' : 'bg-gray-800'
                )}
                aria-pressed={form.autoAdd}
              >
                <span
                  className={cn(
                    'h-5 w-5 rounded-full bg-white shadow transition-transform',
                    form.autoAdd ? 'translate-x-6' : 'translate-x-0'
                  )}
                />
              </button>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground" htmlFor="scan-interval">
                Scan interval (hours)
              </label>
              <input
                id="scan-interval"
                type="number"
                min={1}
                max={168}
                value={form.scanIntervalHours}
                onChange={(event) =>
                  setForm((current) => ({ ...current, scanIntervalHours: Number(event.target.value) }))
                }
                className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40 md:w-48"
              />
              <p className="text-xs text-muted-foreground">Between 1 and 168 hours. Default: once per day.</p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button onClick={handleSaveConfig} disabled={saveConfigMutation.isPending}>
                {saveConfigMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Save configuration
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={!form.enabled || sanitizedNetworks.length === 0 || autoScanMutation.isPending}
                onClick={() => autoScanMutation.mutate()}
              >
                {autoScanMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                Run auto-scan now
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Globe2 className="h-5 w-5 text-blue-300" /> Network ranges
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {networkInfoQuery.data?.network_cidr && (
              <div className="rounded-xl border border-blue-500/40 bg-blue-500/10 p-4 text-sm text-blue-50">
                <p className="font-semibold">Suggested CIDR: {networkInfoQuery.data.network_cidr}</p>
                <p className="text-xs text-blue-100/80">Auto-detected from your current interface.</p>
                <Button size="sm" variant="secondary" className="mt-3" onClick={handleUseSuggested}>
                  Use this range
                </Button>
              </div>
            )}

            {form.networks.length === 0 && (
              <p className="text-sm text-muted-foreground">No networks configured. Add at least one CIDR block.</p>
            )}

            <div className="space-y-3">
              {form.networks.map((network, index) => (
                <div
                  key={`${network.cidr}-${index}`}
                  className="rounded-2xl border border-border/60 bg-muted/5 p-4"
                >
                  <div className="grid gap-3 md:grid-cols-[1.3fr,1fr,auto] md:items-center">
                    <div>
                      <label className="text-xs uppercase tracking-wide text-muted-foreground">CIDR</label>
                      <input
                        type="text"
                        value={network.cidr}
                        onChange={(event) => handleNetworkField(index, 'cidr', event.target.value)}
                        className="mt-1 w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                        placeholder="192.168.1.0/24"
                      />
                    </div>
                    <div>
                      <label className="text-xs uppercase tracking-wide text-muted-foreground">Label</label>
                      <input
                        type="text"
                        value={network.name ?? ''}
                        onChange={(event) => handleNetworkField(index, 'name', event.target.value)}
                        className="mt-1 w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                        placeholder="Garage, Office, etc."
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => triggerManualScan(network.cidr)}
                      >
                        <ScanSearch className="mr-1.5 h-4 w-4" /> Scan
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => handleRemoveNetwork(index)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <Button type="button" variant="outline" onClick={handleAddNetwork}>
              <Plus className="mr-2 h-4 w-4" /> Add network
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Network className="h-5 w-5 text-blue-300" /> Manual discovery scan
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 md:grid-cols-[1.2fr,auto]">
            <div>
              <label className="text-sm font-medium text-foreground">Network CIDR</label>
              <input
                type="text"
                value={manualNetwork}
                onChange={(event) => setManualNetwork(event.target.value)}
                className="mt-1 w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                placeholder="192.168.1.0/24"
              />
              {scanError && <p className="mt-1 text-xs text-red-300">{scanError}</p>}
              <p className="mt-1 text-xs text-muted-foreground">
                Each scan tests Avalon cgminer ports and Bitaxe/NerdQaxe HTTP APIs.
              </p>
            </div>
            <div className="flex flex-col gap-2 md:items-end">
              <Button onClick={() => triggerManualScan()} disabled={manualScanMutation.isPending} className="w-full md:w-auto">
                {manualScanMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <ScanSearch className="mr-2 h-4 w-4" />
                )}
                Scan network
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={handleDetectLocal}
                disabled={networkInfoQuery.isFetching}
                className="w-full md:w-auto"
              >
                {networkInfoQuery.isFetching ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Globe2 className="mr-2 h-4 w-4" />
                )}
                Detect local network
              </Button>
            </div>
          </div>

          {manualScanMutation.isPending && (
            <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-muted/5 px-4 py-3 text-sm">
              <Loader2 className="h-4 w-4 animate-spin text-blue-300" />
              Scanning hosts… this can take up to a minute for /24 ranges.
            </div>
          )}

          {scanResult && (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <StatTile label="Total found" value={scanResult.total_found} tone="primary" />
                <StatTile label="New miners" value={scanResult.new_miners} tone="success" />
                <StatTile label="Already added" value={scanResult.existing_miners} tone="muted" />
              </div>

              <div className="space-y-3">
                {scanResult.miners.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No miners responded on this network.</p>
                ) : (
                  scanResult.miners.map((miner) => (
                    <DiscoveredMinerCard
                      key={`${miner.ip}:${miner.port}`}
                      miner={miner}
                      onAdd={() => handleAddMiner(miner)}
                      isAdding={addingMinerKey === `${miner.ip}:${miner.port}` && addMinerMutation.isPending}
                    />
                  ))
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function sanitizeNetworks(networks: NetworkRange[]): NetworkRange[] {
  return networks
    .map((network) => ({
      cidr: network.cidr?.trim() ?? '',
      name: network.name?.trim() || undefined,
    }))
    .filter((network) => network.cidr.length > 0)
}

function StatTile({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'primary' | 'success' | 'muted'
}) {
  const toneStyles = {
    primary: 'text-blue-300',
    success: 'text-emerald-300',
    muted: 'text-muted-foreground',
  }
  return (
    <div className="rounded-2xl border border-border/60 bg-muted/5 px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('text-3xl font-semibold', toneStyles[tone])}>{value}</p>
    </div>
  )
}

function DiscoveredMinerCard({
  miner,
  onAdd,
  isAdding,
}: {
  miner: DiscoveredMiner
  onAdd: () => void
  isAdding: boolean
}) {
  const detailEntries = Object.entries(miner.details ?? {}).slice(0, 4)
  return (
    <div
      className={cn(
        'rounded-2xl border border-border/60 bg-muted/5 p-4',
        miner.already_added && 'opacity-60'
      )}
    >
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold text-foreground">{miner.name}</p>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{miner.type}</p>
        </div>
        {!miner.already_added && (
          <Button size="sm" onClick={onAdd} disabled={isAdding}>
            {isAdding ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
            Add miner
          </Button>
        )}
      </div>

      <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Address</p>
          <p className="font-semibold text-foreground">
            {miner.ip}:{miner.port}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Status</p>
          <p className="font-semibold text-foreground">
            {miner.already_added ? 'Already enrolled' : 'New device'}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Details</p>
          <p className="font-semibold text-foreground">
            {detailEntries.length > 0 ? `${detailEntries.length} field${detailEntries.length === 1 ? '' : 's'}` : '—'}
          </p>
        </div>
      </div>

      {detailEntries.length > 0 && (
        <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
          {detailEntries.map(([key, value]) => (
            <div key={key}>
              <span className="font-semibold text-foreground">{key}:</span> {String(value)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function NetworkDiscoverySkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-8 w-56 animate-pulse rounded bg-muted/20" />
      <div className="grid gap-6 xl:grid-cols-[1.4fr,1fr]">
        {[1, 2].map((section) => (
          <div key={section} className="space-y-3 rounded-2xl border border-border/40 bg-muted/5 p-6">
            <div className="h-5 w-1/3 animate-pulse rounded bg-muted/30" />
            {[...Array(4)].map((_, index) => (
              <div key={index} className="h-10 animate-pulse rounded bg-muted/20" />
            ))}
          </div>
        ))}
      </div>
      <div className="rounded-2xl border border-border/40 bg-muted/5 p-6">
        <div className="h-5 w-1/4 animate-pulse rounded bg-muted/30" />
        <div className="mt-4 space-y-3">
          {[...Array(3)].map((_, index) => (
            <div key={index} className="h-12 animate-pulse rounded bg-muted/20" />
          ))}
        </div>
      </div>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="border-red-500/40 bg-red-500/10">
      <CardContent className="flex flex-col gap-4 py-6">
        <div className="flex items-center gap-2 text-sm text-red-100">
          <AlertTriangle className="h-5 w-5" />
          {message}
        </div>
        <div>
          <Button variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
