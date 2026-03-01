import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'

type RulePayload = {
  name: string
  enabled: boolean
  trigger_type: string
  trigger_config: Record<string, unknown>
  action_type: string
  action_config: Record<string, unknown>
  priority: number
}

const TRIGGER_OPTIONS = [
  { value: 'price_threshold', label: 'Energy Price Threshold' },
  { value: 'time_window', label: 'Time Window' },
  { value: 'miner_overheat', label: 'Miner Overheat' },
]

const ACTION_OPTIONS = [
  { value: 'apply_mode', label: 'Apply Miner Mode' },
  { value: 'switch_pool', label: 'Switch Pool' },
  { value: 'send_alert', label: 'Send Alert' },
  { value: 'log_event', label: 'Log Event' },
]

const PRICE_CONDITIONS = [
  { value: 'below', label: 'Below threshold' },
  { value: 'above', label: 'Above threshold' },
  { value: 'between', label: 'Between two values' },
  { value: 'outside', label: 'Outside range' },
]

const MODE_OPTIONS = ['low', 'med', 'high', 'eco', 'standard', 'turbo', 'oc']

type MinerOption = {
  id: number
  name: string
  miner_type: string
}

type PoolOption = {
  id: number
  name: string
}

function parseIntStrict(value: string, fieldName: string): number {
  const parsed = Number.parseInt(value, 10)
  if (Number.isNaN(parsed)) {
    throw new Error(`${fieldName} must be a valid integer.`)
  }
  return parsed
}

function parseFloatStrict(value: string, fieldName: string): number {
  const parsed = Number.parseFloat(value)
  if (Number.isNaN(parsed)) {
    throw new Error(`${fieldName} must be a valid number.`)
  }
  return parsed
}

