export interface Miner {
  id: number;
  name: string;
  miner_type: string;
  enabled: boolean;
  is_offline: boolean;
  hashrate: number;
  hashrate_unit: string;
  power: number;
  pool: string;
  cost_24h: number;
  current_mode: string | null;
  best_diff: number;
  firmware_version: string | null;
  health_score: number | null;
  ip_address?: string;
  manual_power_watts?: number;
}

export interface MinersResponse {
  miners: Miner[];
  stats: {
    online_miners: number;
    total_hashrate: number;
    total_power: number;
    total_cost_24h: number;
    current_price: number;
  };
  events?: unknown[];
  energy_prices?: unknown[];
}

export type ViewMode = 'tiles' | 'table';

export interface BulkOperation {
  type: 'enable' | 'disable' | 'restart' | 'set-mode' | 'switch-pool';
  minerIds: number[];
  payload?: {
    mode?: string;
    pool_id?: number;
  };
}
