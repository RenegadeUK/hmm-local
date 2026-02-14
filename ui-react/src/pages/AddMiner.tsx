import { useState, useMemo } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { AlertCircle, Info } from 'lucide-react'
const IPV4_REGEX = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(?:\.|$)){4}$/

const MINER_LABELS: Record<string, string> = {
  avalon_nano: 'Avalon Nano 3 / 3S',
  bitaxe: 'Bitaxe 601',
  nerdqaxe: 'NerdQaxe++',
  nmminer: 'NMMiner ESP32',
}

type MinerTypeDetail = {
  badge: 'success' | 'info'
  title: string
  bullets: string[]
  showPassword?: boolean
}

const MINER_TYPE_DETAILS: Record<string, MinerTypeDetail> = {
  avalon_nano: {
    badge: 'success',
    title: 'Avalon Nano · Dynamic Pool Control',
    bullets: [
      'Full remote pool management via cgminer TCP API',
      'Price band strategy can switch pools automatically',
      "Requires admin password (default 'admin') to push pool changes",
    ],
    showPassword: true,
  },
  bitaxe: {
    badge: 'success',
    title: 'Bitaxe · Full Control',
    bullets: [
      'Supports dynamic pool switching to any configured pool',
      'Power and frequency tuning available',
      'Multiple performance profiles supported',
    ],
  },
  nerdqaxe: {
    badge: 'success',
    title: 'NerdQaxe++ · Full Control',
    bullets: [
      'Supports dynamic pool switching and tuning',
      'Automation engine can apply band-based profiles',
      'Tracks temperature, power, and reject metrics',
    ],
  },
  nmminer: {
    badge: 'info',
    title: 'NMMiner ESP32 · UDP Telemetry',
    bullets: [
      'Telemetry is broadcast over UDP every few seconds',
      'Pool configuration is sent via UDP port 12347',
      'Limited automation—no power metrics or tuning data',
    ],
  },
}

type MinerTypesResponse = {
  types: string[]
}

interface MinerPayload {
  name: string
  miner_type: string
  ip_address: string
  port: number | null
  config?: Record<string, unknown>
}

export default function AddMiner() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [name, setName] = useState('')
  const [minerType, setMinerType] = useState('')
  const [ipAddress, setIpAddress] = useState('')
  const [port, setPort] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const { data: minerTypes = [], isLoading: typesLoading } = useQuery<string[]>({
    queryKey: ['miner-types'],
    queryFn: async () => {
      const response = await fetch('/api/miners/types')
      if (!response.ok) {
        throw new Error('Failed to load miner types')
      }
      const payload: MinerTypesResponse = await response.json()
      return payload.types || []
    },
  })

  const selectedTypeDetail: MinerTypeDetail | undefined = useMemo(() => {
    return minerType ? MINER_TYPE_DETAILS[minerType] : undefined
  }, [minerType])

  const mutation = useMutation({
    mutationFn: async (payload: MinerPayload) => {
      const response = await fetch('/api/miners/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}))
        throw new Error(errorBody.detail || 'Failed to add miner')
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['miners'] })
      navigate('/miners')
    },
  })

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setFormError(null)

    if (!name.trim() || !minerType || !ipAddress.trim()) {
      setFormError('Name, miner type, and IP address are required.')
      return
    }

    if (!IPV4_REGEX.test(ipAddress.trim())) {
      setFormError('Enter a valid IPv4 address (e.g., 192.168.0.42).')
      return
    }

    const payload: MinerPayload = {
      name: name.trim(),
      miner_type: minerType,
      ip_address: ipAddress.trim(),
      port: port ? parseInt(port, 10) : null,
    }

    if (minerType === 'avalon_nano' && adminPassword.trim()) {
      payload.config = { admin_password: adminPassword.trim() }
    }

    try {
      await mutation.mutateAsync(payload)
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Failed to add miner')
    }
  }

  return (
    <div className="p-6">
      <div className="max-w-3xl mx-auto">
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-1">
              <p className="text-sm uppercase tracking-wider text-blue-300">Miners</p>
              <h1 className="text-2xl font-semibold">Add New Miner</h1>
              <p className="text-gray-400 text-sm">
                Provide the device details below. Pool presets and automation logic come straight from your existing configuration.
              </p>
            </div>
          </CardHeader>
          <CardContent>
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <Label htmlFor="name">Miner Name</Label>
                <input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g., Avalon Nano #1"
                  className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="miner-type">Miner Type</Label>
                <select
                  id="miner-type"
                  value={minerType}
                  onChange={(event) => setMinerType(event.target.value)}
                  disabled={typesLoading}
                  className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40 disabled:opacity-60"
                  required
                >
                  <option value="" disabled>
                    {typesLoading ? 'Loading miner types…' : 'Select miner type'}
                  </option>
                  {minerTypes
                    .filter((type) => MINER_LABELS[type])
                    .map((type) => (
                      <option key={type} value={type}>
                        {MINER_LABELS[type]}
                      </option>
                    ))}
                </select>
                {selectedTypeDetail && (
                  <div
                    className={`mt-3 rounded-lg border px-4 py-3 text-sm ${
                      selectedTypeDetail.badge === 'success'
                        ? 'border-green-500/30 bg-green-500/5 text-green-200'
                        : 'border-blue-400/40 bg-blue-400/5 text-blue-100'
                    }`}
                  >
                    <p className="font-semibold flex items-center gap-2">
                      <Info className="h-4 w-4" />
                      {selectedTypeDetail.title}
                    </p>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-gray-200">
                      {selectedTypeDetail.bullets.map((bullet) => (
                        <li key={bullet}>{bullet}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="ip-address">IP Address</Label>
                  <input
                    id="ip-address"
                    type="text"
                    value={ipAddress}
                    onChange={(event) => setIpAddress(event.target.value)}
                    placeholder="192.168.1.120"
                    pattern="^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(?:\.|$)){4}$"
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                    required
                  />
                  <p className="text-xs text-gray-500">Use the static IP configured on the miner.</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="port">Port (optional)</Label>
                  <input
                    id="port"
                    type="number"
                    value={port}
                    onChange={(event) => setPort(event.target.value)}
                    min={1}
                    max={65535}
                    placeholder="Default per miner type"
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  />
                </div>
              </div>

              {selectedTypeDetail?.showPassword && (
                <div className="space-y-2">
                  <Label htmlFor="admin-password">Avalon Nano Admin Password</Label>
                  <input
                    id="admin-password"
                    type="password"
                    value={adminPassword}
                    onChange={(event) => setAdminPassword(event.target.value)}
                    placeholder="Default is 'admin'"
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  />
                  <p className="text-xs text-gray-500">Needed for remote pool configuration. Leave blank to use the device default.</p>
                </div>
              )}

              {formError && (
                <div className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
                  <AlertCircle className="h-4 w-4" />
                  <span>{formError}</span>
                </div>
              )}

              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={mutation.isPending} className="min-w-[140px]">
                  {mutation.isPending ? 'Adding Miner…' : 'Add Miner'}
                </Button>
                <Button type="button" variant="secondary" asChild>
                  <Link to="/miners">Cancel</Link>
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
