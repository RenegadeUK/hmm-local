import { ShieldCheck } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function AuditLogs() {
  return (
    <SettingsPlaceholder
      title="Audit Logs"
      description="Track configuration changes and system actions."
      icon={<ShieldCheck className="h-10 w-10 text-blue-400" />}
    />
  )
}
