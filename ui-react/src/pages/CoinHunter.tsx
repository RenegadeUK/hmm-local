import { useQuery } from '@tanstack/react-query';
import { Trophy, Coins } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { MinerTypeBadge } from '@/components/miners/MinerTypeBadge';
import { formatMinerTypeLabel } from '@/lib/minerTypes';

interface CoinHunterEntry {
  rank: number;
  miner_id: number;
  miner_name: string;
  miner_type: string;
  btc_blocks: number;
  bch_blocks: number;
  bc2_blocks: number;
  dgb_blocks: number;
  total_blocks: number;
  total_score: number;
}

interface CoinHunterResponse {
  entries: CoinHunterEntry[];
  scoring: {
    BTC: number;
    BCH: number;
    BC2: number;
    DGB: number;
  };
}

export default function CoinHunter() {
  const { data, isLoading, error } = useQuery<CoinHunterResponse>({
    queryKey: ['coin-hunter'],
    queryFn: async () => {
      const response = await fetch('/api/coin-hunter');
      if (!response.ok) {
        throw new Error('Failed to fetch coin hunter leaderboard');
      }
      return response.json();
    },
    refetchInterval: 60000, // Refetch every minute
  });

  const getRankStyle = (rank: number) => {
    if (rank <= 3) {
      return 'border-l-4';
    }
    return '';
  };
  
  const getRankColor = (rank: number) => {
    switch (rank) {
      case 1:
        return 'border-l-yellow-500';
      case 2:
        return 'border-l-gray-400';
      case 3:
        return 'border-l-orange-500';
      default:
        return '';
    }
  };

  const getRankMedal = (rank: number) => {
    switch (rank) {
      case 1:
        return '🥇';
      case 2:
        return '🥈';
      case 3:
        return '🥉';
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Coins className="h-8 w-8 text-green-600 dark:text-green-400" />
            Coin Hunter Leaderboard
          </h1>
          <p className="text-muted-foreground mt-1">
            All-time blocks found across all coins with weighted scoring
          </p>
        </div>
      </div>

      {/* Scoring Legend */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Scoring System</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-lg">₿</span>
              <span>BTC</span>
              <span className="text-muted-foreground">1,000 pts</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-lg">฿</span>
              <span>BCH</span>
              <span className="text-muted-foreground">100 pts</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-lg">฿₂</span>
              <span>BC2</span>
              <span className="text-muted-foreground">50 pts</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-lg">◆</span>
              <span>DGB</span>
              <span className="text-muted-foreground">1 pt</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Loading State */}
      {isLoading && (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 dark:border-gray-100 mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading leaderboard...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center">
              <p className="text-red-500">Failed to load leaderboard</p>
              <p className="text-sm text-muted-foreground mt-2">
                {error instanceof Error ? error.message : 'Unknown error'}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Leaderboard Entries */}
      {data && data.entries.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {data.entries.map((entry) => {
            const medal = getRankMedal(entry.rank);
            const hasBlocks = entry.total_blocks > 0;
            
            return (
              <Card
                key={`${entry.miner_id}-${entry.rank}`}
                className={`transition-all hover:shadow-md ${getRankStyle(entry.rank)} ${getRankColor(entry.rank)}`}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="text-2xl font-bold text-muted-foreground w-12">
                        {medal || `#${entry.rank}`}
                      </div>
                      <div>
                        <CardTitle className="text-base flex items-center gap-2">
                          <span>{entry.miner_name}</span>
                          <MinerTypeBadge type={entry.miner_type} size="sm" />
                        </CardTitle>
                        <CardDescription className="text-xs flex items-center gap-2 text-muted-foreground">
                          <span className="font-semibold text-foreground">
                            {entry.total_score.toLocaleString()} pts
                          </span>
                          <span aria-hidden="true">•</span>
                          <span>{formatMinerTypeLabel(entry.miner_type)}</span>
                        </CardDescription>
                      </div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {hasBlocks ? (
                    <div className="flex items-center gap-4 text-sm">
                      {entry.btc_blocks > 0 && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-lg">₿</span>
                          <span className="font-semibold">{entry.btc_blocks}</span>
                        </div>
                      )}
                      {entry.bch_blocks > 0 && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-lg">฿</span>
                          <span className="font-semibold">{entry.bch_blocks}</span>
                        </div>
                      )}
                      {entry.bc2_blocks > 0 && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-lg">฿₂</span>
                          <span className="font-semibold">{entry.bc2_blocks}</span>
                        </div>
                      )}
                      {entry.dgb_blocks > 0 && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-lg">◆</span>
                          <span className="font-semibold">{entry.dgb_blocks}</span>
                        </div>
                      )}
                      <div className="ml-auto text-xs text-muted-foreground">
                        {entry.total_blocks} total
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-4 text-sm text-muted-foreground">
                      No blocks found yet
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {data && data.entries.length === 0 && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center">
              <Trophy className="h-12 w-12 mx-auto text-muted-foreground/50" />
              <h3 className="mt-4 text-lg font-semibold">No Blocks Found Yet</h3>
              <p className="text-muted-foreground mt-2">
                Keep mining! Block discoveries will appear here.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
