import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, ChevronDown, ClipboardList, Loader2, RefreshCcw, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { dashboardAPI, type SystemEvent } from '@/lib/api'
import { cn } from '@/lib/utils'

const EVENTS_PER_PAGE = 200
const FILTERS = [
  { label: 'All', value: 'all' },
  { label: 'Info', value: 'info' },
  { label: 'Success', value: 'success' },
  { label: 'Warning', value: 'warning' },
  { label: 'Error', value: 'error' },
] as const

type EventFilter = (typeof FILTERS)[number]['value']
type EventSeverity = Exclude<EventFilter, 'all'>

export default function SystemLogs() {
  const queryClient = useQueryClient()
  const [activeFilter, setActiveFilter] = useState<EventFilter>('all')
  const [currentPage, setCurrentPage] = useState(1)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [banner, setBanner] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

  const eventsQuery = useQuery({
    queryKey: ['system-logs'],
    queryFn: () => dashboardAPI.getEvents(1000).then((response) => response.events),
    refetchInterval: autoRefresh ? 30000 : false,
  })

  const events = useMemo(() => eventsQuery.data ?? [], [eventsQuery.data])

  useEffect(() => {
    setCurrentPage(1)
  }, [activeFilter, events.length])

  useEffect(() => {
    if (!banner) return
    const timeout = window.setTimeout(() => setBanner(null), 4000)
    return () => window.clearTimeout(timeout)
  }, [banner])

  const showBanner = (tone: 'success' | 'error', message: string) => {
    setBanner({ tone, message })
  }

  const counts = useMemo(() => {
    const base: Record<EventFilter, number> = {
      all: events.length,
      info: 0,
      success: 0,
      warning: 0,
      error: 0,
    }
    events.forEach((event) => {
      const category = getSeverity(event.event_type)
      base[category] += 1
    })
    return base
  }, [events])

  const filteredEvents = useMemo(() => {
    if (activeFilter === 'all') return events
    return events.filter((event) => getSeverity(event.event_type) === activeFilter)
  }, [events, activeFilter])

  const totalPages = Math.max(1, Math.ceil(filteredEvents.length / EVENTS_PER_PAGE))
  const paginatedEvents = useMemo(() => {
    const start = (currentPage - 1) * EVENTS_PER_PAGE
    return filteredEvents.slice(start, start + EVENTS_PER_PAGE)
  }, [filteredEvents, currentPage])

  const invalidateEvents = () => queryClient.invalidateQueries({ queryKey: ['system-logs'] })

  const clearMutation = useMutation({
    mutationFn: dashboardAPI.clearEvents,
    onSuccess: () => {
      invalidateEvents()
      setCurrentPage(1)
      showBanner('success', 'All events cleared')
    },
    onError: () => showBanner('error', 'Failed to clear events'),
  })

  const handleClear = () => {
    if (events.length === 0) return
    if (!window.confirm('Clear all system events? This cannot be undone.')) return
    clearMutation.mutate()
  }

  const handlePageChange = (delta: number) => {
    setCurrentPage((prev) => {
      const next = prev + delta
      if (next < 1 || next > totalPages) return prev
      return next
    })
  }

  const lastUpdated = eventsQuery.dataUpdatedAt ? new Date(eventsQuery.dataUpdatedAt).toLocaleTimeString() : '—'

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex items-center gap-3 text-3xl font-semibold text-foreground">
          <ClipboardList className="h-8 w-8 text-blue-400" />
          <span>System Logs</span>
        </div>
        <p className="text-base text-muted-foreground">
          Inspect miner activity, automation outcomes, and integration events without leaving the new dashboard.
        </p>
      </div>

      <Card className="border-border/60 bg-muted/5">
        <CardHeader className="space-y-4">
          {banner && <InlineBanner tone={banner.tone} message={banner.message} />}
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <CardTitle className="text-lg">Recent Events</CardTitle>
            <div className="flex flex-wrap gap-2">
              <AutoRefreshToggle checked={autoRefresh} onCheckedChange={setAutoRefresh} />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void eventsQuery.refetch()}
                disabled={eventsQuery.isFetching}
              >
                {eventsQuery.isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
                Refresh
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleClear}
                disabled={events.length === 0 || clearMutation.isPending}
              >
                {clearMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                Clear all
              </Button>
            </div>
          </div>
          <div className="flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <span>
              Showing {paginatedEvents.length} of {filteredEvents.length} events · Last updated {lastUpdated}
            </span>
            <span>Auto-refresh every 30s when enabled</span>
          </div>
          <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
            {FILTERS.map((filter) => {
              const isExhausted = filter.value !== 'all' && counts[filter.value] === 0
              return (
              <button
                key={filter.value}
                type="button"
                onClick={() => setActiveFilter(filter.value)}
                className={cn(
                  'rounded-xl border border-border/60 bg-background/60 px-4 py-3 text-left transition',
                    activeFilter === filter.value && 'border-blue-500/80 bg-blue-500/10 shadow-inner',
                    isExhausted && 'opacity-60'
                  )}
                >
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">{filter.label}</div>
                  <div className="text-2xl font-semibold text-foreground">{counts[filter.value]}</div>
                </button>
              )
            })}
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {eventsQuery.isLoading && <SkeletonTable />}
          {eventsQuery.isError && (
            <ErrorBanner onRetry={() => void eventsQuery.refetch()} message="Failed to load events." />
          )}
          {!eventsQuery.isLoading && !eventsQuery.isError && paginatedEvents.length === 0 && (
            <EmptyState />
          )}

          {!eventsQuery.isLoading && !eventsQuery.isError && paginatedEvents.length > 0 && (
            <>
              <div className="hidden lg:block">
                <EventsTable events={paginatedEvents} />
              </div>
              <div className="space-y-3 lg:hidden">
                {paginatedEvents.map((event) => (
                  <EventCard key={event.id} event={event} />
                ))}
              </div>
            </>
          )}

          {totalPages > 1 && (
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalEvents={filteredEvents.length}
              onPageChange={handlePageChange}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function getSeverity(eventType: string): EventSeverity {
  const normalized = (eventType || '').toLowerCase()
  if (normalized.includes('error')) return 'error'
  if (normalized.includes('warning')) return 'warning'
  if (normalized.includes('success')) return 'success'
  return 'info'
}

function resolveSource(event: SystemEvent): string {
  const data = (event.data ?? {}) as Record<string, unknown>
  const candidates = ['miner_name', 'miner', 'target', 'source']
  for (const key of candidates) {
    const value = data[key]
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  if (event.source?.startsWith('miner:')) {
    return event.source.split(':')[1] || 'Miner'
  }
  return event.source || 'System'
}

function formatTimestamp(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function EventsTable({ events }: { events: SystemEvent[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border/60">
      <table className="w-full text-sm">
        <thead className="bg-muted/10 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-3 text-left font-semibold">Time</th>
            <th className="px-4 py-3 text-left font-semibold">Source</th>
            <th className="px-4 py-3 text-left font-semibold">Event</th>
            <th className="px-4 py-3 text-left font-semibold">Details</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.id} className="border-t border-border/50">
              <td className="px-4 py-3 align-top text-muted-foreground">{formatTimestamp(event.timestamp)}</td>
              <td className="px-4 py-3 align-top text-foreground">{resolveSource(event)}</td>
              <td className="px-4 py-3 align-top">
                <SeverityBadge eventType={event.event_type} />
              </td>
              <td className="px-4 py-3 align-top text-sm text-muted-foreground">
                <p className="whitespace-pre-line text-foreground">{event.message}</p>
                <EventDataDisclosure data={event.data} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EventCard({ event }: { event: SystemEvent }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{resolveSource(event)}</p>
          <p className="text-xs text-muted-foreground">{formatTimestamp(event.timestamp)}</p>
        </div>
        <SeverityBadge eventType={event.event_type} />
      </div>
      <p className="mt-3 text-sm text-foreground">{event.message}</p>
      <EventDataDisclosure data={event.data} />
    </div>
  )
}

function SeverityBadge({ eventType }: { eventType: string }) {
  const severity = getSeverity(eventType)
  const tone =
    severity === 'error'
      ? 'bg-red-500/20 text-red-200'
      : severity === 'warning'
        ? 'bg-amber-500/20 text-amber-200'
        : severity === 'success'
          ? 'bg-emerald-500/20 text-emerald-200'
          : 'bg-blue-500/20 text-blue-200'

  return (
    <span className={cn('inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold capitalize', tone)}>
      {eventType || severity}
    </span>
  )
}

function Pagination({
  currentPage,
  totalPages,
  totalEvents,
  onPageChange,
}: {
  currentPage: number
  totalPages: number
  totalEvents: number
  onPageChange: (delta: number) => void
}) {
  return (
    <div className="flex flex-col gap-3 border-t border-border/40 pt-4 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
      <span>
        Page {currentPage} of {totalPages} · {totalEvents} event{totalEvents === 1 ? '' : 's'}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(-1)}
          disabled={currentPage === 1}
        >
          Previous
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(1)}
          disabled={currentPage === totalPages}
        >
          Next
        </Button>
      </div>
    </div>
  )
}

function SkeletonTable() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, idx) => (
        <div key={idx} className="h-16 animate-pulse rounded-2xl bg-muted/20" />
      ))}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="rounded-2xl border border-dashed border-border/60 bg-background/40 p-6 text-center">
      <p className="text-base font-semibold text-foreground">No events yet</p>
      <p className="mt-1 text-sm text-muted-foreground">
        When miners change pools, automations fire, or integrations respond, entries will appear here.
      </p>
    </div>
  )
}

