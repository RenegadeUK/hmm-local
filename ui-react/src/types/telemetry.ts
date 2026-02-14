export interface MinerTelemetry {
  timestamp: string;
  hashrate: number | { display: string; value: number; unit: string };
  hashrate_unit: string;
  temperature: number;
  power_watts: number;
  shares_accepted: number;
  shares_rejected: number;
  pool_in_use: string;
  extra_data: {
    raw_source?: string;
    uptime_seconds?: number;
    firmware_version?: string;
    frequency_mhz?: number;
    voltage_mv?: number;
    best_share_diff?: number;
    pool_response_ms?: number;
    error_rate_pct?: number;
    free_heap_bytes?: number;
    core_voltage_mv?: number;
    core_voltage_actual_mv?: number;
    fan_speed_pct?: number;
    vr_temp_c?: number;
    frequency?: number;
    voltage?: number;
    uptime?: number;
    asic_model?: string;
    version?: string;
    current_mode?: string;
    best_diff?: number;
    best_session_diff?: number;
    free_heap?: number;
    core_voltage?: number;
    core_voltage_actual?: number;
    wifi_rssi?: string;
    fan_speed?: number;
    fan_rpm?: number;
    vr_temp?: number;
    rssi?: string;
    small_core_count?: number;
    difficulty?: number;
    network_difficulty?: number;
    stratum_suggested_difficulty?: number;
    response_time?: number;
    error_percentage?: number;
    block_height?: number;
    // Avalon specific
    diff_accepted?: number;
    diff_rejected?: number;
    pool_difficulty?: number;
    last_share_diff?: number;
    work_difficulty?: number;
    stale_shares?: number;
    pool_reject_pct?: number;
    pool_stale_pct?: number;
    device_hw_pct?: number;
    device_reject_pct?: number;
    get_failures?: number;
    hw_errors?: number;
    hardware_errors?: number;
    utility?: number;
    found_blocks?: number;
    vendor?: Record<string, unknown>;
  };
}

export interface MinerModes {
  modes: string[];
}

export interface Pool {
  id: number;
  name: string;
  url: string;
  port: number;
  user: string;
  password: string;
  enabled: boolean;
  show_on_dashboard: boolean;
}

export interface DevicePool {
  slot: number;
  url: string;
  user: string;
  password: string;
}
