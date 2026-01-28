import { Bot } from 'lucide-react'
import { SettingsPlaceholder } from './SettingsPlaceholder'

export default function AISettings() {
  return (
    <SettingsPlaceholder
      title="AI Settings"
      description="Configure AI integrations such as OpenAI or Ollama."
      icon={<Bot className="h-10 w-10 text-blue-400" />}
    />
  )
}
