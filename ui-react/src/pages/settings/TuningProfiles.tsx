import { SlidersHorizontal } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function TuningProfiles() {
  return (
    <SettingsPlaceholder
      title="Tuning Profiles"
      description="Create and manage overclocking profiles for your miners."
      icon={<SlidersHorizontal className="h-10 w-10 text-blue-400" />}
    />
  )
}
