import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import PoolFormDialog from '@/components/pools/PoolFormDialog'
import type { Pool } from '@/types/telemetry'
import type {
  PoolFormValues,
  PoolHealthOverview,
  PoolHealthStatus,
} from '@/types/pools'
import {
  Activity,
  AlertCircle,
  Eye,
  EyeOff,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Waves,
  Wrench,
} from 'lucide-react'

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    ...init,
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    const message = errorBody.detail || errorBody.message || `Request failed (${response.status})`
    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

function getHealthTone(score?: number | null) {
  if (typeof score !== 'number') {
    return { label: 'No data', className: 'text-gray-400' }
  }
  if (score >= 70) return { label: 'Healthy', className: 'text-green-400' }
  if (score >= 40) return { label: 'Fair', className: 'text-yellow-400' }
  return { label: 'Critical', className: 'text-red-400' }
}

function formatMetric(value?: number | null, suffix = '') {
  if (value === null || value === undefined) return '—'
  return `${value}${suffix}`
}

export default function Pools() {
  const queryClient = useQueryClient()
  const [formMode, setFormMode] = useState<'add' | 'edit'>('add')
  const [formOpen, setFormOpen] = useState(false)
  const [selectedPool, setSelectedPool] = useState<Pool | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Pool | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const {
    data: pools = [],
    isLoading: poolsLoading,
    error: poolsError,
  } = useQuery<Pool[]>({
    queryKey: ['pools'],
    queryFn: () => fetchJSON<Pool[]>('/api/pools/'),
  })

  const {
    data: healthOverview,
    isLoading: healthLoading,
    error: healthError,
  } = useQuery<PoolHealthOverview>({
    queryKey: ['pool-health-overview'],
    queryFn: () => fetchJSON<PoolHealthOverview>('/api/pools/health/overview'),
    refetchInterval: 60000,
  })

  const healthByPoolId = useMemo(() => {
    const map = new Map<number, PoolHealthStatus>()
    healthOverview?.pools.forEach((status) => map.set(status.pool_id, status))
    return map
  }, [healthOverview])

  const createPoolMutation = useMutation({
    mutationFn: (payload: PoolFormValues) => {
      const { id: _omitId, ...body } = payload
      return fetchJSON<Pool>('/api/pools/', {
        method: 'POST',
        body: JSON.stringify(body),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
      queryClient.invalidateQueries({ queryKey: ['pool-health-overview'] })
    },
  })

  const updatePoolMutation = useMutation({
    mutationFn: (payload: PoolFormValues) => {
      if (!payload.id) {
        throw new Error('Pool ID missing')
      }
      const { id, ...rest } = payload
      return fetchJSON<Pool>(`/api/pools/${id}`, {
        method: 'PUT',
        body: JSON.stringify(rest),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
      queryClient.invalidateQueries({ queryKey: ['pool-health-overview'] })
    },
  })

  const deletePoolMutation = useMutation({
    mutationFn: (poolId: number) =>
      fetchJSON(`/api/pools/${poolId}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
      queryClient.invalidateQueries({ queryKey: ['pool-health-overview'] })
    },
  })

  const toggleDashboardMutation = useMutation({
    mutationFn: ({ poolId, show }: { poolId: number; show: boolean }) =>
      fetchJSON<Pool>(`/api/pools/${poolId}`, {
        method: 'PUT',
        body: JSON.stringify({ show_on_dashboard: show }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const isSavingPool = createPoolMutation.isPending || updatePoolMutation.isPending

  const sortedPools = useMemo(() => {
    return [...pools].sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()))
  }, [pools])

  const handleAddPool = () => {
    setFormMode('add')
    setSelectedPool(null)
    setFormOpen(true)
  }

  const handleEditPool = (pool: Pool) => {
    setFormMode('edit')
    setSelectedPool(pool)
    setFormOpen(true)
  }

  const handleFormSubmit = async (values: PoolFormValues) => {
    if (formMode === 'add') {
      await createPoolMutation.mutateAsync(values)
    } else {
      await updatePoolMutation.mutateAsync(values)
    }
  }

  const handleDelete = (pool: Pool) => {
    setDeleteTarget(pool)
    setDeleteError(null)
    setDeleteDialogOpen(true)
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    try {
      await deletePoolMutation.mutateAsync(deleteTarget.id)
      setDeleteDialogOpen(false)
      setDeleteTarget(null)
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : 'Unable to delete pool')
    }
  }

  const handleToggleDashboard = async (pool: Pool) => {
    await toggleDashboardMutation.mutateAsync({
      poolId: pool.id,
      show: !pool.show_on_dashboard,
    })
  }

  const poolsErrorMessage = poolsError instanceof Error ? poolsError.message : null
  const healthErrorMessage = healthError instanceof Error ? healthError.message : null

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 text-sm uppercase tracking-widest text-blue-300">
          <Waves className="h-5 w-5" />
          <span>Pools</span>
        </div>
        <h1 className="text-2xl font-semibold">Pool Management</h1>
        <p className="text-gray-400 text-sm">
          Review pool health, manage approved providers, and keep Braiins Pool telemetry in sync.
        </p>
        <div className="flex flex-wrap gap-3 pt-4">
          <Button onClick={handleAddPool} className="flex items-center gap-2">
            <Plus className="h-4 w-4" />
            Add Pool
          </Button>
          <Button variant="outline" onClick={() => queryClient.invalidateQueries({ queryKey: ['pool-health-overview'] })} className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Refresh Health
          </Button>
        </div>
      </div>

      {healthOverview && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-gray-400">Total Pools</p>
              <p className="text-2xl font-semibold mt-2">{healthOverview.total_pools}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-gray-400">Healthy</p>
              <div className="flex items-baseline gap-2 mt-2">
                <p className="text-2xl font-semibold text-green-400">{healthOverview.healthy_pools}</p>
                <span className="text-sm text-gray-500">/{healthOverview.total_pools}</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-gray-400">Avg Response Time</p>
              <p className="text-2xl font-semibold mt-2">{formatMetric(healthOverview.avg_response_time_ms, 'ms')}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-gray-400">Avg Reject Rate</p>
              <p className="text-2xl font-semibold mt-2">{formatMetric(healthOverview.avg_reject_rate, '%')}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {(poolsErrorMessage || healthErrorMessage) && (
        <div className="flex items-center gap-3 rounded-md border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          <AlertCircle className="h-4 w-4" />
          <span>{poolsErrorMessage || healthErrorMessage}</span>
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-1">
            <h2 className="text-xl font-semibold">Configured Pools</h2>
            <p className="text-sm text-gray-400">Only approved Solopool and Braiins providers are shown.</p>
          </div>
        </CardHeader>
        <CardContent>
          {poolsLoading || healthLoading ? (
            <div className="flex min-h-[200px] items-center justify-center text-gray-400">Loading pools…</div>
          ) : sortedPools.length === 0 ? (
            <div className="rounded-md border border-dashed border-gray-700 p-8 text-center">
              <p className="text-gray-300 font-medium">No pools configured yet</p>
              <p className="text-sm text-gray-500 mt-2">Use the Add Pool button to connect your preferred provider.</p>
              <Button onClick={handleAddPool} className="mt-4">Add Pool</Button>
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {sortedPools.map((pool) => {
                const health = healthByPoolId.get(pool.id)
                const tone = getHealthTone(health?.health_score)
                return (
                  <div key={pool.id} className="rounded-xl border border-gray-800 bg-gray-950/60 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-lg font-semibold">{pool.name}</span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                              pool.enabled ? 'bg-green-500/10 text-green-300' : 'bg-gray-600/20 text-gray-400'
                            }`}
                          >
                            {pool.enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </div>
                        <p className="text-sm text-gray-500 mt-1">{pool.url}:{pool.port}</p>
                        <p className="text-xs text-gray-500 mt-1">Worker: {pool.user}</p>
                      </div>
                      <div className={`text-sm font-medium ${tone.className}`}>{tone.label}</div>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                      <div>
                        <p className="text-xs text-gray-500 uppercase">Health Score</p>
                        <p className="text-lg font-semibold">{health?.health_score ?? '—'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 uppercase">Response</p>
                        <p className="text-lg font-semibold">{formatMetric(health?.response_time_ms, 'ms')}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 uppercase">Reject Rate</p>
                        <p className="text-lg font-semibold">{formatMetric(health?.reject_rate, '%')}</p>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-gray-500">
                      <div className="flex items-center gap-1">
                        <ShieldCheck className="h-3.5 w-3.5" />
                        Active miners: {health?.active_miners ?? 0}
                      </div>
                      <div className="flex items-center gap-1">
                        <Activity className="h-3.5 w-3.5" />
                        {health?.last_checked ? new Date(health.last_checked).toLocaleTimeString() : 'No checks yet'}
                      </div>
                      {health?.error_message && (
                        <div className="flex items-center gap-1 text-red-300">
                          <ShieldAlert className="h-3.5 w-3.5" />
                          {health.error_message}
                        </div>
                      )}
                    </div>

                    <div className="mt-5 flex flex-wrap gap-3">
                      <Button
                        variant="secondary"
                        size="sm"
                        className="flex items-center gap-2"
                        onClick={() => handleToggleDashboard(pool)}
                        disabled={toggleDashboardMutation.isPending}
                      >
                        {pool.show_on_dashboard ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                        {pool.show_on_dashboard ? 'Hide from Dashboard' : 'Show on Dashboard'}
                      </Button>
                      <Button variant="secondary" size="sm" className="flex items-center gap-2" onClick={() => handleEditPool(pool)}>
                        <Wrench className="h-4 w-4" />
                        Edit
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        className="flex items-center gap-2"
                        onClick={() => handleDelete(pool)}
                        disabled={deletePoolMutation.isPending && deleteTarget?.id === pool.id}
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <PoolFormDialog
        open={formOpen}
        mode={formMode}
        pool={selectedPool}
        isSubmitting={isSavingPool}
        onOpenChange={(open) => {
          setFormOpen(open)
          if (!open) {
            setSelectedPool(null)
            setFormMode('add')
          }
        }}
        onSubmit={handleFormSubmit}
      />

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">Delete pool</DialogTitle>
            <DialogDescription>
              This action removes the pool from every miner and automation rule. You can re-add it later using the approved presets.
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm text-gray-300">
            {deleteTarget ? `${deleteTarget.name} (${deleteTarget.url}:${deleteTarget.port})` : ''}
          </p>
          {deleteError && (
            <div className="flex items-center gap-2 text-sm text-red-300">
              <AlertCircle className="h-4 w-4" />
              <span>{deleteError}</span>
            </div>
          )}
          <DialogFooter className="gap-3">
            <Button variant="secondary" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deletePoolMutation.isPending}>
              {deletePoolMutation.isPending ? 'Deleting…' : 'Delete Pool'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  )
}
