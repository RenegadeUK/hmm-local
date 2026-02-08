import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle, Loader2, Database, RefreshCcw, Activity, HardDrive, Zap, TrendingUp } from 'lucide-react';

interface DatabaseStatus {
  active: string;
  postgresql_configured: boolean;
  postgresql_config?: {
    host: string;
    port: number;
    database: string;
    username: string;
    password: string;
  };
}

interface DatabaseHealth {
  status: string;
  pool: {
    size: number;
    checked_out: number;
    overflow: number;
    total_capacity: number;
    max_size_configured?: number;
    max_overflow_configured?: number;
    max_capacity_configured?: number;
    utilization_percent: number;
  };
  database_type: string;
  postgresql?: {
    active_connections: number;
    database_size_mb: number;
    long_running_queries: number;
  };
  high_water_marks?: {
    last_24h_date: string;
    last_24h: {
      db_pool_in_use_peak: number;
      db_pool_wait_count: number;
      db_pool_wait_seconds_sum: number;
      active_queries_peak: number;
      slow_query_count: number;
    };
    since_boot: {
      db_pool_in_use_peak: number;
      db_pool_wait_count: number;
      db_pool_wait_seconds_sum: number;
      active_queries_peak: number;
      slow_query_count: number;
    };
  };
}

interface MigrationProgress {
  table: string;
  progress: number;
  message: string;
}

interface MigrationStatus {
  running: boolean;
  progress: MigrationProgress[];
  result: {
    success: boolean;
    message: string;
    tables_migrated: number;
    total_rows: number;
    errors: string[];
  } | null;
}

