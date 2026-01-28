import { formatMinerTypeLabel, getMinerTypeAvatarClasses, getMinerTypeBadgeClasses, getMinerTypeGlyph } from '@/lib/minerTypes'
import { cn } from '@/lib/utils'

interface BadgeProps {
  type?: string | null
  className?: string
  size?: 'sm' | 'md'
  variant?: 'full' | 'short'
}

export function MinerTypeBadge({ type, className, size = 'md', variant = 'full' }: BadgeProps) {
  return (
    <span
      className={cn(
        getMinerTypeBadgeClasses(type),
        size === 'sm' ? 'text-[10px] px-2 py-0.5' : 'text-[11px] px-2.5 py-0.5',
        className,
      )}
    >
      {formatMinerTypeLabel(type, { short: variant === 'short' })}
    </span>
  )
}

interface AvatarProps {
  type?: string | null
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

const sizeMap: Record<Required<AvatarProps>['size'], string> = {
  sm: 'h-7 w-7 text-[11px]',
  md: 'h-9 w-9 text-xs',
  lg: 'h-12 w-12 text-sm',
}

export function MinerTypeAvatar({ type, className, size = 'md' }: AvatarProps) {
  return (
    <div className={cn(getMinerTypeAvatarClasses(type), sizeMap[size], className)}>
      {getMinerTypeGlyph(type)}
    </div>
  )
}
