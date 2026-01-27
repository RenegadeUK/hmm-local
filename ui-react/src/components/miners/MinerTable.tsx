import { Activity, Power, DollarSign, Gauge, Network, TrendingUp } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import type { Miner } from '@/types/miner';

interface MinerTableProps {
  miners: Miner[];
  selectedMiners: Set<number>;
  onToggleSelect: (minerId: number) => void;
  onToggleSelectAll: () => void;
}

const getMinerTypeColor = (type: string) => {
  const normalized = type.toLowerCase().replace(/\s+/g, '_');
  
  if (normalized.includes('bitaxe')) return { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20' };
  if (normalized.includes('nerdqaxe') || normalized.includes('qaxe')) return { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20' };
  if (normalized.includes('avalon')) return { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/20' };
  if (normalized.includes('nmminer')) return { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/20' };
  if (normalized.includes('xmrig')) return { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20' };
  
  return { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/20' };
};

const getMinerIcon = (type: string) => {
  const normalized = type.toLowerCase();
  if (normalized.includes('xmrig')) return '💻';
  if (normalized.includes('bitaxe')) return '🔷';
  if (normalized.includes('nerdqaxe') || normalized.includes('qaxe')) return '🤓';
  if (normalized.includes('nmminer')) return '📡';
  return '⛏️';
};

const formatHashrate = (hashrate: number, unit: string) => {
  if (hashrate === 0) return '—';
  return `${hashrate.toFixed(2)} ${unit}`;
};

const formatBestDiff = (bestDiff: number, minerType: string, firmwareVersion: string | null) => {
  const type = minerType.toLowerCase();
  
  if (type.includes('xmrig')) return firmwareVersion || '—';
  if (!bestDiff || bestDiff <= 0) return '—';
  
  if (bestDiff >= 1000000000) return `${(bestDiff / 1000000000).toFixed(2)}B`;
  if (bestDiff >= 1000000) return `${(bestDiff / 1000000).toFixed(2)}M`;
  if (bestDiff >= 1000) return `${(bestDiff / 1000).toFixed(2)}K`;
  return bestDiff.toFixed(0);
};

export default function MinerTable({ miners, selectedMiners, onToggleSelect, onToggleSelectAll }: MinerTableProps) {
  const allSelected = miners.length > 0 && selectedMiners.size === miners.length;

  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-800/50 border-b border-gray-700">
              <tr>
                <th className="text-left p-4 w-12">
                  <Checkbox
                    checked={allSelected}
                    onCheckedChange={onToggleSelectAll}
                    className="border-gray-600"
                  />
                </th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">Miner</th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">Status</th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center gap-2">
                    <Activity className="h-3 w-3" />
                    Hashrate
                  </div>
                </th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center gap-2">
                    <Power className="h-3 w-3" />
                    Power
                  </div>
                </th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center gap-2">
                    <Network className="h-3 w-3" />
                    Pool
                  </div>
                </th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center gap-2">
                    <DollarSign className="h-3 w-3" />
                    24h Cost
                  </div>
                </th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center gap-2">
                    <Gauge className="h-3 w-3" />
                    Mode
                  </div>
                </th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="h-3 w-3" />
                    Best Diff
                  </div>
                </th>
                <th className="text-left p-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700/50">
              {miners.map((miner) => {
                const typeColors = getMinerTypeColor(miner.miner_type);
                const hasHealthIssue = miner.health_score !== null && miner.health_score < 50;
                const isSelected = selectedMiners.has(miner.id);

                return (
                  <tr
                    key={miner.id}
                    className={`
                      hover:bg-gray-800/30 transition-colors
                      ${miner.is_offline ? 'opacity-60 bg-gray-800/20' : ''}
                      ${hasHealthIssue ? 'border-l-4 border-l-red-500' : ''}
                      ${isSelected ? 'bg-blue-500/5' : ''}
                    `}
                  >
                    <td className="p-4">
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={() => onToggleSelect(miner.id)}
                        className="border-gray-600"
                      />
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-3">
                        <span className="text-xl flex-shrink-0">{getMinerIcon(miner.miner_type)}</span>
                        <div className="min-w-0">
                          <p className="font-medium truncate">{miner.name}</p>
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium border mt-1 ${typeColors.bg} ${typeColors.text} ${typeColors.border}`}>
                            {miner.miner_type}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="flex flex-col gap-1">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium w-fit ${miner.enabled ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'}`}>
                          {miner.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                        {miner.is_offline && (
                          <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-orange-500/10 text-orange-400 border border-orange-500/20 w-fit">
                            Offline
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="p-4 font-medium text-sm">{formatHashrate(miner.hashrate, miner.hashrate_unit)}</td>
                    <td className="p-4 text-sm">{miner.power > 0 ? `${miner.power.toFixed(1)} W` : '—'}</td>
                    <td className="p-4 text-sm">{miner.pool || '—'}</td>
                    <td className="p-4 font-medium text-sm">£{miner.cost_24h.toFixed(2)}</td>
                    <td className="p-4 text-sm">{miner.current_mode || '—'}</td>
                    <td className="p-4 text-xs">{formatBestDiff(miner.best_diff, miner.miner_type, miner.firmware_version)}</td>
                    <td className="p-4">
                      <div className="flex gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs"
                          asChild
                        >
                          <a href={`/miners/${miner.id}`}>View</a>
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs"
                          asChild
                        >
                          <a href={`/miners/${miner.id}/edit`}>Edit</a>
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