export default function DatabaseSettings() {
  const queryClient = useQueryClient();
  
  const [showMigrationModal, setShowMigrationModal] = useState(false);
  const [showValidation, setShowValidation] = useState(false);

  // Fetch current database status
  const { data: status, isLoading } = useQuery<DatabaseStatus>({
    queryKey: ['database-status'],
    queryFn: async () => {
      const response = await fetch('/api/settings/database/status');
      if (!response.ok) throw new Error('Failed to fetch status');
      return response.json();
    },
    refetchInterval: 5000
  });

  // Fetch database health metrics
  const { data: health } = useQuery<DatabaseHealth>({
    queryKey: ['database-health'],
    queryFn: async () => {
      const response = await fetch('/api/health/database');
      if (!response.ok) throw new Error('Failed to fetch health');
      return response.json();
    },
    refetchInterval: 5000,
    enabled: status?.active === 'postgresql' // Only fetch for PostgreSQL
  });

  // Start migration mutation
  const startMigrationMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch('/api/settings/database/migrate/start', {
        method: 'POST'
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
      }
      return response.json();
    },
    onSuccess: () => {
      setShowMigrationModal(true);
      // Start polling migration status
      const interval = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ['migration-status'] });
      }, 1000);
      
      // Store interval ID to clear later
      (window as any).migrationInterval = interval;
    },
    onError: (error: Error) => {
      alert(`Failed to start migration: ${error.message}`);
    }
  });

  // Fetch migration status
  const { data: migrationStatus } = useQuery<MigrationStatus>({
    queryKey: ['migration-status'],
    queryFn: async () => {
      const response = await fetch('/api/settings/database/migrate/status');
      if (!response.ok) throw new Error('Failed to fetch migration status');
      return response.json();
    },
    enabled: showMigrationModal,
    refetchInterval: showMigrationModal ? 1000 : false
  });

  // Stop polling when migration completes
  React.useEffect(() => {
    if (migrationStatus && !migrationStatus.running && migrationStatus.result) {
      if ((window as any).migrationInterval) {
        clearInterval((window as any).migrationInterval);
        (window as any).migrationInterval = null;
      }
      setShowValidation(true);
    }
  }, [migrationStatus]);

  // Validate migration mutation
  const validateMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch('/api/settings/database/migrate/validate', {
        method: 'POST'
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
      }
      return response.json();
    }
  });

  // Switch database mutation
  const switchMutation = useMutation({
    mutationFn: async ({ target, force }: { target: string; force?: boolean }) => {
      const forceParam = force ? '&force=true' : '';
      const response = await fetch(`/api/settings/database/switch?target=${target}${forceParam}`, {
        method: 'POST'
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
      }
      return response.json();
    },
    onSuccess: (data) => {
      if (data.restart_required) {
        if (confirm('Database switched! Container restart required. Restart now?')) {
          fetch('/api/settings/restart', { method: 'POST' });
        }
      } else {
        alert(data.message);
      }
      queryClient.invalidateQueries({ queryKey: ['database-status'] });
    },
    onError: (error: Error) => {
      alert(`Failed to switch: ${error.message}`);
    }
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center space-x-3">
        <Database className="h-6 w-6" />
        <h1 className="text-2xl font-bold">Database Configuration</h1>
      </div>

      {/* Health Monitoring Widgets - Only show for PostgreSQL */}
      {status?.active === 'postgresql' && health && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Connection Pool Status */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-400">Connection Pool</h3>
              <Activity className={`h-4 w-4 ${
                health.status === 'critical' ? 'text-red-400' :
                health.status === 'warning' ? 'text-yellow-400' :
                'text-green-400'
              }`} />
            </div>
            <div className="space-y-2">
              <div className="flex items-baseline space-x-2">
                <span className="text-2xl font-bold text-white">
                  {health.pool.utilization_percent}%
                </span>
                <span className="text-sm text-gray-400">utilized</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${
                    health.pool.utilization_percent > 90 ? 'bg-red-500' :
                    health.pool.utilization_percent > 80 ? 'bg-yellow-500' :
                    'bg-green-500'
                  }`}
                  style={{ width: `${health.pool.utilization_percent}%` }}
                />
              </div>
              <p className="text-xs text-gray-500">
                {health.pool.checked_out}/{health.pool.total_capacity} connections ({
                  health.pool.max_capacity_configured ?? health.pool.total_capacity
                } max)
              </p>
            </div>
          </div>

          {/* Active Connections */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-400">Active Queries</h3>
              <Zap className="h-4 w-4 text-blue-400" />
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-white">
                {health.postgresql?.active_connections || 0}
              </div>
              <p className="text-xs text-gray-500">running queries</p>
              {health.postgresql && health.postgresql.long_running_queries > 0 && (
                <p className="text-xs text-yellow-400 flex items-center space-x-1">
                  <AlertCircle className="h-3 w-3" />
                  <span>{health.postgresql.long_running_queries} slow ({'>'}1min)</span>
                </p>
              )}
            </div>
          </div>

          {/* Database Size */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-400">Database Size</h3>
              <HardDrive className="h-4 w-4 text-purple-400" />
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-white">
                {health.postgresql?.database_size_mb.toFixed(1) || '0'} MB
              </div>
              <p className="text-xs text-gray-500">total storage</p>
            </div>
          </div>

          {/* Status Indicator */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-400">Health Status</h3>
              <TrendingUp className={`h-4 w-4 ${
                health.status === 'healthy' ? 'text-green-400' :
                health.status === 'warning' ? 'text-yellow-400' :
                'text-red-400'
              }`} />
            </div>
            <div className="space-y-1">
              <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                health.status === 'healthy' ? 'bg-green-900/30 text-green-400 border border-green-700' :
                health.status === 'warning' ? 'bg-yellow-900/30 text-yellow-400 border border-yellow-700' :
                'bg-red-900/30 text-red-400 border border-red-700'
              }`}>
                {health.status.toUpperCase()}
              </div>
              <p className="text-xs text-gray-500 mt-2">
                {health.status === 'healthy' && 'All systems operational'}
                {health.status === 'warning' && 'Pool usage high'}
                {health.status === 'critical' && 'Pool nearly exhausted'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* High-water Marks */}
      {status?.active === 'postgresql' && health?.high_water_marks && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <h3 className="text-sm font-medium text-gray-400 mb-2">High-water marks (last 24h)</h3>
            <div className="text-xs text-gray-500 mb-3">Since {health.high_water_marks.last_24h_date}</div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-gray-400">Pool in-use peak</div>
                <div className="text-white font-semibold">{health.high_water_marks.last_24h.db_pool_in_use_peak}</div>
              </div>
              <div>
                <div className="text-gray-400">Active queries peak</div>
                <div className="text-white font-semibold">{health.high_water_marks.last_24h.active_queries_peak}</div>
              </div>
              <div>
                <div className="text-gray-400">Wait count</div>
                <div className="text-white font-semibold">{health.high_water_marks.last_24h.db_pool_wait_count}</div>
              </div>
              <div>
                <div className="text-gray-400">Wait seconds</div>
                <div className="text-white font-semibold">{health.high_water_marks.last_24h.db_pool_wait_seconds_sum.toFixed(1)}s</div>
              </div>
              <div>
                <div className="text-gray-400">Slow queries</div>
                <div className="text-white font-semibold">{health.high_water_marks.last_24h.slow_query_count}</div>
              </div>
            </div>
          </div>

          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <h3 className="text-sm font-medium text-gray-400 mb-2">High-water marks (since boot)</h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-gray-400">Pool in-use peak</div>
                <div className="text-white font-semibold">{health.high_water_marks.since_boot.db_pool_in_use_peak}</div>
              </div>
              <div>
                <div className="text-gray-400">Active queries peak</div>
                <div className="text-white font-semibold">{health.high_water_marks.since_boot.active_queries_peak}</div>
              </div>
              <div>
                <div className="text-gray-400">Wait count</div>
                <div className="text-white font-semibold">{health.high_water_marks.since_boot.db_pool_wait_count}</div>
              </div>
              <div>
                <div className="text-gray-400">Wait seconds</div>
                <div className="text-white font-semibold">{health.high_water_marks.since_boot.db_pool_wait_seconds_sum.toFixed(1)}s</div>
              </div>
              <div>
                <div className="text-gray-400">Slow queries</div>
                <div className="text-white font-semibold">{health.high_water_marks.since_boot.slow_query_count}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Current Status */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Current Database</h2>
        <div className="flex items-center space-x-3">
          <div className="px-4 py-2 rounded-lg font-mono text-lg bg-green-900/30 text-green-400 border border-green-700">
            POSTGRESQL
          </div>
          <p className="text-gray-400 text-sm">
            Embedded PostgreSQL running at localhost:5432
          </p>
        </div>
      </div>

      {/* Migration Section */}
      {status?.postgresql_configured && status.active === 'sqlite' && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Migrate to PostgreSQL</h2>
          <p className="text-gray-400 mb-4">
            This will copy all data from SQLite to PostgreSQL. Your SQLite database will remain as a backup.
            The process may take 10-15 minutes depending on data size.
          </p>
          
          <button
            onClick={() => startMigrationMutation.mutate()}
            disabled={startMigrationMutation.isPending}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-md font-medium flex items-center space-x-2"
          >
            {startMigrationMutation.isPending ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> <span>Starting...</span></>
            ) : (
              <><RefreshCcw className="h-4 w-4" /> <span>Start Migration</span></>
            )}
          </button>
        </div>
      )}

      {status?.postgresql_configured && status.active === 'sqlite' && (
        <div className="bg-yellow-900/20 rounded-lg p-6 border border-yellow-700">
          <h2 className="text-lg font-semibold mb-2 text-yellow-300">Force switch to PostgreSQL</h2>
          <p className="text-gray-300 mb-4 text-sm">
            Use this only if you accept the risk of incomplete data. This bypasses migration validation.
          </p>
          <button
            onClick={() => {
              if (confirm('Force switch to PostgreSQL without successful migration? This may cause missing data.')) {
                switchMutation.mutate({ target: 'postgresql', force: true });
              }
            }}
            disabled={switchMutation.isPending}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-md font-medium flex items-center space-x-2"
          >
            {switchMutation.isPending ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> <span>Switching...</span></>
            ) : (
              <><Database className="h-4 w-4" /> <span>Force switch to PostgreSQL</span></>
            )}
          </button>
        </div>
      )}

      {/* Migration Modal */}
      {showMigrationModal && migrationStatus && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto border border-gray-700">
            <h2 className="text-xl font-bold mb-4">Migration Progress</h2>
            
            {/* Progress List */}
            <div className="space-y-2 mb-4 max-h-96 overflow-y-auto">
              {migrationStatus.progress.map((item, idx) => (
                <div key={idx} className="flex items-center space-x-3 text-sm">
                  {item.progress === 100 ? (
                    <CheckCircle className="h-4 w-4 text-green-400 flex-shrink-0" />
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin text-blue-400 flex-shrink-0" />
                  )}
                  <span className="text-gray-300">{item.message}</span>
                </div>
              ))}
            </div>

            {/* Result */}
            {migrationStatus.result && (
              <div className={`p-4 rounded-md border mb-4 ${
                migrationStatus.result.success
                  ? 'bg-green-900/30 border-green-700'
                  : 'bg-red-900/30 border-red-700'
              }`}>
                <p className="font-medium">{migrationStatus.result.message}</p>
                {migrationStatus.result.errors.length > 0 && (
                  <ul className="mt-2 text-sm space-y-1">
                    {migrationStatus.result.errors.map((error, idx) => (
                      <li key={idx} className="text-red-400">• {error}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* Validation */}
            {showValidation && migrationStatus.result?.success && (
              <div className="mb-4">
                <button
                  onClick={() => validateMutation.mutate()}
                  disabled={validateMutation.isPending}
                  className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-md font-medium flex items-center justify-center space-x-2"
                >
                  {validateMutation.isPending ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> <span>Validating...</span></>
                  ) : (
                    <><CheckCircle className="h-4 w-4" /> <span>Validate Migration</span></>
                  )}
                </button>

                {validateMutation.data && (
                  <div className={`mt-3 p-3 rounded-md border ${
                    validateMutation.data.success
                      ? 'bg-green-900/30 border-green-700 text-green-400'
                      : 'bg-red-900/30 border-red-700 text-red-400'
                  }`}>
                    <p>{validateMutation.data.message}</p>
                    {validateMutation.data.mismatches?.length > 0 && (
                      <ul className="mt-2 text-sm">
                        {validateMutation.data.mismatches.map((m: any, idx: number) => (
                          <li key={idx}>
                            {m.table}: SQLite={m.sqlite_rows}, PostgreSQL={m.postgresql_rows}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Switch Button */}
            {migrationStatus.result?.success && validateMutation.data?.success && (
              <button
                onClick={() => {
                  setShowMigrationModal(false);
                  switchMutation.mutate({ target: 'postgresql' });
                }}
                disabled={switchMutation.isPending}
                className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 rounded-md font-medium flex items-center justify-center space-x-2"
              >
                {switchMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> <span>Switching...</span></>
                ) : (
                  <><Database className="h-4 w-4" /> <span>Switch to PostgreSQL</span></>
                )}
              </button>
            )}

            {/* Close Button */}
            {!migrationStatus.running && (
              <button
                onClick={() => setShowMigrationModal(false)}
                className="w-full mt-3 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-md font-medium"
              >
                Close
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
