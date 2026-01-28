import { ReactNode, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ChevronRight,
  ClipboardList,
  Loader2,
  RefreshCcw,
  ShieldCheck,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { auditAPI, type AuditLogEntry, type AuditStatsResponse } from '@/lib/api'
import { cn } from '@/lib/utils'

const RESOURCE_TYPES = [
  { label: 'All resources', value: '' },
  { label: 'Miner', value: 'miner' },
  { label: 'Pool', value: 'pool' },
  { label: 'Strategy', value: 'strategy' },
  { label: 'Automation', value: 'automation' },
  { label: 'Discovery', value: 'discovery' },
  { label: 'Profile', value: 'profile' },
]

const ACTIONS = [
  { label: 'All actions', value: '' },
  { label: 'Create', value: 'create' },
  { label: 'Update', value: 'update' },
  { label: 'Delete', value: 'delete' },
  { label: 'Execute', value: 'execute' },
  { label: 'Enable', value: 'enable' },
  { label: 'Disable', value: 'disable' },
]

const RANGE_OPTIONS = [
  { label: 'Last 24 hours', value: 1 },
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 90 days', value: 90 },
]

export default function AuditLogs() {
  const [resourceType, setResourceType] = useState('')
  const [action, setAction] = useState('')
  const [days, setDays] = useState(7)
  const [selectedLog, setSelectedLog] = useState<AuditLogEntry | null>(null)

  const logsQuery = useQuery({
    queryKey: ['audit-logs', resourceType, action, days],
    queryFn: () =>
      auditAPI.getLogs({
        resourceType: resourceType || undefined,
        action: action || undefined,
        days,
        limit: 250,
      }),
  })

  const statsQuery = useQuery({
    queryKey: ['audit-stats', days],
    queryFn: () => auditAPI.getStats(days),
  })

  const logs = logsQuery.data ?? []
  const stats = statsQuery.data

  const topAction = useMemo(() => pickTop(stats?.by_action), [stats?.by_action])
  const topResource = useMemo(
    () => pickTop(stats?.by_resource_type),
    [stats?.by_resource_type]
  )
  const topUser = useMemo(() => pickTop(stats?.by_user), [stats?.by_user])

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <div className="flex items-center gap-3 text-3xl font-semibold text-foreground">
          <ShieldCheck className="h-8 w-8 text-blue-400" />
          <span>Audit Logs</span>
        </div>
        <p className="text-base text-muted-foreground">
          Trace configuration changes, automation actions, and system activity. Use the filters to narrow down specific resources or actions.
        </p>
      </header>

      <StatsSection stats={stats} topAction={topAction} topResource={topResource} topUser={topUser} />

      <Card className="border-border/60 bg-muted/5">
        <CardHeader className="space-y-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <CardTitle className="text-lg">Filters</CardTitle>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => logsQuery.refetch()}
              disabled={logsQuery.isFetching}
            >
              {logsQuery.isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </div>
          <div className="grid gap-4 md:grid-cols-4">
            <FilterSelect
              label="Resource type"
              value={resourceType}
              onChange={setResourceType}
              options={RESOURCE_TYPES}
            />
            <FilterSelect label="Action" value={action} onChange={setAction} options={ACTIONS} />
            <FilterSelect
              label="Time range"
              value={String(days)}
              onChange={(value) => setDays(Number(value))}
              options={RANGE_OPTIONS.map((option) => ({ label: option.label, value: String(option.value) }))}
            />
            <div className="flex items-end">
              <Button
                type="button"
                variant="ghost"
                className="w-full justify-center"
                onClick={() => {
                  setResourceType('')
                  setAction('')
                  setDays(7)
                }}
                disabled={!resourceType && !action && days === 7}
              >
                Reset
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {logsQuery.isError && <ErrorBanner message="Failed to load audit logs." onRetry={() => logsQuery.refetch()} />}
          {logsQuery.isLoading && <SkeletonRows count={6} />}
          {!logsQuery.isLoading && !logsQuery.isError && logs.length === 0 && (
            <EmptyState icon={<ClipboardList className="h-6 w-6" />} message="No audit events match the current filters." />
          )}

          {!logsQuery.isLoading && !logsQuery.isError && logs.length > 0 && (
            <>
              <div className="hidden lg:block">
                <AuditTable logs={logs} onViewChanges={setSelectedLog} />
              </div>
              <div className="space-y-3 lg:hidden">
                {logs.map((log) => (
                  <AuditCard key={log.id} log={log} onViewChanges={setSelectedLog} />
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <ChangesModal log={selectedLog} onClose={() => setSelectedLog(null)} />
    </div>
  )
}

function StatsSection({
  stats,
  topAction,
  topResource,
  topUser,
}: {
  stats?: AuditStatsResponse
  topAction?: string | null
  topResource?: string | null
  topUser?: string | null
}) {
  const successRate = stats ? `${stats.success_rate.toFixed(1)}%` : '—'
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      <StatTile label="Total events" value={stats?.total_events?.toLocaleString() ?? '—'} />
      <StatTile label="Success rate" value={successRate} />
      <StatTile label="Most common action" value={topAction ?? '—'} subtle="From selected window" />
      <StatTile label="Most referenced resource" value={topResource ?? '—'} subtle="Based on by_resource" />
      <StatTile label="Busiest actor" value={topUser ?? '—'} subtle="Based on by_user counts" />
    </div>
  )
}

function StatTile({ label, value, subtle }: { label: string; value: string; subtle?: string }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-muted/5 p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold text-foreground">{value}</p>
      {subtle && <p className="text-xs text-muted-foreground">{subtle}</p>}
    </div>
  )
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { label: string; value: string }[]
}) {
  return (
    <label className="text-sm text-muted-foreground">
      <span className="mb-1 block text-xs uppercase tracking-wide">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-border/60 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
      >
        {options.map((option) => (
          <option key={option.value || 'all'} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function AuditTable({ logs, onViewChanges }: { logs: AuditLogEntry[]; onViewChanges: (log: AuditLogEntry) => void }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border/60">
      <table className="w-full text-sm">
        <thead className="bg-muted/10 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-3 text-left font-semibold">Timestamp</th>
            <th className="px-4 py-3 text-left font-semibold">Action</th>
            <th className="px-4 py-3 text-left font-semibold">Resource</th>
            <th className="px-4 py-3 text-left font-semibold">User</th>
            <th className="px-4 py-3 text-left font-semibold">IP</th>
            <th className="px-4 py-3 text-left font-semibold">Status</th>
            <th className="px-4 py-3 text-left font-semibold">Changes</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id} className="border-t border-border/50">
              <td className="px-4 py-3 align-top text-muted-foreground">{formatTimestamp(log.timestamp)}</td>
              <td className="px-4 py-3 align-top"><ActionBadge action={log.action} /></td>
              <td className="px-4 py-3 align-top">
                <div className="font-semibold text-foreground capitalize">{log.resource_type || 'system'}</div>
                {log.resource_name && (
                  <div className="text-xs text-muted-foreground">{log.resource_name}</div>
                )}
              </td>
              <td className="px-4 py-3 align-top text-foreground">{log.user}</td>
              <td className="px-4 py-3 align-top text-muted-foreground">{log.ip_address || '—'}</td>
              <td className="px-4 py-3 align-top"><StatusBadge status={log.status} /></td>
              <td className="px-4 py-3 align-top">
                {log.changes ? (
                  <Button variant="link" className="px-0" onClick={() => onViewChanges(log)}>
                    View
                  </Button>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AuditCard({ log, onViewChanges }: { log: AuditLogEntry; onViewChanges: (log: AuditLogEntry) => void }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{log.user}</p>
          <p className="text-xs text-muted-foreground">{formatTimestamp(log.timestamp)}</p>
        </div>
        <ActionBadge action={log.action} />
      </div>
      <div className="mt-3 space-y-2 text-sm">
        <p className="text-muted-foreground">
          <span className="text-foreground">Resource:</span> {log.resource_type}
          {log.resource_name && <span className="text-muted-foreground"> · {log.resource_name}</span>}
        </p>
        <p className="text-muted-foreground">
          <span className="text-foreground">Status:</span> <StatusBadge status={log.status} />
        </p>
        <p className="text-muted-foreground">
          <span className="text-foreground">IP:</span> {log.ip_address || '—'}
        </p>
        {log.error_message && (
          <p className="text-xs text-red-300">{log.error_message}</p>
        )}
      </div>
      {log.changes && (
        <Button variant="ghost" className="mt-3 w-full justify-between" onClick={() => onViewChanges(log)}>
          View changes
          <ChevronRight className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}

function ActionBadge({ action }: { action: string }) {
  const tone =
    action === 'create'
      ? 'bg-emerald-500/20 text-emerald-200'
      : action === 'update'
        ? 'bg-blue-500/20 text-blue-200'
        : action === 'delete'
          ? 'bg-red-500/20 text-red-200'
          : action === 'execute'
            ? 'bg-amber-500/20 text-amber-100'
            : action === 'enable'
              ? 'bg-purple-500/20 text-purple-200'
              : 'bg-slate-500/20 text-slate-200'
  return (
    <span className={cn('inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold capitalize', tone)}>
      {action || 'unknown'}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const normalized = (status || '').toLowerCase()
  const tone = normalized === 'failure' ? 'bg-red-500/20 text-red-200' : 'bg-emerald-500/20 text-emerald-200'
  return (
    <span className={cn('inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold capitalize', tone)}>
      {status || 'unknown'}
    </span>
  )
}

function ChangesModal({ log, onClose }: { log: AuditLogEntry | null; onClose: () => void }) {
  if (!log?.changes) return null
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border/60 bg-background p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="text-base font-semibold text-foreground">Change details</p>
            <p className="text-xs text-muted-foreground">{formatTimestamp(log.timestamp)}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        <pre className="max-h-[60vh] overflow-auto rounded-xl bg-muted/10 px-4 py-3 text-xs text-muted-foreground">
          {JSON.stringify(log.changes, null, 2)}
        </pre>
      </div>
    </div>
  )
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-100">
      <div className="flex items-center gap-2">
        <AlertCircle className="h-4 w-4" />
        <span>{message}</span>
      </div>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, idx) => (
        <div key={idx} className="h-16 animate-pulse rounded-2xl bg-muted/20" />
      ))}
    </div>
  )
}

function EmptyState({ icon, message }: { icon: ReactNode; message: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border/60 bg-background/40 p-8 text-center text-sm text-muted-foreground">
      <div className="rounded-full border border-border/50 p-3 text-foreground">{icon}</div>
      <p className="text-base font-semibold text-foreground">Nothing to show</p>
      <p>{message}</p>
    </div>
  )
}

function formatTimestamp(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function pickTop(map?: Record<string, number>): string | null {
  if (!map) return null
  const entries = Object.entries(map).sort((a, b) => b[1] - a[1])
  return entries.length > 0 ? entries[0][0] : null
}
