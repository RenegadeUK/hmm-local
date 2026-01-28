import { ReactNode } from 'react'

interface SettingsPlaceholderProps {
  title: string
  description: string
  icon?: ReactNode
  children?: ReactNode
}

export function SettingsPlaceholder({ title, description, icon, children }: SettingsPlaceholderProps) {
  return (
    <div className="space-y-6 rounded-2xl border border-border/40 bg-muted/5 p-8">
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3 text-3xl font-semibold">
          {icon}
          <span>{title}</span>
        </div>
        <p className="max-w-3xl text-base text-muted-foreground">{description}</p>
      </div>
      <div className="rounded-xl border border-dashed border-border/60 bg-background/40 p-6 text-sm text-muted-foreground">
        {children ?? (
          <>
            <p className="font-medium text-foreground">React migration placeholder</p>
            <p>
              This view will be rebuilt here next. Until then, refer back to the classic dashboard version to manage these
              settings.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
