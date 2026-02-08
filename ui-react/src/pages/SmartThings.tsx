import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Trash2
} from 'lucide-react'

interface StConfigResponse {
  configured: boolean
  id?: number
  name?: string
  enabled?: boolean
  last_test?: string | null
  last_test_success?: boolean | null
}

interface SaveConfigPayload {
  name: string
  access_token: string | null
  enabled: boolean
}

interface Device {
  id: number
  device_id: string
  name: string
  domain: string
  miner_id: number | null
  enrolled: boolean
  never_auto_control: boolean
  current_state: string | null
  capabilities?: Record<string, any>
}

interface DevicesResponse {
  devices: Device[]
}

interface Miner {
  id: number
  name: string
}

interface ApiResponse {
  success: boolean
  message: string
}

// Minimal fetch helper
async function fetchJSON<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(errorData.detail || response.statusText)
  }
  return response.json()
}

function ConnectionBadge({ config }: { config: StConfigResponse | undefined }) {
  if (!config?.configured) {
    return (
      <span className="inline-flex items-center rounded-full bg-slate-500/10 px-2 py-0.5 text-xs text-slate-300">
        Not configured
      </span>
    )
  }
  if (config.last_test_success === true) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-500/15 px-2 py-0.5 text-xs font-medium text-green-300">
        <CheckCircle2 className="h-3.5 w-3.5" /> Connected
      </span>
    )
  }
  if (config.last_test_success === false) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-300">
        <AlertTriangle className="h-3.5 w-3.5" /> Connection failed
      </span>
    )
  }
  return <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200">Not tested</span>
}

