import { Activity, Power, DollarSign, Gauge, Network, TrendingUp, AlertCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { MinerTypeAvatar, MinerTypeBadge } from '@/components/miners/MinerTypeBadge';
import type { Miner } from '@/types/miner';

interface MinerTileProps {
  miner: Miner;
  selected: boolean;
  highlight?: boolean;
  onToggleSelect: () => void;
}

const formatHashrate = (hashrate: number, unit: string) => {
  if (hashrate === 0) return '—';
  
  // Auto-convert GH/s to TH/s when >= 1000 GH/s
  if (unit === 'GH/s' && hashrate >= 1000) {
    return `${(hashrate / 1000).toFixed(2)} TH/s`;
  }
  
  return `${hashrate.toFixed(2)} ${unit}`;
};

const getBestDiffLabel = (minerType: string) => {
  const type = minerType.toLowerCase();
  if (type === 'avalon_nano') return 'Best Share';
  if (type === 'nmminer') return 'Best Diff';
  return 'Best Session';
};

const formatBestDiff = (bestDiff: number) => {
  if (!bestDiff || bestDiff <= 0) return '—';
  
  // Format large numbers with suffixes
  if (bestDiff >= 1000000000) return `${(bestDiff / 1000000000).toFixed(2)}B`;
  if (bestDiff >= 1000000) return `${(bestDiff / 1000000).toFixed(2)}M`;
  if (bestDiff >= 1000) return `${(bestDiff / 1000).toFixed(2)}K`;
  return bestDiff.toFixed(0);
};

export default function MinerTile({ miner, selected, highlight, onToggleSelect }: MinerTileProps) {
  const hasHealthIssue = miner.health_score !== null && miner.health_score < 50;

  return (
    <Card
      className={`
        relative transition-all
        ${miner.is_offline ? 'opacity-60 bg-gray-800/30' : ''}
        ${hasHealthIssue ? 'border-l-4 border-l-red-500' : ''}
        ${selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-gray-900' : ''}
        ${highlight ? 'ring-2 ring-emerald-400/70 shadow-emerald-500/20 animate-pulse' : ''}
      `}
    >
      {/* Selection checkbox */}
      <div className="absolute top-3 right-3 z-10">
        <Checkbox
          checked={selected}
          onCheckedChange={onToggleSelect}
          className="border-gray-600"
        />
      </div>

      <CardHeader className="pb-3">
        <div className="flex items-start gap-3 pr-8">
          <MinerTypeAvatar type={miner.miner_type} size="lg" className="flex-shrink-0 shadow-inner shadow-black/20" />
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-lg truncate mb-1">{miner.name}</h3>
            <div className="flex items-center gap-2 flex-wrap">
              <MinerTypeBadge type={miner.miner_type} />
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${miner.enabled ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'}`}>
                {miner.enabled ? 'Enabled' : 'Disabled'}
              </span>
              {miner.is_offline && (
                <span className="px-2 py-0.5 rounded text-xs font-medium bg-orange-500/10 text-orange-400 border border-orange-500/20">
                  Offline
                </span>
              )}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* Hashrate */}
          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
              <Activity className="h-3 w-3" />
              <span className="uppercase tracking-wide">Hashrate</span>
            </div>
            <p className="font-semibold text-sm">{formatHashrate(miner.hashrate, miner.hashrate_unit)}</p>
          </div>

          {/* Power */}
          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
              <Power className="h-3 w-3" />
              <span className="uppercase tracking-wide">Power</span>
            </div>
            <p className="font-semibold text-sm">{miner.power > 0 ? `${miner.power.toFixed(1)} W` : '—'}</p>
          </div>

          {/* Pool */}
          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
              <Network className="h-3 w-3" />
              <span className="uppercase tracking-wide">Pool</span>
            </div>
            <p className="font-semibold text-xs truncate">{miner.pool || '—'}</p>
          </div>

          {/* 24h Cost */}
          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
              <DollarSign className="h-3 w-3" />
              <span className="uppercase tracking-wide">24h Cost</span>
            </div>
            <p className="font-semibold text-sm">£{miner.cost_24h.toFixed(2)}</p>
          </div>

          {/* Mode */}
          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
              <Gauge className="h-3 w-3" />
              <span className="uppercase tracking-wide">Mode</span>
            </div>
            <p className="font-semibold text-xs">{miner.current_mode || '—'}</p>
          </div>

          {/* Best Diff */}
          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
              <TrendingUp className="h-3 w-3" />
              <span className="uppercase tracking-wide">{getBestDiffLabel(miner.miner_type)}</span>
            </div>
            <p className="font-semibold text-xs">{formatBestDiff(miner.best_diff)}</p>
          </div>
        </div>

        {/* Health warning */}
        {hasHealthIssue && (
          <div className="flex items-center gap-2 text-red-400 text-xs bg-red-500/10 rounded-lg p-2 border border-red-500/20">
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            <span>Health score: {miner.health_score}%</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-2 border-t border-gray-700/50">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 text-xs"
            asChild
          >
            <Link to={`/miners/${miner.id}`}>View</Link>
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1 text-xs"
            asChild
          >
            <Link to={`/miners/${miner.id}/edit`}>Edit</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
