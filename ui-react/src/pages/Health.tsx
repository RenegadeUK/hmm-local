export function Health() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Fleet Health</h1>
      </div>

      <div className="rounded-lg border bg-card p-6">
        <p className="text-muted-foreground">
          Fleet health monitoring coming soon. Will show health scores, status indicators,
          and reason codes for each miner.
        </p>
      </div>
    </div>
  )
}
