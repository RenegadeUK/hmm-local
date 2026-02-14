import type { Pool } from './telemetry'

export interface PoolHealthStatus {
  pool_id: number
  pool_name: string
  pool_url: string
  active_miners: number
  is_reachable: boolean | null
  response_time_ms: number | null
  reject_rate: number | null
  health_score: number | null
  last_checked: string | null
  error_message?: string | null
}

export interface PoolHealthOverview {
  total_pools: number
  healthy_pools: number
  unhealthy_pools: number
  avg_response_time_ms: number | null
  avg_reject_rate: number | null
  pools: PoolHealthStatus[]
}

export interface PoolFormValues extends Omit<Pool, 'id'> {
  id?: number
}

export interface PoolPreset {
  key: string
  name: string
  url: string
  port: number
  group: string
  subtitle?: string
}
