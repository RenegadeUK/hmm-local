import { cn } from '@/lib/utils'

export type KnownMinerType = 'avalon_nano' | 'bitaxe' | 'nerdqaxe' | 'nmminer'

interface MinerTypeColors {
  badgeBg: string
  badgeText: string
  badgeBorder: string
  avatarBg: string
  avatarText: string
}

export interface MinerTypeMeta {
  key: string
  label: string
  shortLabel: string
  glyph: string
  colors: MinerTypeColors
}

const humanize = (value: string) =>
  value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')

const MINER_TYPE_META: Record<KnownMinerType, MinerTypeMeta> = {
  avalon_nano: {
    key: 'avalon_nano',
    label: 'Avalon Nano',
    shortLabel: 'Avalon',
    glyph: 'AN',
    colors: {
      badgeBg: 'bg-amber-500/20',
      badgeText: 'text-amber-100',
      badgeBorder: 'border-amber-300/40',
      avatarBg: 'bg-gradient-to-br from-amber-500/40 via-amber-500/20 to-yellow-500/20',
      avatarText: 'text-amber-50',
    },
  },
  bitaxe: {
    key: 'bitaxe',
    label: 'Bitaxe',
    shortLabel: 'Bitaxe',
    glyph: 'BX',
    colors: {
      badgeBg: 'bg-sky-500/20',
      badgeText: 'text-sky-100',
      badgeBorder: 'border-sky-300/40',
      avatarBg: 'bg-gradient-to-br from-sky-500/40 via-sky-500/20 to-cyan-400/20',
      avatarText: 'text-sky-50',
    },
  },
  nerdqaxe: {
    key: 'nerdqaxe',
    label: 'Nerdqaxe',
    shortLabel: 'Nerd',
    glyph: 'NQ',
    colors: {
      badgeBg: 'bg-fuchsia-500/20',
      badgeText: 'text-fuchsia-100',
      badgeBorder: 'border-fuchsia-300/40',
      avatarBg: 'bg-gradient-to-br from-fuchsia-500/40 via-fuchsia-500/20 to-violet-500/20',
      avatarText: 'text-fuchsia-50',
    },
  },
  nmminer: {
    key: 'nmminer',
    label: 'NMMiner',
    shortLabel: 'NMMiner',
    glyph: 'NM',
    colors: {
      badgeBg: 'bg-orange-500/20',
      badgeText: 'text-orange-100',
      badgeBorder: 'border-orange-300/40',
      avatarBg: 'bg-gradient-to-br from-orange-500/40 via-orange-500/20 to-amber-400/20',
      avatarText: 'text-orange-50',
    },
  },
}

const DEFAULT_META: MinerTypeMeta = {
  key: 'unknown',
  label: 'Unknown Miner',
  shortLabel: 'Unknown',
  glyph: '??',
  colors: {
    badgeBg: 'bg-slate-500/20',
    badgeText: 'text-slate-200',
    badgeBorder: 'border-slate-400/30',
    avatarBg: 'bg-slate-700/60',
    avatarText: 'text-slate-100',
  },
}

const normalizeType = (type?: string | null) => type?.toLowerCase().trim() ?? ''

export function getMinerTypeMeta(type?: string | null): MinerTypeMeta {
  const normalized = normalizeType(type)
  if (normalized && normalized in MINER_TYPE_META) {
    return MINER_TYPE_META[normalized as KnownMinerType]
  }

  if (normalized) {
    return {
      ...DEFAULT_META,
      key: normalized,
      label: humanize(normalized),
      shortLabel: humanize(normalized),
      glyph: normalized.substring(0, 2).toUpperCase(),
    }
  }

  return DEFAULT_META
}

export function getMinerTypeBadgeClasses(type?: string | null, extra?: string) {
  const meta = getMinerTypeMeta(type)
  return cn(
    'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold tracking-wide uppercase',
    meta.colors.badgeBg,
    meta.colors.badgeText,
    meta.colors.badgeBorder,
    extra,
  )
}

export function getMinerTypeAvatarClasses(type?: string | null, extra?: string) {
  const meta = getMinerTypeMeta(type)
  return cn(
    'flex items-center justify-center rounded-full font-bold uppercase border border-white/5',
    meta.colors.avatarBg,
    meta.colors.avatarText,
    extra,
  )
}

export function formatMinerTypeLabel(type?: string | null, { short = false } = {}) {
  const meta = getMinerTypeMeta(type)
  return short ? meta.shortLabel : meta.label
}

export function getMinerTypeGlyph(type?: string | null) {
  return getMinerTypeMeta(type).glyph
}
