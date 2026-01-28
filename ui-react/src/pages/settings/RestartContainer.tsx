import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, Loader2, Power, RefreshCw, ShieldAlert, Zap } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { maintenanceAPI } from '@/lib/api'
import { cn } from '@/lib/utils'

type ConfirmStep = 'idle' | 'stage-one' | 'stage-two'
type BannerTone = 'success' | 'error' | 'info'

export default function RestartContainer() {
  const [confirmStep, setConfirmStep] = useState<ConfirmStep>('idle')
  const [banner, setBanner] = useState<{ tone: BannerTone; message: string } | null>(null)
  const [countdown, setCountdown] = useState<number | null>(null)

  const restartMutation = useMutation({
    mutationFn: () => maintenanceAPI.restartContainer(),
    onSuccess: () => {
      setBanner({ tone: 'success', message: 'Restart initiated. Hold tight while the container reboots.' })
      setCountdown(10)
      setConfirmStep('idle')
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to restart container'
      setBanner({ tone: 'error', message })
      setConfirmStep('idle')
    },
  })

  useEffect(() => {
    if (countdown === null) return
    if (countdown <= 0) {
      window.location.reload()
      return
    }
    const timer = window.setTimeout(() => setCountdown((value) => (value ?? 0) - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [countdown])

  const handleRestart = () => {
    restartMutation.mutate()
  }

  const openConfirm = () => setConfirmStep('stage-one')
  const closeConfirm = () => setConfirmStep('idle')

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex items-center gap-3 text-3xl font-semibold text-foreground">
          <RefreshCw className="h-8 w-8 text-red-400" />
          <span>Restart Container</span>
        </div>
        <p className="text-base text-muted-foreground">
          Initiate a safe restart of the HMM container. All miners remain unaffected, but the dashboard and APIs will be
          unavailable for a brief period (~10 seconds) while the service restarts.
        </p>
      </div>

      {banner && <Banner tone={banner.tone} message={banner.message} onDismiss={() => setBanner(null)} />}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="border border-red-500/40 bg-red-500/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-lg text-red-200">
              <ShieldAlert className="h-5 w-5" />
              Before you restart
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-red-100">
            <ChecklistItem label="All API requests will fail during the restart window." />
            <ChecklistItem label="Telemetry ingestion pauses until the container returns." />
            <ChecklistItem label="CLI/Docker access is required if the restart does not complete." />
            <div className="rounded-xl border border-red-500/50 bg-red-500/10 p-3 text-xs">
              Safety tip: run restarts during low activity windows. Automations resume automatically once the container
              is back online.
            </div>
          </CardContent>
        </Card>

        <Card className="border border-border/60">
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-lg">
              <Power className="h-5 w-5 text-red-300" />
              Controlled restart
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="rounded-2xl border border-border/60 bg-muted/5 p-4 text-sm text-muted-foreground">
              This flow mirrors the legacy double confirmation + countdown overlay but keeps you inside the new React
              experience. Once confirmed, we POST to `/api/settings/restart` and give you a visual countdown until the
              page reloads.
            </div>

            <div className="space-y-2 text-sm">
              <p className="font-semibold text-foreground">Restart impact</p>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                <li>Dashboard & API go offline for ~10 seconds</li>
                <li>Miners continue hashing (they connect to pools directly)</li>
                <li>Automation engine resumes pending jobs automatically</li>
              </ul>
            </div>

            <Button
              variant="destructive"
              className="w-full justify-center"
              onClick={openConfirm}
              disabled={restartMutation.isPending}
            >
              {restartMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Zap className="mr-2 h-4 w-4" />}
              Restart container
            </Button>

            {countdown !== null && <CountdownOverlay seconds={countdown} />}
          </CardContent>
        </Card>
      </div>

      <ConfirmModal
        step={confirmStep}
        onCancel={closeConfirm}
        onConfirm={() => setConfirmStep('stage-two')}
        onRestart={() => {
          closeConfirm()
          handleRestart()
        }}
        isRestarting={restartMutation.isPending}
      />
    </div>
  )
}

function ChecklistItem({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs">
      <AlertTriangle className="h-4 w-4" />
      <span>{label}</span>
    </div>
  )
}

function Banner({ tone, message, onDismiss }: { tone: BannerTone; message: string; onDismiss: () => void }) {
  const styles =
    tone === 'success'
      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
      : tone === 'error'
        ? 'border-red-500/40 bg-red-500/10 text-red-100'
        : 'border-blue-500/40 bg-blue-500/10 text-blue-100'
  return (
    <div className={cn('flex items-center justify-between rounded-xl border px-4 py-3 text-sm', styles)}>
      <span>{message}</span>
      <Button variant="ghost" size="sm" className="text-current" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  )
}

function ConfirmModal({
  step,
  onCancel,
  onConfirm,
  onRestart,
  isRestarting,
}: {
  step: ConfirmStep
  onCancel: () => void
  onConfirm: () => void
  onRestart: () => void
  isRestarting: boolean
}) {
  if (step === 'idle') return null
  const isStageTwo = step === 'stage-two'
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-2xl border border-border/60 bg-background p-6 text-sm text-foreground">
        <div className="flex items-center gap-3 text-lg font-semibold text-red-300">
          <ShieldAlert className="h-5 w-5" />
          {isStageTwo ? 'Final confirmation' : 'Confirm restart'}
        </div>
        <p className="mt-3 text-muted-foreground">
          {isStageTwo
            ? 'This is your last chance to cancel. The container restart takes all UI/API services offline temporarily.'
            : 'Restarting interrupts any active API calls and temporarily pauses telemetry ingestion. Continue?'}
        </p>
        <div className="mt-5 flex flex-wrap justify-end gap-3">
          <Button variant="ghost" onClick={onCancel} disabled={isRestarting}>
            Cancel
          </Button>
          {!isStageTwo && (
            <Button variant="secondary" onClick={onConfirm}>
              Continue
            </Button>
          )}
          {isStageTwo && (
            <Button variant="destructive" onClick={onRestart} disabled={isRestarting}>
              {isRestarting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Zap className="mr-2 h-4 w-4" />}
              Restart now
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

function CountdownOverlay({ seconds }: { seconds: number }) {
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/70">
      <div className="rounded-2xl border border-border/70 bg-background/95 p-6 text-center text-foreground">
        <div className="text-5xl font-bold text-red-300">{seconds}s</div>
        <p className="mt-2 text-sm text-muted-foreground">Restart in progress… page will refresh automatically.</p>
      </div>
    </div>
  )
}