export default function AddAutomationRule() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [triggerType, setTriggerType] = useState(TRIGGER_OPTIONS[0].value)
  const [actionType, setActionType] = useState(ACTION_OPTIONS[0].value)
  const [priceCondition, setPriceCondition] = useState('below')
  const [priceThreshold, setPriceThreshold] = useState('15')
  const [priceThresholdMin, setPriceThresholdMin] = useState('10')
  const [priceThresholdMax, setPriceThresholdMax] = useState('25')
  const [timeStart, setTimeStart] = useState('00:00')
  const [timeEnd, setTimeEnd] = useState('23:59')
  const [overheatMinerId, setOverheatMinerId] = useState('')
  const [overheatThreshold, setOverheatThreshold] = useState('80')
  const [applyModeTarget, setApplyModeTarget] = useState<'single' | 'multi' | 'type'>('single')
  const [applyModeMinerId, setApplyModeMinerId] = useState('')
  const [applyModeMinerIds, setApplyModeMinerIds] = useState<string[]>([])
  const [applyModeMinerType, setApplyModeMinerType] = useState('')
  const [applyModeValue, setApplyModeValue] = useState('eco')
  const [switchPoolMinerId, setSwitchPoolMinerId] = useState('')
  const [switchPoolPoolId, setSwitchPoolPoolId] = useState('')
  const [alertMessage, setAlertMessage] = useState('Automation alert triggered')
  const [eventMessage, setEventMessage] = useState('Automation event logged')
  const [priority, setPriority] = useState('0')
  const [formError, setFormError] = useState<string | null>(null)

  const { data: miners = [] } = useQuery<MinerOption[]>({
    queryKey: ['miners'],
    queryFn: async () => {
      const response = await fetch('/api/miners/')
      if (!response.ok) throw new Error('Failed to load miners')
      return response.json()
    },
  })

  const { data: pools = [] } = useQuery<PoolOption[]>({
    queryKey: ['pools'],
    queryFn: async () => {
      const response = await fetch('/api/pools/')
      if (!response.ok) throw new Error('Failed to load pools')
      return response.json()
    },
  })

  const minerTypes = useMemo(
    () => Array.from(new Set(miners.map((miner) => miner.miner_type))).sort(),
    [miners],
  )

  const toTimeInputValue = (value: string) => {
    if (/^\d{2}:\d{2}$/.test(value)) return value
    return '00:00'
  }

  const createMutation = useMutation({
    mutationFn: async (payload: RulePayload) => {
      const response = await fetch('/api/automation/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}))
        throw new Error(errorBody.detail || 'Failed to create automation rule')
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['automation-rules'] })
      navigate('/automation')
    },
  })

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setFormError(null)

    if (!name.trim()) {
      setFormError('Rule name is required.')
      return
    }

    try {
      const parsedPriority = parseIntStrict(priority, 'Priority')
      let triggerConfig: Record<string, unknown> = {}
      let actionConfig: Record<string, unknown> = {}

      if (triggerType === 'price_threshold') {
        if (priceCondition === 'below' || priceCondition === 'above') {
          triggerConfig = {
            condition: priceCondition,
            threshold: parseFloatStrict(priceThreshold, 'Price threshold'),
          }
        } else {
          const thresholdMin = parseFloatStrict(priceThresholdMin, 'Minimum price threshold')
          const thresholdMax = parseFloatStrict(priceThresholdMax, 'Maximum price threshold')
          if (thresholdMin > thresholdMax) {
            throw new Error('Minimum price threshold cannot be greater than maximum threshold.')
          }
          triggerConfig = {
            condition: priceCondition,
            threshold_min: thresholdMin,
            threshold_max: thresholdMax,
          }
        }
      } else if (triggerType === 'time_window') {
        triggerConfig = {
          start: toTimeInputValue(timeStart),
          end: toTimeInputValue(timeEnd),
        }
      } else if (triggerType === 'miner_overheat') {
        if (!overheatMinerId) {
          throw new Error('Select a miner for overheat trigger.')
        }
        triggerConfig = {
          miner_id: parseIntStrict(overheatMinerId, 'Overheat miner'),
          threshold: parseFloatStrict(overheatThreshold, 'Overheat threshold'),
        }
      }

      if (actionType === 'apply_mode') {
        if (!applyModeValue) {
          throw new Error('Select a mode to apply.')
        }

        if (applyModeTarget === 'type') {
          if (!applyModeMinerType.trim()) {
            throw new Error('Select a miner type to target.')
          }
          actionConfig = {
            miner_id: `type:${applyModeMinerType}`,
            mode: applyModeValue,
          }
        } else if (applyModeTarget === 'multi') {
          if (!applyModeMinerIds.length) {
            throw new Error('Select one or more miners to target.')
          }
          actionConfig = {
            miner_ids: applyModeMinerIds.map((minerId) => parseIntStrict(minerId, 'Apply mode miner list')),
            mode: applyModeValue,
          }
        } else {
          if (!applyModeMinerId) {
            throw new Error('Select a miner to target.')
          }
          actionConfig = {
            miner_id: parseIntStrict(applyModeMinerId, 'Apply mode miner'),
            mode: applyModeValue,
          }
        }
      } else if (actionType === 'switch_pool') {
        if (!switchPoolMinerId || !switchPoolPoolId) {
          throw new Error('Select both miner and pool for switch pool action.')
        }
        actionConfig = {
          miner_id: parseIntStrict(switchPoolMinerId, 'Switch pool miner'),
          pool_id: parseIntStrict(switchPoolPoolId, 'Switch pool target pool'),
        }
      } else if (actionType === 'send_alert') {
        actionConfig = {
          message: alertMessage.trim() || 'Automation alert triggered',
        }
      } else if (actionType === 'log_event') {
        actionConfig = {
          message: eventMessage.trim() || 'Automation event logged',
        }
      }

      const payload: RulePayload = {
        name: name.trim(),
        enabled,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        action_type: actionType,
        action_config: actionConfig,
        priority: parsedPriority,
      }

      await createMutation.mutateAsync(payload)
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Failed to create automation rule')
    }
  }

  return (
    <div className="p-6">
      <div className="max-w-3xl mx-auto">
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-1">
              <p className="text-sm uppercase tracking-wider text-blue-300">Automation</p>
              <h1 className="text-2xl font-semibold">Add Automation Rule</h1>
              <p className="text-gray-400 text-sm">
                Create a new rule with guided fields. No JSON required.
              </p>
            </div>
          </CardHeader>
          <CardContent>
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <Label htmlFor="rule-name">Rule Name</Label>
                <input
                  id="rule-name"
                  type="text"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g., Cheap Power Turbo"
                  className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  required
                />
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="trigger-type">Trigger Type</Label>
                  <select
                    id="trigger-type"
                    value={triggerType}
                    onChange={(event) => setTriggerType(event.target.value)}
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  >
                    {TRIGGER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="action-type">Action Type</Label>
                  <select
                    id="action-type"
                    value={actionType}
                    onChange={(event) => setActionType(event.target.value)}
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  >
                    {ACTION_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {triggerType === 'price_threshold' && (
                <div className="grid gap-6 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label htmlFor="price-condition">Price Condition</Label>
                    <select
                      id="price-condition"
                      value={priceCondition}
                      onChange={(event) => setPriceCondition(event.target.value)}
                      className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                    >
                      {PRICE_CONDITIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {(priceCondition === 'below' || priceCondition === 'above') && (
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="price-threshold">Threshold (p/kWh)</Label>
                      <input
                        id="price-threshold"
                        type="number"
                        step="0.1"
                        value={priceThreshold}
                        onChange={(event) => setPriceThreshold(event.target.value)}
                        className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                      />
                    </div>
                  )}

                  {(priceCondition === 'between' || priceCondition === 'outside') && (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="price-threshold-min">Minimum (p/kWh)</Label>
                        <input
                          id="price-threshold-min"
                          type="number"
                          step="0.1"
                          value={priceThresholdMin}
                          onChange={(event) => setPriceThresholdMin(event.target.value)}
                          className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="price-threshold-max">Maximum (p/kWh)</Label>
                        <input
                          id="price-threshold-max"
                          type="number"
                          step="0.1"
                          value={priceThresholdMax}
                          onChange={(event) => setPriceThresholdMax(event.target.value)}
                          className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                        />
                      </div>
                    </>
                  )}
                </div>
              )}

              {triggerType === 'time_window' && (
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="time-start">Start Time (UTC)</Label>
                    <input
                      id="time-start"
                      type="time"
                      value={toTimeInputValue(timeStart)}
                      onChange={(event) => setTimeStart(event.target.value)}
                      className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="time-end">End Time (UTC)</Label>
                    <input
                      id="time-end"
                      type="time"
                      value={toTimeInputValue(timeEnd)}
                      onChange={(event) => setTimeEnd(event.target.value)}
                      className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                    />
                  </div>
                </div>
              )}

              {triggerType === 'miner_overheat' && (
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="overheat-miner">Miner</Label>
                    <select
                      id="overheat-miner"
                      value={overheatMinerId}
                      onChange={(event) => setOverheatMinerId(event.target.value)}
                      className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                    >
                      <option value="">Select miner</option>
                      {miners.map((miner) => (
                        <option key={miner.id} value={String(miner.id)}>
                          {miner.name} ({miner.miner_type})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="overheat-threshold">Temperature Threshold (°C)</Label>
                    <input
                      id="overheat-threshold"
                      type="number"
                      step="0.1"
                      value={overheatThreshold}
                      onChange={(event) => setOverheatThreshold(event.target.value)}
                      className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                    />
                  </div>
                </div>
              )}

              {actionType === 'apply_mode' && (
                <div className="space-y-6">
                  <div className="grid gap-6 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="apply-target">Target</Label>
                      <select
                        id="apply-target"
                        value={applyModeTarget}
                        onChange={(event) => setApplyModeTarget(event.target.value as 'single' | 'multi' | 'type')}
                        className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                      >
                        <option value="single">Single miner</option>
                        <option value="multi">Selected miners</option>
                        <option value="type">All miners of a type</option>
                      </select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="apply-mode">Mode</Label>
                      <select
                        id="apply-mode"
                        value={applyModeValue}
                        onChange={(event) => setApplyModeValue(event.target.value)}
                        className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                      >
                        {MODE_OPTIONS.map((mode) => (
                          <option key={mode} value={mode}>
                            {mode}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {applyModeTarget === 'single' ? (
                    <div className="space-y-2">
                      <Label htmlFor="apply-mode-miner">Miner</Label>
                      <select
                        id="apply-mode-miner"
                        value={applyModeMinerId}
                        onChange={(event) => setApplyModeMinerId(event.target.value)}
                        className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                      >
                        <option value="">Select miner</option>
                        {miners.map((miner) => (
                          <option key={miner.id} value={String(miner.id)}>
                            {miner.name} ({miner.miner_type})
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : applyModeTarget === 'multi' ? (
                    <div className="space-y-2">
                      <Label htmlFor="apply-mode-miners">Miners</Label>
                      <select
                        id="apply-mode-miners"
                        multiple
                        value={applyModeMinerIds}
                        onChange={(event) =>
                          setApplyModeMinerIds(
                            Array.from(event.target.selectedOptions, (option) => option.value),
                          )
                        }
                        className="w-full h-40 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                      >
                        {miners.map((miner) => (
                          <option key={miner.id} value={String(miner.id)}>
                            {miner.name} ({miner.miner_type})
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-gray-400">Hold Ctrl or Shift to select multiple miners.</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Label htmlFor="apply-mode-type">Miner Type</Label>
                      <select
                        id="apply-mode-type"
                        value={applyModeMinerType}
                        onChange={(event) => setApplyModeMinerType(event.target.value)}
                        className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                      >
                        <option value="">Select type</option>
                        {minerTypes.map((minerType) => (
                          <option key={minerType} value={minerType}>
                            {minerType}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              )}

              {actionType === 'switch_pool' && (
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="switch-pool-miner">Miner</Label>
                    <select
                      id="switch-pool-miner"
                      value={switchPoolMinerId}
                      onChange={(event) => setSwitchPoolMinerId(event.target.value)}
                      className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                    >
                      <option value="">Select miner</option>
                      {miners.map((miner) => (
                        <option key={miner.id} value={String(miner.id)}>
                          {miner.name} ({miner.miner_type})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="switch-pool-target">Pool</Label>
                    <select
                      id="switch-pool-target"
                      value={switchPoolPoolId}
                      onChange={(event) => setSwitchPoolPoolId(event.target.value)}
                      className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                    >
                      <option value="">Select pool</option>
                      {pools.map((pool) => (
                        <option key={pool.id} value={String(pool.id)}>
                          {pool.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {actionType === 'send_alert' && (
                <div className="space-y-2">
                  <Label htmlFor="alert-message">Alert Message</Label>
                  <input
                    id="alert-message"
                    type="text"
                    value={alertMessage}
                    onChange={(event) => setAlertMessage(event.target.value)}
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  />
                </div>
              )}

              {actionType === 'log_event' && (
                <div className="space-y-2">
                  <Label htmlFor="event-message">Event Message</Label>
                  <input
                    id="event-message"
                    type="text"
                    value={eventMessage}
                    onChange={(event) => setEventMessage(event.target.value)}
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  />
                </div>
              )}

              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="priority">Priority</Label>
                  <input
                    id="priority"
                    type="number"
                    value={priority}
                    onChange={(event) => setPriority(event.target.value)}
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="enabled" className="block">Initial Status</Label>
                  <select
                    id="enabled"
                    value={enabled ? 'enabled' : 'paused'}
                    onChange={(event) => setEnabled(event.target.value === 'enabled')}
                    className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
                  >
                    <option value="enabled">Enabled</option>
                    <option value="paused">Paused</option>
                  </select>
                </div>
              </div>

              {formError && (
                <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{formError}</div>
              )}

              <div className="flex items-center justify-end gap-3">
                <Button type="button" variant="outline" onClick={() => navigate('/automation')}>
                  Cancel
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Creating…' : 'Create Rule'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
