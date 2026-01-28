import { Palette } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function Defaults() {
  return (
    <SettingsPlaceholder
      title="Defaults"
      description="Customize application appearance and default behaviors."
      icon={<Palette className="h-10 w-10 text-blue-400" />}
    />
  )
}
