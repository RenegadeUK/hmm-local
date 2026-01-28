import { RefreshCw } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function RestartContainer() {
  return (
    <SettingsPlaceholder
      title="Restart Container"
      description="Restart the HMM container. All connections will be interrupted temporarily."
      icon={<RefreshCw className="h-10 w-10 text-red-400" />}
    >
      <p className="mb-2">A React-native restart flow will replace the legacy confirm dialogs.</p>
      <p>For now, continue using the classic dashboard button or restart the container manually via Docker.</p>
    </SettingsPlaceholder>
  )
}
