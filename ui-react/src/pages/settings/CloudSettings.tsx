import { Cloud } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function CloudSettings() {
  return (
    <SettingsPlaceholder
      title="Cloud Settings"
      description="Configure cloud sync and monitor all installations from one dashboard."
      icon={<Cloud className="h-10 w-10 text-blue-400" />}
    />
  )
}
