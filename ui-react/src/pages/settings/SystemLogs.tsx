import { ClipboardList } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function SystemLogs() {
  return (
    <SettingsPlaceholder
      title="System Logs"
      description="View system events, errors, and activity logs."
      icon={<ClipboardList className="h-10 w-10 text-blue-400" />}
    />
  )
}
