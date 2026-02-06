import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { useNavigate } from "react-router-dom";
import { MinerTypeBadge } from '@/components/miners/MinerTypeBadge';
import { formatMetricLabel, formatReasonCode, humanizeKey } from '@/lib/textFormatters';

interface MinerHealthData {
  miner_id: number;
  miner_name: string;
  miner_type: string;
  timestamp: string;
  health_score: number;
  reasons: Array<string | {
    code?: string;
    severity?: string;
    metric?: string;
    actual?: number | string;
    expected_min?: number;
    expected_max?: number;
    unit?: string;
  }>;
  anomaly_score: number;
  current_mode: string;
  has_issues: boolean;
}

interface FleetHealthResponse {
  total_miners: number;
  monitored_miners: number;
  miners: MinerHealthData[];
}

export function Health() {
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery<FleetHealthResponse>({
    queryKey: ["health", "all"],
    queryFn: async () => {
      const response = await fetch("/api/health/all");
      if (!response.ok) throw new Error("Failed to fetch health data");
      return response.json();
    },
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Fleet Health</h1>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted-foreground">Loading health data...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Fleet Health</h1>
        <div className="flex items-center justify-center h-64">
          <div className="text-destructive">
            Error loading health data: {error.message}
          </div>
        </div>
      </div>
    );
  }

  const getHealthColor = (score: number) => {
    if (score >= 80) return "text-green-500";
    if (score >= 60) return "text-yellow-500";
    if (score >= 40) return "text-orange-500";
    return "text-red-500";
  };

  const getHealthBg = (score: number) => {
    if (score >= 80) return "bg-green-500/10 border-green-500/20";
    if (score >= 60) return "bg-yellow-500/10 border-yellow-500/20";
    if (score >= 40) return "bg-orange-500/10 border-orange-500/20";
    return "bg-red-500/10 border-red-500/20";
  };

  const getHealthStatus = (score: number) => {
    if (score >= 80) return "Excellent";
    if (score >= 60) return "Good";
    if (score >= 40) return "Fair";
    return "Poor";
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  const formatNumberValue = (value: number) => {
    if (Math.abs(value) >= 100) return value.toFixed(0);
    if (Math.abs(value) >= 10) return value.toFixed(1);
    return value.toFixed(2).replace(/\.00$/, '');
  };

  const insertNumberSpacing = (text: string) => text.replace(/(\d)([A-Za-z])/g, '$1 $2');

  const formatValueWithUnit = (value: number | string | undefined, unit?: string) => {
    if (value === undefined || value === null) return '';
    if (typeof value === 'number') {
      const formatted = formatNumberValue(value);
      return unit ? `${formatted} ${unit}` : formatted;
    }
    const cleaned = insertNumberSpacing(value);
    return unit ? `${cleaned} ${unit}`.trim() : cleaned;
  };

  const formatExpectedRange = (min?: number, max?: number, unit?: string) => {
    if (min !== undefined && max !== undefined) {
      const range = `${formatNumberValue(min)}–${formatNumberValue(max)}`;
      return unit ? `${range} ${unit}` : range;
    }
    if (min !== undefined) {
      const target = `${formatNumberValue(min)}`;
      return unit ? `≥ ${target} ${unit}` : `≥ ${target}`;
    }
    if (max !== undefined) {
      const target = `${formatNumberValue(max)}`;
      return unit ? `≤ ${target} ${unit}` : `≤ ${target}`;
    }
    return '';
  };

  type ReasonEntry = string | {
    code?: string;
    severity?: string;
    metric?: string;
    actual?: number | string;
    expected_min?: number;
    expected_max?: number;
    unit?: string;
  };

  const formatReasonText = (reason: ReasonEntry) => {
    if (typeof reason === 'string') {
      return humanizeKey(reason);
    }

    const code = reason.code || '';
    if (code === 'INSUFFICIENT_DATA') {
      const expected = reason.expected_min || 60;
      return `Collecting baseline — ${reason.actual || 0}/${expected} samples`;
    }

    const label = formatReasonCode(code || '');
    const metricLabel = reason.metric ? formatMetricLabel(reason.metric) : '';
    const actualText = formatValueWithUnit(reason.actual, reason.unit) || (code === 'SENSOR_MISSING' ? 'No samples' : '');
    const expectedText = formatExpectedRange(reason.expected_min, reason.expected_max, reason.unit);

    const prefix = metricLabel ? `${label} — ${metricLabel}` : label;
    const body = actualText ? ` ${actualText}` : '';
    const suffix = expectedText ? ` (target ${expectedText})` : '';

    return `${prefix}${body}${suffix}`.trim();
  };

  const sortedMiners = [...(data?.miners || [])].sort(
    (a, b) => a.health_score - b.health_score
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Fleet Health</h1>
        <div className="text-sm text-muted-foreground">
          {data?.monitored_miners} of {data?.total_miners} miners monitored
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="p-4">
          <div className="text-sm font-medium text-muted-foreground">
            Excellent Health
          </div>
          <div className="mt-2 text-2xl font-bold text-green-500">
            {sortedMiners.filter((m) => m.health_score >= 80).length}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sm font-medium text-muted-foreground">
            Good Health
          </div>
          <div className="mt-2 text-2xl font-bold text-yellow-500">
            {sortedMiners.filter((m) => m.health_score >= 60 && m.health_score < 80).length}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sm font-medium text-muted-foreground">
            Fair Health
          </div>
          <div className="mt-2 text-2xl font-bold text-orange-500">
            {sortedMiners.filter((m) => m.health_score >= 40 && m.health_score < 60).length}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sm font-medium text-muted-foreground">
            Poor Health
          </div>
          <div className="mt-2 text-2xl font-bold text-red-500">
            {sortedMiners.filter((m) => m.health_score < 40).length}
          </div>
        </Card>
      </div>

      {/* Info Banner for SENSOR_MISSING */}
      {sortedMiners.filter(m => m.reasons.some(r => typeof r === 'object' && r.code === 'SENSOR_MISSING')).length > 0 && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <div className="flex items-start gap-3">
            <div className="text-blue-600 text-xl">ℹ️</div>
            <div className="flex-1">
              <div className="font-medium text-blue-900">Miners Powered Down</div>
              <div className="text-sm text-blue-700 mt-1">
                SENSOR_MISSING errors are expected when miners are OFF due to Agile pricing. 
                They will automatically resume when electricity is cheaper.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Miner Health Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {sortedMiners.map((miner) => (
          <Card
            key={miner.miner_id}
            className={`p-4 cursor-pointer hover:shadow-lg transition-shadow ${getHealthBg(
              miner.health_score
            )}`}
            onClick={() => navigate(`/health/${miner.miner_id}`)}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">{miner.miner_name}</h3>
                  <MinerTypeBadge type={miner.miner_type} size="sm" />
                </div>
                <div className="text-xs text-muted-foreground">
                  {miner.current_mode}
                </div>
              </div>
              <div className="text-right">
                <div className={`text-3xl font-bold ${getHealthColor(miner.health_score)}`}>
                  {miner.health_score}
                </div>
                <div className={`text-xs font-medium ${getHealthColor(miner.health_score)}`}>
                  {getHealthStatus(miner.health_score)}
                </div>
              </div>
            </div>

            {miner.reasons.length > 0 && (
              <div className="mt-3 space-y-1">
                {miner.reasons.map((reason, idx) => (
                  <div
                    key={idx}
                    className="text-xs px-2 py-1 rounded bg-background/50"
                  >
                    ⚠️ {formatReasonText(reason)}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>Anomaly: {miner.anomaly_score != null ? miner.anomaly_score.toFixed(2) : 'N/A'}</span>
              <span>{formatTimestamp(miner.timestamp)}</span>
            </div>
          </Card>
        ))}
      </div>

      {sortedMiners.length === 0 && (
        <Card className="p-8 text-center">
          <div className="text-muted-foreground">
            No health data available yet. Health monitoring will begin once miners report telemetry.
          </div>
        </Card>
      )}
    </div>
  );
}
