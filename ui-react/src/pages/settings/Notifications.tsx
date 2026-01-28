import { BellRing } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function Notifications() {
  return (
    <SettingsPlaceholder
      title="Notifications"
      description="Configure Telegram and Discord alerts for miner events."
      icon={<BellRing className="h-10 w-10 text-blue-400" />}
    />
  )
}
