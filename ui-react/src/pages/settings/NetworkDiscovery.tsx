import { Radar } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function NetworkDiscovery() {
  return (
    <SettingsPlaceholder
      title="Network Discovery"
      description="Configure automatic miner discovery and network scanning."
      icon={<Radar className="h-10 w-10 text-blue-400" />}
    />
  )
}
