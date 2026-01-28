import { Hammer } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function PoolIntegrations() {
  return (
    <SettingsPlaceholder
      title="Pool Integrations"
      description="Configure Solopool.org and Braiins Pool API integrations."
      icon={<Hammer className="h-10 w-10 text-blue-400" />}
    />
  )
}