function InlineBanner({ tone, message }: { tone: 'success' | 'error'; message: string }) {
  const toneClasses = tone === 'success'
    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
    : 'border-red-500/40 bg-red-500/10 text-red-100'
  const Icon = tone === 'success' ? CheckCircle2 : AlertCircle
  return (
    <div className={cn('flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm', toneClasses)}>
      <Icon className="h-4 w-4" />
      <span>{message}</span>
    </div>
  )
}

function EventDataDisclosure({ data }: { data?: SystemEvent['data'] }) {
  const [expanded, setExpanded] = useState(false)
  if (!data) return null
  const payload = JSON.stringify(data, null, 2)
  return (
    <div className="mt-3 rounded-xl border border-border/40 bg-muted/10">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        aria-expanded={expanded}
      >
        <span>{expanded ? 'Hide payload' : 'Show payload'}</span>
        <ChevronDown className={cn('h-4 w-4 transition-transform', expanded && 'rotate-180')} />
      </button>
      {expanded && (
        <pre className="max-h-64 overflow-auto border-t border-border/40 px-3 py-2 text-xs text-muted-foreground">
          {payload}
        </pre>
      )}
    </div>
  )
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-100">
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

function AutoRefreshToggle({
  checked,
  onCheckedChange,
}: {
  checked: boolean
  onCheckedChange: (value: boolean) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        'relative inline-flex items-center rounded-full border border-border/70 bg-gray-800 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground transition',
        checked && 'border-emerald-400/70 bg-emerald-500/10 text-emerald-100'
      )}
    >
      <span
        className={cn(
          'mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full border border-border/50 bg-background text-[10px] font-bold',
          checked && 'border-emerald-400/70 text-emerald-200'
        )}
      >
        {checked ? 'ON' : 'OFF'}
      </span>
      Auto-refresh
    </button>
  )
}