export default function SmartThings() {
  const queryClient = useQueryClient()
  const [banner, setBanner] = useState<{ tone: 'success' | 'error' | 'info'; message: string } | null>(null)
  const [formState, setFormState] = useState({
    name: 'SmartThings',
    access_token: '',
    enabled: true,
  })
  const [showAllDevices, setShowAllDevices] = useState(false)

  // Load config
  const { data: config, isLoading } = useQuery({
    queryKey: ['smartthings-config'],
    queryFn: () => fetchJSON<StConfigResponse>('/api/integrations/smartthings/config'),
    refetchOnWindowFocus: false,
  })

  // Load devices
  const { data: devicesData, isLoading: devicesLoading } = useQuery({
    queryKey: ['smartthings-devices', showAllDevices],
    queryFn: () =>
      fetchJSON<DevicesResponse>(
        `/api/integrations/smartthings/devices${showAllDevices ? '' : '?enrolled_only=true'}`
      ),
    enabled: config?.configured === true,
    refetchOnWindowFocus: false,
  })

  // Load miners
  const { data: miners } = useQuery({
    queryKey: ['miners'],
    queryFn: () => fetchJSON<Miner[]>('/api/miners/'),
    refetchOnWindowFocus: false,
  })

  // Update form when config loads
  useState(() => {
    if (config?.configured) {
      setFormState({
        name: config.name || 'SmartThings',
        access_token: '',
        enabled: config.enabled || false,
      })
    }
  })

  // Save config mutation
  const saveConfigMutation = useMutation({
    mutationFn: async (payload: SaveConfigPayload) => {
      return fetchJSON<ApiResponse>('/api/integrations/smartthings/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    },
    onSuccess: (data) => {
      setBanner({ tone: 'success', message: data.message })
      queryClient.invalidateQueries({ queryKey: ['smartthings-config'] })
    },
    onError: (error: Error) => {
      setBanner({ tone: 'error', message: error.message })
    },
  })

  // Test connection mutation
  const testConnectionMutation = useMutation({
    mutationFn: async () =>
      fetchJSON<ApiResponse>('/api/integrations/smartthings/test', {
        method: 'POST',
      }),
    onSuccess: (data) => {
      setBanner({ tone: data.success ? 'success' : 'error', message: data.message })
      queryClient.invalidateQueries({ queryKey: ['smartthings-config'] })
    },
    onError: (error: Error) => {
      setBanner({ tone: 'error', message: error.message })
    },
  })

  // Delete config mutation
  const deleteConfigMutation = useMutation({
    mutationFn: async () =>
      fetchJSON<ApiResponse>('/api/integrations/smartthings/config', {
        method: 'DELETE',
      }),
    onSuccess: (data) => {
      setBanner({ tone: 'success', message: data.message })
      queryClient.invalidateQueries({ queryKey: ['smartthings-config'] })
      queryClient.invalidateQueries({ queryKey: ['smartthings-devices'] })
      setFormState({ name: 'SmartThings', access_token: '', enabled: true })
    },
    onError: (error: Error) => {
      setBanner({ tone: 'error', message: error.message })
    },
  })

  // Discover devices mutation
  const discoverMutation = useMutation({
    mutationFn: async () =>
      fetchJSON<ApiResponse>('/api/integrations/smartthings/discover', {
        method: 'POST',
      }),
    onSuccess: (data) => {
      setBanner({ tone: 'success', message: data.message })
      queryClient.invalidateQueries({ queryKey: ['smartthings-devices'] })
    },
    onError: (error: Error) => {
      setBanner({ tone: 'error', message: error.message })
    },
  })

  // Enroll device mutation
  const enrollMutation = useMutation({
    mutationFn: async ({ deviceId, enrolled }: { deviceId: number; enrolled: boolean }) =>
      fetchJSON<ApiResponse>(`/api/integrations/smartthings/devices/${deviceId}/enroll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enrolled }),
      }),
    onSuccess: (data) => {
      setBanner({ tone: 'success', message: data.message })
      queryClient.invalidateQueries({ queryKey: ['smartthings-devices'] })
    },
    onError: (error: Error) => {
      setBanner({ tone: 'error', message: error.message })
    },
  })

  // Link device mutation
  const linkMutation = useMutation({
    mutationFn: async ({ deviceId, minerId }: { deviceId: number; minerId: number | null }) =>
      fetchJSON<ApiResponse>(`/api/integrations/smartthings/devices/${deviceId}/link`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ miner_id: minerId }),
      }),
    onSuccess: (data) => {
      setBanner({ tone: 'success', message: data.message })
      queryClient.invalidateQueries({ queryKey: ['smartthings-devices'] })
    },
    onError: (error: Error) => {
      setBanner({ tone: 'error', message: error.message })
    },
  })

  // Safety toggle mutation
  const safetyMutation = useMutation({
    mutationFn: async ({ deviceId, neverAutoControl }: { deviceId: number; neverAutoControl: boolean }) =>
      fetchJSON<ApiResponse>(`/api/integrations/smartthings/devices/${deviceId}/safety`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ never_auto_control: neverAutoControl }),
      }),
    onSuccess: (data) => {
      setBanner({ tone: 'success', message: data.message })
      queryClient.invalidateQueries({ queryKey: ['smartthings-devices'] })
    },
    onError: (error: Error) => {
      setBanner({ tone: 'error', message: error.message })
    },
  })

  const handleSave = () => {
    if (!formState.name.trim()) {
      setBanner({ tone: 'error', message: 'Name is required' })
      return
    }

    if (!config?.configured && !formState.access_token.trim()) {
      setBanner({ tone: 'error', message: 'Personal Access Token is required' })
      return
    }

    saveConfigMutation.mutate({
      name: formState.name,
      access_token: formState.access_token || null,
      enabled: formState.enabled,
    })
  }

  const handleDelete = () => {
    if (!confirm('Are you sure you want to delete SmartThings configuration and all devices?')) {
      return
    }
    deleteConfigMutation.mutate()
  }

  const getDomainIcon = (domain: string) => {
    switch (domain) {
      case 'switch':
        return '🔌'
      case 'light':
        return '💡'
      case 'dimmer':
        return '🎚️'
      case 'thermostat':
        return '🌡️'
      case 'sensor':
        return '📡'
      default:
        return '❓'
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const devices = devicesData?.devices || []

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="flex text-sm text-muted-foreground">
        <a href="/" className="hover:text-foreground">
          Home
        </a>
        <span className="mx-2">/</span>
        <a href="/settings" className="hover:text-foreground">
          Settings
        </a>
        <span className="mx-2">/</span>
        <span className="text-foreground">SmartThings</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">SmartThings Integration</h1>
          <p className="mt-2 text-muted-foreground">
            Control miners via SmartThings devices (bypass Home Assistant)
          </p>
        </div>
        <ConnectionBadge config={config} />
      </div>

      {/* Banner */}
      {banner && (
        <div
          className={`rounded-lg border p-4 ${
            banner.tone === 'success'
              ? 'border-green-500/50 bg-green-500/10 text-green-300'
              : banner.tone === 'error'
              ? 'border-red-500/50 bg-red-500/10 text-red-300'
              : 'border-blue-500/50 bg-blue-500/10 text-blue-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span>{banner.message}</span>
            <button onClick={() => setBanner(null)} className="hover:opacity-70">
              ×
            </button>
          </div>
        </div>
      )}

      {/* Configuration Card */}
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label htmlFor="name" className="text-sm font-medium">
                Name
              </label>
              <input
                type="text"
                id="name"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                value={formState.name}
                onChange={(e) => setFormState({ ...formState, name: e.target.value })}
                placeholder="SmartThings"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="access_token" className="text-sm font-medium">
                Personal Access Token (PAT)
                <a
                  href="https://account.smartthings.com/tokens"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-2 text-xs text-muted-foreground hover:text-foreground"
                >
                  Get PAT →
                </a>
              </label>
              <input
                type="password"
                id="access_token"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                value={formState.access_token}
                onChange={(e) => setFormState({ ...formState, access_token: e.target.value })}
                placeholder={config?.configured ? '••••••••••••' : 'Enter your PAT'}
              />
              {config?.configured && (
                <p className="text-xs text-muted-foreground">Leave empty to keep existing token</p>
              )}
            </div>

            <div className="flex items-center space-x-2 sm:col-span-2">
              <input
                type="checkbox"
                id="enabled"
                className="h-4 w-4 rounded border-gray-300"
                checked={formState.enabled}
                onChange={(e) => setFormState({ ...formState, enabled: e.target.checked })}
              />
              <label htmlFor="enabled" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                Enable SmartThings integration
              </label>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={handleSave} disabled={saveConfigMutation.isPending}>
              {saveConfigMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Configuration'
              )}
            </Button>

            {config?.configured && (
              <>
                <Button variant="outline" onClick={() => testConnectionMutation.mutate()} disabled={testConnectionMutation.isPending}>
                  {testConnectionMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Testing...
                    </>
                  ) : (
                    'Test Connection'
                  )}
                </Button>

                <Button variant="destructive" onClick={handleDelete} disabled={deleteConfigMutation.isPending} className="ml-auto">
                  {deleteConfigMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    <>
                      <Trash2 className="mr-2 h-4 w-4" />
                      Delete Configuration
                    </>
                  )}
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Devices Card */}
      {config?.configured && config.enabled && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Devices</CardTitle>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={showAllDevices}
                    onChange={(e) => setShowAllDevices(e.target.checked)}
                    className="h-4 w-4 rounded"
                  />
                  Show all devices
                </label>
                <Button size="sm" onClick={() => discoverMutation.mutate()} disabled={discoverMutation.isPending}>
                  {discoverMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Discovering...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Discover Devices
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {devicesLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : devices.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                <p>No devices found</p>
                <p className="mt-2 text-sm">Click "Discover Devices" to scan for SmartThings devices</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border text-left text-sm text-muted-foreground">
                      <th className="pb-3 pr-4 font-medium"></th>
                      <th className="pb-3 pr-4 font-medium">Device Name</th>
                      <th className="pb-3 pr-4 font-medium">Type</th>
                      <th className="pb-3 pr-4 font-medium">Linked Miner</th>
                      <th className="pb-3 pr-4 font-medium">Enrolled</th>
                      <th className="pb-3 pr-4 font-medium">Safety Lock</th>
                      <th className="pb-3 font-medium">State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {devices.map((device) => (
                      <tr key={device.id} className="border-b border-border">
                        <td className="py-3 pr-4 text-center text-2xl">{getDomainIcon(device.domain)}</td>
                        <td className="py-3 pr-4">
                          <div>
                            <div className="font-medium">{device.name}</div>
                            <div className="text-xs text-muted-foreground">{device.device_id}</div>
                          </div>
                        </td>
                        <td className="py-3 pr-4">
                          <span className="inline-flex items-center rounded-full bg-secondary px-2 py-0.5 text-xs font-medium">
                            {device.domain}
                          </span>
                        </td>
                        <td className="py-3 pr-4">
                          <Select
                            value={device.miner_id?.toString() || ''}
                            onValueChange={(value) => linkMutation.mutate({ deviceId: device.id, minerId: value ? parseInt(value) : null })}
                          >
                            <SelectTrigger className="w-[180px]">
                              <SelectValue placeholder="Not linked" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="">Not linked</SelectItem>
                              {miners?.map((miner) => (
                                <SelectItem key={miner.id} value={miner.id.toString()}>
                                  {miner.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-3 pr-4">
                          <input
                            type="checkbox"
                            checked={device.enrolled}
                            disabled={!device.miner_id}
                            onChange={(e) => enrollMutation.mutate({ deviceId: device.id, enrolled: e.target.checked })}
                            className="h-4 w-4 rounded"
                          />
                        </td>
                        <td className="py-3 pr-4">
                          <button
                            onClick={() => safetyMutation.mutate({ deviceId: device.id, neverAutoControl: !device.never_auto_control })}
                            className="text-lg hover:opacity-70"
                            title={device.never_auto_control ? 'Safety locked' : 'Not locked'}
                          >
                            {device.never_auto_control ? '🔒' : '🔓'}
                          </button>
                        </td>
                        <td className="py-3">
                          {device.current_state ? (
                            <span
                              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                                device.current_state === 'on' ? 'bg-green-500/15 text-green-300' : 'bg-secondary text-muted-foreground'
                              }`}
                            >
                              {device.current_state.toUpperCase()}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Info Card */}
      <Card>
        <CardHeader>
          <CardTitle>About SmartThings Integration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            This integration allows HMM to control SmartThings devices directly via the SmartThings API, bypassing Home Assistant for
            improved performance and reliability.
          </p>
          <ul className="list-inside list-disc space-y-1">
            <li>Create a Personal Access Token in your SmartThings account</li>
            <li>Discover devices connected to your SmartThings hub</li>
            <li>Link devices to miners for automated control</li>
            <li>Enable enrollment to allow Agile Solo Strategy to control devices</li>
            <li>Use safety lock to prevent automation from controlling critical devices</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
