const REASON_LABELS: Record<string, string> = {
  HASHRATE_DROP: 'Hashrate drop',
  EFFICIENCY_DRIFT: 'Efficiency drift',
  TEMP_HIGH: 'High temperature',
  REJECT_RATE_SPIKE: 'Reject rate spike',
  POWER_SPIKE: 'Power spike',
  SENSOR_MISSING: 'Telemetry missing',
  INSUFFICIENT_DATA: 'Insufficient baseline data',
}

const METRIC_LABELS: Record<string, string> = {
  hashrate_th: 'Hashrate (TH/s)',
  w_per_th: 'Efficiency (W/TH)',
  temp_c: 'Temperature (°C)',
  reject_rate: 'Reject rate (%)',
  power_w: 'Power (W)',
  telemetry: 'Telemetry',
  baseline_samples: 'Baseline samples',
}

const ACTION_LABELS: Record<string, string> = {
  RESTART_MINER: 'Restart miner',
  DROP_MODE: 'Lower power mode',
  SWITCH_POOL: 'Switch mining pool',
  CHECK_NETWORK: 'Check network connectivity',
  CHECK_COOLING: 'Inspect cooling and airflow',
  CHECK_PSU: 'Check power supply',
  WAIT_FOR_BASELINE: 'Wait for more baseline data',
}

const UPPERCASE_WORDS = new Set(['API', 'ASIC', 'BTC', 'BCH', 'DGB', 'BC2', 'CPU', 'GPU', 'HA'])

export function humanizeKey(value: string | null | undefined): string {
  if (!value) return ''

  const raw = String(value).trim()
  if (!raw) return ''

  const spaced = raw
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_.-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  return spaced
    .split(' ')
    .map((word) => {
      if (!word) return word
      const upper = word.toUpperCase()
      if (UPPERCASE_WORDS.has(upper)) return upper
      if (/^[A-Z0-9]+$/.test(word) && word.length <= 3) return upper
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
    })
    .join(' ')
}

export function formatReasonCode(code: string | null | undefined): string {
  if (!code) return ''
  const key = code.toUpperCase()
  return REASON_LABELS[key] || humanizeKey(code)
}

export function formatMetricLabel(metric: string | null | undefined): string {
  if (!metric) return ''
  return METRIC_LABELS[metric] || humanizeKey(metric)
}

export function formatSuggestedAction(action: string | null | undefined): string {
  if (!action) return ''
  const key = action.toUpperCase()
  return ACTION_LABELS[key] || humanizeKey(action)
}
