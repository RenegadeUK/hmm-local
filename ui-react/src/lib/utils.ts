import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

type HashrateObject = {
  display?: string
  value?: number
  unit?: string
}

type HashrateInput = number | string | null | undefined | HashrateObject

const UNIT_FACTORS_TO_HS: Record<string, number> = {
  'H/S': 1,
  'KH/S': 1e3,
  'MH/S': 1e6,
  'GH/S': 1e9,
  'TH/S': 1e12,
  'PH/S': 1e15,
}

function normalizeHashrateUnit(unit?: string | null): string {
  if (!unit) return 'GH/s'

  const compact = unit.replace(/\s+/g, '').toUpperCase()
  const normalized = compact.endsWith('/S') ? compact : `${compact}/S`

  if (UNIT_FACTORS_TO_HS[normalized]) {
    return normalized.replace('/S', '/s')
  }

  return unit
}

function toHashrateHs(value: number, unit: string): number {
  const normalized = normalizeHashrateUnit(unit).toUpperCase()
  const factor = UNIT_FACTORS_TO_HS[normalized]
  if (!factor) {
    return value * UNIT_FACTORS_TO_HS['GH/S']
  }
  return value * factor
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatHashrate(value: number | null | undefined, unit: string = 'GH/s'): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value <= 0) {
    return `0.00 ${normalizeHashrateUnit(unit)}`
  }

  const normalizedUnit = normalizeHashrateUnit(unit)
  const hs = toHashrateHs(value, normalizedUnit)

  if (hs >= 1e15) return `${(hs / 1e15).toFixed(2)} PH/s`
  if (hs >= 1e12) return `${(hs / 1e12).toFixed(2)} TH/s`
  if (hs >= 1e9) return `${(hs / 1e9).toFixed(2)} GH/s`
  if (hs >= 1e6) return `${(hs / 1e6).toFixed(2)} MH/s`
  if (hs >= 1e3) return `${(hs / 1e3).toFixed(2)} KH/s`
  return `${hs.toFixed(2)} H/s`
}

export function formatHashrateDisplay(hashrate: HashrateInput, unit: string = 'GH/s'): string {
  if (hashrate === null || hashrate === undefined) {
    return formatHashrate(0, unit)
  }

  if (typeof hashrate === 'string') {
    return hashrate.trim() || formatHashrate(0, unit)
  }

  if (typeof hashrate === 'number') {
    return formatHashrate(hashrate, unit)
  }

  if (hashrate.display && hashrate.display.trim().length > 0) {
    return hashrate.display
  }

  if (typeof hashrate.value === 'number') {
    return formatHashrate(hashrate.value, hashrate.unit || unit)
  }

  return formatHashrate(0, unit)
}
