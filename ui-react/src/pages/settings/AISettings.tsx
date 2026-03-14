import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Bot, Cable, Loader2, PlugZap, ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  APIError,
  aiAPI,
  type AIConfigResponse,
  type AITestPayload,
  type SaveAIConfigPayload,
} from '@/lib/api'
import { cn } from '@/lib/utils'

type BannerTone = 'success' | 'error' | 'info'
type TestStatus = { tone: BannerTone; message: string }

const OPENAI_MODELS = [
  { value: 'gpt-4o', label: 'GPT-4o (recommended)' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini (cheaper)' },
  { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
]

const OLLAMA_MODELS = [
  { value: 'qwen2.5-coder:7b', label: 'Qwen 2.5 Coder 7B (function calling)' },
  { value: 'llama3.1:8b', label: 'Llama 3.1 8B' },
  { value: 'mistral:7b', label: 'Mistral 7B' },
  { value: 'qwen2.5:7b', label: 'Qwen 2.5 7B' },
  { value: 'custom', label: 'Custom model…' },
]

const OPENAI_BASE_URL = 'https://api.openai.com/v1'
const DEFAULT_OLLAMA_BASE_URL = 'http://localhost:11434/v1'
const MIN_TOKENS = 100
const MAX_TOKENS = 4000

interface OpenAIFormState {
  enabled: boolean
  apiKey: string
  model: string
  maxTokens: number
}

interface OllamaFormState {
  enabled: boolean
  baseUrl: string
  model: string
  customModel: string
  maxTokens: number
}

const defaultOpenAIForm: OpenAIFormState = {
  enabled: false,
  apiKey: '',
  model: OPENAI_MODELS[0].value,
  maxTokens: 1000,
}

const defaultOllamaForm: OllamaFormState = {
  enabled: false,
  baseUrl: DEFAULT_OLLAMA_BASE_URL,
  model: OLLAMA_MODELS[0].value,
  customModel: '',
  maxTokens: 1000,
}

export default function AISettings() {
  const queryClient = useQueryClient()
  const [banner, setBanner] = useState<{ tone: BannerTone; message: string } | null>(null)
  const [openAIForm, setOpenAIForm] = useState<OpenAIFormState>(defaultOpenAIForm)
  const [ollamaForm, setOllamaForm] = useState<OllamaFormState>(defaultOllamaForm)
  const [openAIStoredKey, setOpenAIStoredKey] = useState(false)
  const [isChangingOpenAIKey, setIsChangingOpenAIKey] = useState(false)
  const [openAIError, setOpenAIError] = useState<string | null>(null)
  const [ollamaError, setOllamaError] = useState<string | null>(null)
  const [openAITestStatus, setOpenAITestStatus] = useState<TestStatus | null>(null)
  const [ollamaTestStatus, setOllamaTestStatus] = useState<TestStatus | null>(null)
  const [pendingProvider, setPendingProvider] = useState<'openai' | 'ollama' | null>(null)

  const configQuery = useQuery({
    queryKey: ['ai-config'],
    queryFn: aiAPI.getConfig,
  })

  useEffect(() => {
    if (!configQuery.data) return
    hydrateForms(configQuery.data)
  }, [configQuery.data])

  const hydrateForms = (config: AIConfigResponse) => {
    if (config.provider === 'openai') {
      setOpenAIForm((current) => ({
        ...current,
        enabled: config.enabled,
        model: config.model ?? OPENAI_MODELS[0].value,
        maxTokens: clampTokens(config.max_tokens ?? 1000),
        apiKey: '',
      }))
      setOpenAIStoredKey(Boolean(config.api_key))
      setIsChangingOpenAIKey(false)
    } else {
      setOpenAIStoredKey(false)
      setIsChangingOpenAIKey(false)
      setOpenAIForm(() => ({ ...defaultOpenAIForm }))
      const storedModel = config.model ?? OLLAMA_MODELS[0].value
      const isPreset = OLLAMA_MODELS.some((option) => option.value === storedModel)
      setOllamaForm((current) => ({
        ...current,
        enabled: config.enabled,
        baseUrl: config.base_url ?? DEFAULT_OLLAMA_BASE_URL,
        model: isPreset ? storedModel : 'custom',
        customModel: isPreset ? '' : storedModel,
        maxTokens: clampTokens(config.max_tokens ?? 1000),
      }))
    }
  }

  const showBanner = (tone: BannerTone, message: string) => {
    setBanner({ tone, message })
    window.setTimeout(() => setBanner(null), 5000)
  }

  const extractError = (error: unknown) => {
    if (error instanceof APIError) {
      if (error.data && typeof error.data === 'object' && 'detail' in error.data) {
        const detail = (error.data as { detail?: unknown }).detail
        if (typeof detail === 'string') return detail
      }
      return error.message
    }
    if (error instanceof Error) return error.message
    return 'Something went wrong'
  }

  const saveConfigMutation = useMutation({
    mutationFn: (payload: SaveAIConfigPayload) => aiAPI.saveConfig(payload),
    onMutate: (variables) => {
      setPendingProvider(variables.provider)
    },
    onSuccess: (response, variables) => {
      if (!response.success) {
        showBanner('error', response.error || 'Failed to save AI settings')
        return
      }
      showBanner('success', `${variables.provider === 'openai' ? 'OpenAI' : 'Ollama'} settings saved`)
      queryClient.invalidateQueries({ queryKey: ['ai-config'] })
      if (variables.provider === 'openai') {
        setOpenAIForm((current) => ({ ...current, apiKey: '' }))
        if (variables.api_key) {
          setOpenAIStoredKey(true)
        }
        setIsChangingOpenAIKey(false)
      }
    },
    onError: (error) => showBanner('error', extractError(error)),
    onSettled: () => setPendingProvider(null),
  })

  const openAITestMutation = useMutation({
    mutationFn: (payload: AITestPayload) => aiAPI.testConnection(payload),
    onMutate: () => setOpenAITestStatus({ tone: 'info', message: 'Testing OpenAI connection…' }),
    onSuccess: (result) => {
      setOpenAITestStatus({
        tone: result.success ? 'success' : 'error',
        message: result.success ? result.message ?? 'OpenAI connection ok' : result.error ?? 'OpenAI test failed',
      })
    },
    onError: (error) => setOpenAITestStatus({ tone: 'error', message: extractError(error) }),
  })

  const ollamaTestMutation = useMutation({
    mutationFn: (payload: AITestPayload) => aiAPI.testConnection(payload),
    onMutate: () => setOllamaTestStatus({ tone: 'info', message: 'Checking Ollama host…' }),
    onSuccess: (result) => {
      setOllamaTestStatus({
        tone: result.success ? 'success' : 'error',
        message: result.success ? result.message ?? 'Ollama connection ok' : result.error ?? 'Ollama test failed',
      })
    },
    onError: (error) => setOllamaTestStatus({ tone: 'error', message: extractError(error) }),
  })

  const handleOpenAISubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setOpenAIError(null)

    const enteredApiKey = openAIForm.apiKey.trim()
    const keyRequired = openAIForm.enabled && (!openAIStoredKey || isChangingOpenAIKey)

    if (keyRequired && !enteredApiKey) {
      setOpenAIError('Enter your OpenAI API key to enable the integration.')
      return
    }

    const payload: SaveAIConfigPayload = {
      enabled: openAIForm.enabled,
      provider: 'openai',
      model: openAIForm.model,
      max_tokens: clampTokens(openAIForm.maxTokens),
      base_url: OPENAI_BASE_URL,
    }

    if (enteredApiKey) {
      payload.api_key = enteredApiKey
    }

    saveConfigMutation.mutate(payload, {
      onSuccess: () => setOpenAITestStatus(null),
    })
  }

  const handleOllamaSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setOllamaError(null)

    const baseUrl = ollamaForm.baseUrl.trim()
    if (!baseUrl) {
      setOllamaError('Enter the Ollama base URL (http://host:11434/v1).')
      return
    }

    const effectiveModel =
      ollamaForm.model === 'custom' ? ollamaForm.customModel.trim() : ollamaForm.model
    if (!effectiveModel) {
      setOllamaError('Select or enter the model name to use.')
      return
    }

    const payload: SaveAIConfigPayload = {
      enabled: ollamaForm.enabled,
      provider: 'ollama',
      model: effectiveModel,
      max_tokens: clampTokens(ollamaForm.maxTokens),
      base_url: baseUrl,
      api_key: 'ollama',
    }

    saveConfigMutation.mutate(payload, {
      onSuccess: () => setOllamaTestStatus(null),
    })
  }

  const handleOpenAITest = () => {
    setOpenAITestStatus(null)
    if (!openAIForm.apiKey.trim()) {
      setOpenAITestStatus({ tone: 'error', message: 'Enter your API key to test connectivity.' })
      return
    }
    openAITestMutation.mutate({
      provider: 'openai',
      api_key: openAIForm.apiKey.trim(),
      model: openAIForm.model,
      base_url: OPENAI_BASE_URL,
    })
  }

  const handleOllamaTest = () => {
    setOllamaTestStatus(null)
    const baseUrl = ollamaForm.baseUrl.trim()
    if (!baseUrl) {
      setOllamaTestStatus({ tone: 'error', message: 'Enter the Ollama base URL first.' })
      return
    }
    const model =
      ollamaForm.model === 'custom' ? ollamaForm.customModel.trim() : ollamaForm.model
    if (!model) {
      setOllamaTestStatus({ tone: 'error', message: 'Select or enter a model before testing.' })
      return
    }
    ollamaTestMutation.mutate({
      provider: 'ollama',
      model,
      base_url: baseUrl,
    })
  }

  const activeSummary = useMemo(() => {
    const config = configQuery.data
    if (!config) return null
    const providerLabel = config.provider === 'ollama' ? 'Ollama (local)' : 'OpenAI (cloud)'
    return {
      providerLabel,
      enabled: config.enabled,
      model: config.model,
      baseUrl: config.base_url,
    }
  }, [configQuery.data])

  const savingOpenAI = saveConfigMutation.isPending && pendingProvider === 'openai'
  const savingOllama = saveConfigMutation.isPending && pendingProvider === 'ollama'

  if (configQuery.isLoading) {
    return <AISettingsSkeleton />
  }

  if (configQuery.isError) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3 text-3xl font-semibold text-foreground">
          <Bot className="h-8 w-8 text-blue-400" />
          AI Settings
        </div>
        <ErrorState message={extractError(configQuery.error)} onRetry={() => configQuery.refetch()} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex items-center gap-3 text-3xl font-semibold text-foreground">
          <Bot className="h-8 w-8 text-blue-400" />
          <span>AI Settings</span>
        </div>
        <p className="text-base text-muted-foreground">
          Wire up OpenAI or Ollama for AI-powered automation, anomaly detection, and future copilots. Only one
          provider is active at a time—configure both so you can switch instantly.
        </p>
      </div>

      {banner && (
        <div
          className={cn(
            'rounded-xl border px-4 py-3 text-sm',
            banner.tone === 'success' && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100',
            banner.tone === 'error' && 'border-red-500/40 bg-red-500/10 text-red-100',
            banner.tone === 'info' && 'border-blue-500/40 bg-blue-500/10 text-blue-100'
          )}
        >
          {banner.message}
        </div>
      )}

      {activeSummary && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-lg">
              <ShieldCheck className="h-5 w-5 text-blue-300" />
              Active provider
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-3">
            <SummaryField label="Provider" value={activeSummary.providerLabel} />
            <SummaryField label="Status" value={activeSummary.enabled ? 'Enabled' : 'Disabled'} />
            <SummaryField label="Model" value={activeSummary.model || 'Not configured'} />
            {activeSummary.baseUrl && (
              <SummaryField label="Base URL" value={activeSummary.baseUrl} spanFull />
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border border-border/60">
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-lg">
              <PlugZap className="h-5 w-5 text-blue-300" />
              OpenAI (cloud)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-5" onSubmit={handleOpenAISubmit}>
              <ToggleRow
                label="Enable OpenAI"
                description="Use GPT models via OpenAI's hosted API."
                checked={openAIForm.enabled}
                onChange={(value) => setOpenAIForm((current) => ({ ...current, enabled: value }))}
              />

              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">API key</label>
                {openAIStoredKey && !isChangingOpenAIKey ? (
                  <div className="space-y-2 rounded-lg border border-border/70 bg-muted/5 px-3 py-3">
                    <div className="text-sm text-foreground">Stored API key is configured.</div>
                    <div className="flex gap-2">
                      <Button type="button" variant="secondary" onClick={() => setIsChangingOpenAIKey(true)}>
                        Change API key
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <input
                      type="password"
                      value={openAIForm.apiKey}
                      onChange={(event) => setOpenAIForm((current) => ({ ...current, apiKey: event.target.value }))}
                      className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                      placeholder="sk-..."
                      autoComplete="off"
                    />
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs text-muted-foreground">
                        Keys are stored encrypted and never shown.
                      </p>
                      {openAIStoredKey && isChangingOpenAIKey && (
                        <button
                          type="button"
                          className="text-xs text-muted-foreground underline-offset-4 hover:underline"
                          onClick={() => {
                            setIsChangingOpenAIKey(false)
                            setOpenAIForm((current) => ({ ...current, apiKey: '' }))
                          }}
                        >
                          Keep existing key
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Model</label>
                <select
                  value={openAIForm.model}
                  onChange={(event) => setOpenAIForm((current) => ({ ...current, model: event.target.value }))}
                  className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                >
                  {OPENAI_MODELS.map((model) => (
                    <option key={model.value} value={model.value}>
                      {model.label}
                    </option>
                  ))}
                </select>
              </div>

              <NumberField
                label="Max response tokens"
                value={openAIForm.maxTokens}
                onChange={(value) => setOpenAIForm((current) => ({ ...current, maxTokens: value }))}
              />

              {openAIError && <p className="text-sm text-red-300">{openAIError}</p>}

              {openAITestStatus && (
                <StatusPill tone={openAITestStatus.tone} message={openAITestStatus.message} />
              )}

              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={savingOpenAI}>
                  {savingOpenAI && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Save OpenAI config
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={openAITestMutation.isPending}
                  onClick={handleOpenAITest}
                >
                  {openAITestMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Cable className="mr-2 h-4 w-4" />
                  )}
                  Test connection
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card className="border border-border/60">
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-lg">
              <Cable className="h-5 w-5 text-blue-300" />
              Ollama (local)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-5" onSubmit={handleOllamaSubmit}>
              <ToggleRow
                label="Enable Ollama"
                description="Use local models without cloud costs."
                checked={ollamaForm.enabled}
                onChange={(value) => setOllamaForm((current) => ({ ...current, enabled: value }))}
              />

              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Base URL</label>
                <input
                  type="text"
                  value={ollamaForm.baseUrl}
                  onChange={(event) => setOllamaForm((current) => ({ ...current, baseUrl: event.target.value }))}
                  className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                  placeholder="http://localhost:11434/v1"
                />
                <p className="text-xs text-muted-foreground">
                  Use <code>http://ollama:11434/v1</code> when both services run in Docker.
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Model</label>
                <select
                  value={ollamaForm.model}
                  onChange={(event) =>
                    setOllamaForm((current) => ({
                      ...current,
                      model: event.target.value,
                      customModel: event.target.value === 'custom' ? current.customModel : '',
                    }))
                  }
                  className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                >
                  {OLLAMA_MODELS.map((model) => (
                    <option key={model.value} value={model.value}>
                      {model.label}
                    </option>
                  ))}
                </select>
              </div>

              {ollamaForm.model === 'custom' && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Custom model name</label>
                  <input
                    type="text"
                    value={ollamaForm.customModel}
                    onChange={(event) =>
                      setOllamaForm((current) => ({ ...current, customModel: event.target.value }))
                    }
                    className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                    placeholder="e.g., llama3.1:70b"
                  />
                </div>
              )}

              <NumberField
                label="Max response tokens"
                value={ollamaForm.maxTokens}
                onChange={(value) => setOllamaForm((current) => ({ ...current, maxTokens: value }))}
              />

              {ollamaError && <p className="text-sm text-red-300">{ollamaError}</p>}

              {ollamaTestStatus && (
                <StatusPill tone={ollamaTestStatus.tone} message={ollamaTestStatus.message} />
              )}

              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={savingOllama}>
                  {savingOllama && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Save Ollama config
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={ollamaTestMutation.isPending}
                  onClick={handleOllamaTest}
                >
                  {ollamaTestMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <PlugZap className="mr-2 h-4 w-4" />
                  )}
                  Test connection
                </Button>
              </div>

              <div className="rounded-xl border border-border/60 bg-muted/5 p-3 text-xs text-muted-foreground">
                Tip: run <code>ollama pull qwen2.5-coder:7b</code> before enabling so the model is available locally.
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function clampTokens(value: number) {
  if (Number.isNaN(value)) return 1000
  return Math.min(MAX_TOKENS, Math.max(MIN_TOKENS, value))
}

function SummaryField({ label, value, spanFull }: { label: string; value: string; spanFull?: boolean }) {
  return (
    <div className={cn('space-y-1', spanFull && 'md:col-span-3')}>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm font-semibold text-foreground break-words">{value || '—'}</p>
    </div>
  )
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string
  description: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-border/60 bg-muted/5 px-4 py-3">
      <div>
        <p className="text-sm font-semibold text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn(
          'flex h-6 w-12 items-center rounded-full border border-border px-0.5 transition-colors',
          checked ? 'bg-blue-500/80 border-blue-400' : 'bg-gray-800'
        )}
        aria-pressed={checked}
      >
        <span
          className={cn(
            'h-5 w-5 rounded-full bg-white shadow transition-transform',
            checked ? 'translate-x-6' : 'translate-x-0'
          )}
        />
      </button>
    </div>
  )
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <input
        type="number"
        min={MIN_TOKENS}
        max={MAX_TOKENS}
        step={100}
        value={value}
        onChange={(event) => onChange(clampTokens(Number(event.target.value)))}
        className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/40"
      />
      <p className="text-xs text-muted-foreground">Between {MIN_TOKENS} and {MAX_TOKENS} tokens.</p>
    </div>
  )
}

function StatusPill({ tone, message }: { tone: BannerTone; message: string }) {
  return (
    <div
      className={cn(
        'rounded-xl border px-3 py-2 text-xs',
        tone === 'success' && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100',
        tone === 'error' && 'border-red-500/40 bg-red-500/10 text-red-100',
        tone === 'info' && 'border-blue-500/40 bg-blue-500/10 text-blue-100'
      )}
    >
      {message}
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
      <div className="flex items-center gap-2">
        <AlertCircle className="h-4 w-4" />
        <span>{message}</span>
      </div>
      <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}

function AISettingsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-8 w-48 animate-pulse rounded bg-muted/20" />
      <div className="h-4 w-3/4 animate-pulse rounded bg-muted/20" />
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, idx) => (
          <div key={idx} className="space-y-3 rounded-2xl border border-border/60 p-4">
            <div className="h-5 w-40 animate-pulse rounded bg-muted/20" />
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((__, innerIdx) => (
                <div key={innerIdx} className="h-10 w-full animate-pulse rounded bg-muted/20" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
