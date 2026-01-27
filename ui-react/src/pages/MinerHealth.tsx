import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeft, AlertTriangle, Info, AlertCircle } from 'lucide-react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale
} from 'chart.js';
import 'chartjs-adapter-date-fns';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale
);

interface MinerHealthDetail {
  miner_id: number;
  miner_name: string;
  health_score: number;
  status: string;
  anomaly_score: number | null;
  reasons: Array<string | {
    code: string;
    severity: string;
    metric: string;
    actual: number;
    expected_min?: number;
    expected_max?: number;
    unit?: string;
    delta_pct?: number;
  }>;
  suggested_actions: string[];
  mode: string;
  last_check: string;
}

interface HealthHistoryPoint {
  timestamp: string;
  health_score: number;
  anomaly_score: number | null;
  status: string;
}

export default function MinerHealth() {
  const { minerId } = useParams();
  const navigate = useNavigate();

  const { data: healthData, isLoading } = useQuery<MinerHealthDetail>({
    queryKey: ['minerHealth', minerId],
    queryFn: async () => {
      const res = await fetch(`/api/health/${minerId}`);
      if (!res.ok) throw new Error('Failed to fetch health data');
      return res.json();
    },
    refetchInterval: 30000,
  });

  const { data: historyData } = useQuery<HealthHistoryPoint[]>({
    queryKey: ['minerHealthHistory', minerId],
    queryFn: async () => {
      const res = await fetch(`/api/health/${minerId}/history?hours=24`);
      if (!res.ok) throw new Error('Failed to fetch history');
      return res.json();
    },
    refetchInterval: 60000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!healthData) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-muted-foreground">Miner not found</div>
      </div>
    );
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'healthy': return 'text-green-600';
      case 'warning': return 'text-yellow-600';
      case 'critical': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'critical': return <AlertCircle className="h-5 w-5" />;
      case 'warning': return <AlertTriangle className="h-5 w-5" />;
      default: return <Info className="h-5 w-5" />;
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical': return 'bg-red-100 text-red-800';
      case 'warning': return 'bg-yellow-100 text-yellow-800';
      case 'info': return 'bg-blue-100 text-blue-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const chartData = {
    labels: historyData?.map(d => new Date(d.timestamp)) || [],
    datasets: [
      {
        label: 'Health Score',
        data: historyData?.map(d => d.health_score) || [],
        borderColor: 'rgb(34, 197, 94)',
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        yAxisID: 'y',
      },
      {
        label: 'Anomaly Score',
        data: historyData?.map(d => d.anomaly_score || null) || [],
        borderColor: 'rgb(239, 68, 68)',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        yAxisID: 'y1',
        spanGaps: true,
      }
    ]
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: '24-Hour Health Timeline'
      }
    },
    scales: {
      x: {
        type: 'time' as const,
        time: {
          unit: 'hour' as const,
        },
        title: {
          display: true,
          text: 'Time'
        }
      },
      y: {
        type: 'linear' as const,
        display: true,
        position: 'left' as const,
        title: {
          display: true,
          text: 'Health Score'
        },
        min: 0,
        max: 100,
      },
      y1: {
        type: 'linear' as const,
        display: true,
        position: 'right' as const,
        title: {
          display: true,
          text: 'Anomaly Score'
        },
        min: 0,
        max: 1,
        grid: {
          drawOnChartArea: false,
        },
      },
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/app/health')}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium border rounded-md hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Fleet
        </button>
        <h1 className="text-3xl font-bold">{healthData.miner_name}</h1>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Health Score</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-bold">{healthData.health_score}</div>
            <div className={`flex items-center gap-2 mt-2 ${getStatusColor(healthData.status)}`}>
              {getStatusIcon(healthData.status)}
              <span className="font-semibold uppercase">{healthData.status}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>ML Anomaly Score</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-bold">
              {healthData.anomaly_score != null ? healthData.anomaly_score.toFixed(3) : 'N/A'}
            </div>
            <div className="text-sm text-muted-foreground mt-2">
              {healthData.anomaly_score != null ? 'Higher = more anomalous' : 'Not yet trained'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Current Mode</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-bold uppercase">{healthData.mode || 'Unknown'}</div>
            <div className="text-sm text-muted-foreground mt-2">
              Last check: {new Date(healthData.last_check).toLocaleString()}
            </div>
          </CardContent>
        </Card>
      </div>

      {healthData.reasons && healthData.reasons.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Issues Detected</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {healthData.reasons.map((reason, idx) => {
                if (typeof reason === 'string') {
                  return (
                    <div key={idx} className="border-l-4 border-yellow-500 pl-4 py-2">
                      <p className="text-sm">{reason}</p>
                    </div>
                  );
                }

                return (
                  <div key={idx} className="border rounded-lg p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-1 rounded text-xs font-semibold ${getSeverityColor(reason.severity)}`}>
                          {reason.severity}
                        </span>
                        <span className="font-mono text-sm font-semibold">{reason.code}</span>
                      </div>
                      {reason.delta_pct != null && (
                        <span className="text-sm font-semibold text-red-600">
                          {reason.delta_pct > 0 ? '+' : ''}{reason.delta_pct.toFixed(1)}%
                        </span>
                      )}
                    </div>

                    <div className="text-sm font-medium">{reason.metric}</div>
                    
                    {reason.code === 'SENSOR_MISSING' && (
                      <div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded">
                        ℹ️ This miner is likely OFF due to Agile pricing. No telemetry available when miner is powered down.
                      </div>
                    )}

                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <div className="text-muted-foreground">Actual</div>
                        <div className="font-semibold">
                          {reason.actual.toFixed(2)} {reason.unit}
                        </div>
                      </div>
                      {reason.expected_min != null && (
                        <div>
                          <div className="text-muted-foreground">Expected Min</div>
                          <div className="font-semibold">
                            {reason.expected_min.toFixed(2)} {reason.unit}
                          </div>
                        </div>
                      )}
                      {reason.expected_max != null && (
                        <div>
                          <div className="text-muted-foreground">Expected Max</div>
                          <div className="font-semibold">
                            {reason.expected_max.toFixed(2)} {reason.unit}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {healthData.suggested_actions && healthData.suggested_actions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Suggested Actions</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {healthData.suggested_actions.map((action, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-blue-600 mt-1">•</span>
                  <span className="text-sm">{action}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {historyData && historyData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Health Timeline (24 Hours)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[400px]">
              <Line data={chartData} options={chartOptions} />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
