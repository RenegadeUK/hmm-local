const API_BASE = '/api'

export class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message)
    this.name = 'APIError'
  }
}

async function fetchAPI<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${endpoint}`
  
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as unknown
    let errorMessage = `HTTP ${response.status}`
    if (
      typeof errorData === 'object' &&
      errorData !== null &&
      'message' in errorData &&
      typeof (errorData as { message?: unknown }).message === 'string'
    ) {
      errorMessage = (errorData as { message: string }).message
    }

    throw new APIError(errorMessage, response.status, errorData)
  }

  return (await response.json()) as T
}

// Miners
export interface Miner {
  id: string
  name: string
  type: string
  ip_address: string
  status: string
  hashrate: number
  temperature: number
  power: number
  uptime: number
  pool_address: string
}

export type MinerStatsResponse = Record<string, unknown>

export interface CreateMinerPayload {
  name: string
  miner_type: string
  ip_address: string
  port: number | null
  config?: Record<string, unknown>
}

export const minersAPI = {
  getAll: () => fetchAPI<Miner[]>('/miners'),
  getById: (id: string) => fetchAPI<Miner>(`/miners/${id}`),
  getStats: (id: string) => fetchAPI<MinerStatsResponse>(`/miners/${id}/stats`),
  create: (payload: CreateMinerPayload) =>
    fetchAPI<Miner>('/miners', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

// Dashboard
export interface SystemEvent {
  id: number
  timestamp: string
  event_type: string
  source: string
  message: string
  data?: Record<string, unknown> | null
}

export interface RecentEventsResponse {
  events: SystemEvent[]
}

export interface DashboardData {
  stats: {
    online_miners: number
    total_hashrate_ghs: number
    total_pool_hashrate_ghs: number
    pool_efficiency_percent: number
    total_power_watts: number
    avg_efficiency_wth: number
    total_cost_24h_pounds: number
    avg_price_per_kwh_pence: number
    current_energy_price_pence: number
    best_share_24h: {
      difficulty: number
      coin: string
      network_difficulty: number
      percentage: number
      timestamp: string
      time_ago_seconds: number
    }
  }
  miners: Record<string, unknown>[]
  events: SystemEvent[]
  pools: Record<string, unknown>[]
}

export const dashboardAPI = {
  getData: () => fetchAPI<DashboardData>('/dashboard'),
  getAll: (dashboardType: string = 'asic') => 
    fetchAPI<DashboardData>(`/dashboard/all?dashboard_type=${dashboardType}`),
  getEvents: (limit: number = 1000) =>
    fetchAPI<RecentEventsResponse>(`/dashboard/events/recent?limit=${limit}`),
  clearEvents: () =>
    fetchAPI<{ message: string }>(`/dashboard/events`, {
      method: 'DELETE',
    }),
}

// Analytics
export type AnalyticsEfficiencyResponse = Record<string, unknown>
export type AnalyticsPerformanceResponse = Record<string, unknown>

export const analyticsAPI = {
  getEfficiency: (timeRange: string) => 
    fetchAPI<AnalyticsEfficiencyResponse>(`/analytics/efficiency?range=${timeRange}`),
  getPerformance: (minerId: string, timeRange: string) =>
    fetchAPI<AnalyticsPerformanceResponse>(`/analytics/miner/${minerId}?range=${timeRange}`),
}

// Pools
export interface SolopoolMinerStats {
  workers?: number
  hashrate?: string
  hashrate_raw?: number
  current_luck?: number | null
  ettb?: { formatted?: string }
  lastBlockTimestamp?: number
  blocks_24h?: number
  blocks_7d?: number
  blocks_30d?: number
  shares?: number
  lastShare?: number
  paid?: number
  hashrate_30m?: number
}

export interface SolopoolMiner {
  username: string
  stats?: SolopoolMinerStats
  is_strategy_pool?: boolean
  is_active_target?: boolean
}

export interface SolopoolStats {
  enabled?: boolean
  strategy_enabled?: boolean
  dgb_miners?: SolopoolMiner[]
  bch_miners?: SolopoolMiner[]
  bc2_miners?: SolopoolMiner[]
  btc_miners?: SolopoolMiner[]
}

export interface BraiinsStatsSummary {
  workers_online?: number
  hashrate_5m?: number | null
  hashrate_raw?: number
  current_balance?: number
  today_reward?: number
  all_time_reward?: number
}

export interface BraiinsStatsResponse {
  enabled?: boolean
  username?: string
  show_always?: boolean
  is_strategy_active?: boolean
  stats?: BraiinsStatsSummary
}

export const poolsAPI = {
  getSolopoolStats: () => fetchAPI<SolopoolStats>('/settings/solopool/stats'),
  getBraiinsStats: () => fetchAPI<BraiinsStatsResponse>('/settings/braiins/stats'),
}

// Health
export interface MinerHealth {
  miner_id: string
  miner_name: string
  score: number
  status: string
  reasons: string[]
  uptime_hours: number
  avg_temp: number
  reject_rate: number
}

export const healthAPI = {
  getFleetHealth: () => fetchAPI<MinerHealth[]>('/health/fleet'),
  getMinerHealth: (id: string) => fetchAPI<Record<string, unknown>>(`/health/miner/${id}`),
}

// Cloud settings
export interface CloudConfigResponse {
  enabled: boolean
  api_key: string | null
  endpoint: string
  installation_name: string
  installation_location?: string | null
  push_interval_minutes: number
}

export interface UpdateCloudConfigPayload {
  enabled: boolean
  api_key: string | null
  endpoint: string
  installation_name: string
  installation_location?: string | null
  push_interval_minutes: number
}

export interface CloudTestResponse {
  success: boolean
  message?: string
  endpoint?: string
}

export interface CloudActionResponse {
  status: string
  message?: string
}

export const cloudAPI = {
  getConfig: () => fetchAPI<CloudConfigResponse>('/cloud/config'),
  updateConfig: (payload: UpdateCloudConfigPayload) =>
    fetchAPI<CloudActionResponse>('/cloud/config', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  testConnection: () =>
    fetchAPI<CloudTestResponse>('/cloud/test', {
      method: 'POST',
    }),
  manualPush: () =>
    fetchAPI<CloudActionResponse>('/cloud/push/manual', {
      method: 'POST',
    }),
}

// Network discovery
export interface NetworkRange {
  cidr: string
  name?: string | null
}

export interface DiscoveryConfigResponse {
  enabled: boolean
  auto_add: boolean
  networks: NetworkRange[]
  scan_interval_hours: number
}

export interface UpdateDiscoveryConfigPayload extends DiscoveryConfigResponse {}

export interface DiscoveredMiner {
  ip: string
  port: number
  type: string
  name: string
  details: Record<string, unknown>
  already_added: boolean
}

export interface DiscoveryScanResponse {
  total_found: number
  new_miners: number
  existing_miners: number
  miners: DiscoveredMiner[]
}

export interface AutoScanResponse {
  total_found: number
  total_added: number
  auto_add_enabled: boolean
  networks_scanned: number
}

export interface NetworkInfoResponse {
  network_cidr: string
  description: string
}

export interface ManualScanPayload {
  network_cidr?: string | null
  timeout?: number
}

export const discoveryAPI = {
  getConfig: () => fetchAPI<DiscoveryConfigResponse>('/discovery/config'),
  updateConfig: (payload: UpdateDiscoveryConfigPayload) =>
    fetchAPI<{ message: string }>('/discovery/config', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getNetworkInfo: () => fetchAPI<NetworkInfoResponse>('/discovery/network-info'),
  scanNetwork: (payload: ManualScanPayload) =>
    fetchAPI<DiscoveryScanResponse>('/discovery/scan', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  triggerAutoScan: () =>
    fetchAPI<AutoScanResponse>('/discovery/auto-scan', {
      method: 'POST',
    }),
}

// Tuning profiles
export interface TuningProfile {
  id: number
  name: string
  miner_type: string
  description: string | null
  settings: Record<string, string | number>
  is_system: boolean
  created_at: string
}

export interface CreateTuningProfilePayload {
  name: string
  miner_type: string
  description?: string | null
  settings: Record<string, string | number>
}

export interface ApplyProfileResponse {
  message: string
}

export const tuningAPI = {
  getProfiles: (minerType?: string) =>
    fetchAPI<TuningProfile[]>(minerType ? `/tuning/profiles?miner_type=${minerType}` : '/tuning/profiles'),
  createProfile: (payload: CreateTuningProfilePayload) =>
    fetchAPI<TuningProfile>('/tuning/profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteProfile: (profileId: number) =>
    fetchAPI<{ message: string }>(`/tuning/profiles/${profileId}`, {
      method: 'DELETE',
    }),
  applyProfile: (profileId: number, minerId: number) =>
    fetchAPI<ApplyProfileResponse>(`/tuning/profiles/${profileId}/apply/${minerId}`, {
      method: 'POST',
    }),
}

// Notifications
export type NotificationChannelType = 'telegram' | 'discord'

export interface NotificationChannel {
  id: number
  channel_type: NotificationChannelType
  enabled: boolean
  config: Record<string, unknown>
}

export interface NotificationChannelCreatePayload {
  channel_type: NotificationChannelType
  enabled: boolean
  config: Record<string, unknown>
}

export interface NotificationChannelUpdatePayload {
  enabled?: boolean
  config?: Record<string, unknown>
}

export interface AlertConfigItem {
  id: number
  alert_type: string
  enabled: boolean
  config?: Record<string, unknown> | null
}

export interface AlertConfigCreatePayload {
  alert_type: string
  enabled: boolean
  config?: Record<string, unknown> | null
}

export interface AlertConfigUpdatePayload extends NotificationChannelUpdatePayload {}

export interface NotificationLogEntry {
  id: number
  timestamp: string
  channel_type: NotificationChannelType
  alert_type: string
  message: string
  success: boolean
  error?: string | null
}

export interface NotificationTestResponse {
  status: string
  message?: string
}

export const notificationsAPI = {
  getChannels: () => fetchAPI<NotificationChannel[]>('/notifications/channels'),
  getChannel: (channelType: NotificationChannelType) =>
    fetchAPI<NotificationChannel>(`/notifications/channels/${channelType}`),
  upsertChannel: (payload: NotificationChannelCreatePayload) =>
    fetchAPI<NotificationChannel>('/notifications/channels', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateChannel: (
    channelType: NotificationChannelType,
    payload: NotificationChannelUpdatePayload
  ) =>
    fetchAPI<NotificationChannel>(`/notifications/channels/${channelType}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteChannel: (channelType: NotificationChannelType) =>
    fetchAPI<{ status: string }>(`/notifications/channels/${channelType}`, {
      method: 'DELETE',
    }),
  testChannel: (channelType: NotificationChannelType) =>
    fetchAPI<NotificationTestResponse>(`/notifications/test/${channelType}`, {
      method: 'POST',
    }),
  getAlerts: () => fetchAPI<AlertConfigItem[]>('/notifications/alerts'),
  upsertAlert: (payload: AlertConfigCreatePayload) =>
    fetchAPI<AlertConfigItem>('/notifications/alerts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateAlert: (alertType: string, payload: AlertConfigUpdatePayload) =>
    fetchAPI<AlertConfigItem>(`/notifications/alerts/${alertType}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getLogs: (limit: number = 100) =>
    fetchAPI<NotificationLogEntry[]>(`/notifications/logs?limit=${limit}`),
}
