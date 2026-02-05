import { useEffect, useMemo, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Pool } from '@/types/telemetry'
import type { PoolFormValues, PoolPreset } from '@/types/pools'
import { AlertCircle, CreditCard, Info, Loader2 } from 'lucide-react'

interface PoolTemplate {
  pool_type: string
  pool_display_name: string
  template_id: string
  display_name: string
  url: string
  port: number
  coin: string
  mining_model: 'solo' | 'pool'
  region: string | null
  requires_auth: boolean
  supports_shares: boolean
  supports_earnings: boolean
  supports_balance: boolean
  description: string | null
  fee_percent: number | null
}

export interface PoolFormDialogProps {
  open: boolean
  mode: 'add' | 'edit'
  pool?: Pool | null
  isSubmitting: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (values: PoolFormValues) => Promise<void>
}

export default function PoolFormDialog({
  open,
  mode,
  pool,
  isSubmitting,
  onOpenChange,
  onSubmit,
}: PoolFormDialogProps) {
  const [selectedPresetKey, setSelectedPresetKey] = useState('')
  const [walletOrUser, setWalletOrUser] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  
  // Fetch templates from API
  const [templates, setTemplates] = useState<PoolTemplate[]>([])
  const [templatesLoading, setTemplatesLoading] = useState(true)
  const [templatesError, setTemplatesError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    
    fetch('/api/pool-templates')
      .then(res => {
        if (!res.ok) throw new Error(`Failed to fetch templates: ${res.statusText}`)
        return res.json()
      })
      .then((data: PoolTemplate[]) => {
        if (isMounted) {
          setTemplates(data)
          setTemplatesLoading(false)
        }
      })
      .catch(err => {
        if (isMounted) {
          setTemplatesError(err.message)
          setTemplatesLoading(false)
        }
      })
    
    return () => { isMounted = false }
  }, [])

  // Transform templates into grouped format for Select component
  const templateGroups = useMemo(() => {
    const groups: { label: string; options: PoolPreset[] }[] = []
    const groupMap = new Map<string, PoolPreset[]>()

    templates.forEach(template => {
      const groupLabel = `${template.pool_display_name} · ${template.coin}`
      const preset: PoolPreset = {
        key: template.template_id,
        name: template.display_name,
        url: template.url,
        port: template.port,
        group: groupLabel,
        subtitle: [
          template.region || 'Global',
          template.mining_model === 'solo' ? 'Solo mining' : 'Pool mining',
          template.fee_percent !== null && template.fee_percent > 0 ? `${template.fee_percent}% fee` : '0% fee'
        ].join(' · ')
      }

      if (!groupMap.has(groupLabel)) {
        groupMap.set(groupLabel, [])
      }
      groupMap.get(groupLabel)!.push(preset)
    })

    groupMap.forEach((options, label) => {
      groups.push({ label, options })
    })

    return groups
  }, [templates])

  // Create lookup for quick preset access
  const PRESET_LOOKUP = useMemo(() => {
    const lookup: Record<string, PoolPreset> = {}
    templateGroups.forEach(group => {
      group.options.forEach(option => {
        lookup[option.key] = option
      })
    })
    return lookup
  }, [templateGroups])

  const presetDetails = useMemo(() => {
    return selectedPresetKey ? PRESET_LOOKUP[selectedPresetKey] : null
  }, [selectedPresetKey, PRESET_LOOKUP])

  useEffect(() => {
    if (open) {
      if (mode === 'edit' && pool) {
        setWalletOrUser(pool.user || '')
        setEnabled(pool.enabled)
      } else {
        setWalletOrUser('')
        setEnabled(true)
        setSelectedPresetKey('')
      }
      setErrorMessage(null)
    } else {
      setWalletOrUser('')
      setSelectedPresetKey('')
      setErrorMessage(null)
    }
  }, [open, mode, pool])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()

    const trimmedUser = walletOrUser.trim()

    if (mode === 'add' && !selectedPresetKey) {
      setErrorMessage('Select an approved pool provider to continue.')
      return
    }

    if (!trimmedUser) {
      setErrorMessage('Wallet address / username is required.')
      return
    }

    let targetPreset: PoolPreset | undefined
    if (mode === 'add') {
      targetPreset = PRESET_LOOKUP[selectedPresetKey]
      if (!targetPreset) {
        setErrorMessage('Invalid pool preset selected.')
        return
      }
    }

    const payload: PoolFormValues = {
      id: pool?.id,
      name: mode === 'add' ? targetPreset!.name : pool?.name || '',
      url: mode === 'add' ? targetPreset!.url : pool?.url || '',
      port: mode === 'add' ? targetPreset!.port : pool?.port || 0,
      user: trimmedUser,
      password: pool?.password || 'x',
      enabled,
    }

    try {
      await onSubmit(payload)
      onOpenChange(false)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to save pool settings.')
    }
  }

  const title = mode === 'add' ? 'Add Mining Pool' : 'Edit Pool'
  const description =
    mode === 'add'
      ? 'Select an approved provider and supply the wallet address or username you use with that pool.'
      : 'Update the wallet address / username and status for this pool. Provider settings remain locked for safety.'

  const readOnlyDetails = mode === 'edit' && pool

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold flex items-center gap-2">
            <CreditCard className="h-5 w-5 text-blue-400" />
            {title}
          </DialogTitle>
          <DialogDescription className="text-gray-400">{description}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {mode === 'add' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="provider">1️⃣ Pool Provider</Label>
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <Info className="h-4 w-4" />
                  {templatesLoading ? 'Loading templates...' : `${templates.length} templates available`}
                </div>
              </div>
              
              {templatesLoading ? (
                <div className="flex items-center justify-center p-8 text-gray-400">
                  <Loader2 className="h-6 w-6 animate-spin mr-2" />
                  <span>Loading pool templates...</span>
                </div>
              ) : templatesError ? (
                <div className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>{templatesError}</span>
                </div>
              ) : (
                <>
                  <Select value={selectedPresetKey} onValueChange={setSelectedPresetKey}>
                    <SelectTrigger id="provider">
                      <SelectValue placeholder="Choose a pool" />
                    </SelectTrigger>
                    <SelectContent>
                      {templateGroups.map((group) => (
                        <SelectGroup key={group.label}>
                          <SelectLabel>{group.label}</SelectLabel>
                          {group.options.map((option) => (
                            <SelectItem key={option.key} value={option.key}>
                              <div className="flex flex-col">
                                <span>{option.name}</span>
                                {option.subtitle && <span className="text-xs text-gray-400">{option.subtitle}</span>}
                              </div>
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      ))}
                    </SelectContent>
                  </Select>
                  {presetDetails && (
                    <div className="rounded-lg border border-gray-700 bg-gray-900/60 p-4 text-sm">
                      <p className="text-gray-300 font-medium">{presetDetails.name}</p>
                      <p className="text-gray-400 mt-1">
                        {presetDetails.url}:{presetDetails.port}
                      </p>
                      <p className="text-gray-500 mt-2">
                        These connection details are locked to ensure reliability.
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {readOnlyDetails && (
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <Label>Pool Name</Label>
                <input
                  type="text"
                  value={pool.name}
                  disabled
                  className="mt-2 w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-400"
                />
              </div>
              <div>
                <Label>URL</Label>
                <input
                  type="text"
                  value={pool.url}
                  disabled
                  className="mt-2 w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-400"
                />
              </div>
              <div>
                <Label>Port</Label>
                <input
                  type="text"
                  value={pool.port}
                  disabled
                  className="mt-2 w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-400"
                />
              </div>
            </div>
          )}

          <div className="space-y-3">
            <Label htmlFor="wallet">2️⃣ Wallet Address / Username</Label>
            <div className="relative">
              <input
                id="wallet"
                type="text"
                value={walletOrUser}
                onChange={(event) => setWalletOrUser(event.target.value)}
                placeholder="paste your Braiins username or Solopool wallet"
                className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                disabled={templatesLoading}
              />
              <CreditCard className="absolute right-3 top-2.5 h-4 w-4 text-gray-500" />
            </div>
            <p className="text-sm text-gray-400">
              This is the only editable field per pool. Passwords default to &quot;x&quot; for all approved providers.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Checkbox id="enabled" checked={enabled} onCheckedChange={(checked) => setEnabled(Boolean(checked))} />
            <Label htmlFor="enabled" className="text-sm">
              Pool enabled
            </Label>
          </div>

          {errorMessage && (
            <div className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          <DialogFooter className="gap-3 sm:gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || templatesLoading} className="min-w-[140px]">
              {isSubmitting ? 'Saving…' : mode === 'add' ? 'Add Pool' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
