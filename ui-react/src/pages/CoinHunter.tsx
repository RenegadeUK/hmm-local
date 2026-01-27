import { useQuery } from '@tanstack/react-query';
import { Trophy, Medal, Coins } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

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
    switch (rank) {
      case 1:
        return 'bg-gradient-to-br from-yellow-100 to-yellow-200 border-yellow-400 dark:from-yellow-900/30 dark:to-yellow-800/30 dark:border-yellow-700';
      case 2:
        return 'bg-gradient-to-br from-gray-100 to-gray-200 border-gray-400 dark:from-gray-800/30 dark:to-gray-700/30 dark:border-gray-600';
      case 3:
        return 'bg-gradient-to-br from-orange-100 to-orange-200 border-orange-400 dark:from-orange-900/30 dark:to-orange-800/30 dark:border-orange-700';
      default:
        return 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700';
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
          <CardTitle className="text-lg flex items-center gap-2">
            <Medal className="h-5 w-5" />
            Scoring System
          </CardTitle>
          <CardDescription>
            Points awarded based on relative difficulty of each blockchain
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="flex items-center justify-between p-3 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800">
              <div className="flex items-center gap-2">
                <span className="text-2xl">₿</span>
                <span className="font-semibold">BTC</span>
              </div>
              <span className="px-2 py-1 rounded text-xs font-bold bg-orange-500 text-white">
                1,000 pts
              </span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
              <div className="flex items-center gap-2">
                <span className="text-2xl">฿</span>
                <span className="font-semibold">BCH</span>
              </div>
              <span className="px-2 py-1 rounded text-xs font-bold bg-green-500 text-white">
                100 pts
              </span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
              <div className="flex items-center gap-2">
                <span className="text-2xl">฿₂</span>
                <span className="font-semibold">BC2</span>
              </div>
              <span className="px-2 py-1 rounded text-xs font-bold bg-blue-500 text-white">
                50 pts
              </span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800">
              <div className="flex items-center gap-2">
                <span className="text-2xl">◆</span>
                <span className="font-semibold">DGB</span>
              </div>
              <span className="px-2 py-1 rounded text-xs font-bold bg-purple-500 text-white">
                1 pt
              </span>
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
                className={`transition-all hover:shadow-lg ${getRankStyle(entry.rank)}`}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center h-10 w-10 rounded-full bg-primary/10 text-primary font-bold text-lg">
                        {medal || `#${entry.rank}`}
                      </div>
                      <div>
                        <CardTitle className="text-lg">{entry.miner_name}</CardTitle>
                        <CardDescription className="capitalize">
                          {entry.miner_type.replace('_', ' ')}
                        </CardDescription>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-primary">
                        {entry.total_score.toLocaleString()}
                      </div>
                      <div className="text-xs text-muted-foreground">points</div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {hasBlocks ? (
                    <div>
                      <div className="grid grid-cols-2 gap-3 mb-3">
                        {/* BTC */}
                        {entry.btc_blocks > 0 && (
                          <div className="flex items-center justify-between p-2 rounded-md bg-orange-50 dark:bg-orange-900/20">
                            <span className="text-sm flex items-center gap-1">
                              <span className="text-lg">₿</span>
                              <span className="font-medium">BTC</span>
                            </span>
                            <span className="font-bold">{entry.btc_blocks}</span>
                          </div>
                        )}
                        
                        {/* BCH */}
                        {entry.bch_blocks > 0 && (
                          <div className="flex items-center justify-between p-2 rounded-md bg-green-50 dark:bg-green-900/20">
                            <span className="text-sm flex items-center gap-1">
                              <span className="text-lg">฿</span>
                              <span className="font-medium">BCH</span>
                            </span>
                            <span className="font-bold">{entry.bch_blocks}</span>
                          </div>
                        )}
                        
                        {/* BC2 */}
                        {entry.bc2_blocks > 0 && (
                          <div className="flex items-center justify-between p-2 rounded-md bg-blue-50 dark:bg-blue-900/20">
                            <span className="text-sm flex items-center gap-1">
                              <span className="text-lg">฿₂</span>
                              <span className="font-medium">BC2</span>
                            </span>
                            <span className="font-bold">{entry.bc2_blocks}</span>
                          </div>
                        )}
                        
                        {/* DGB */}
                        {entry.dgb_blocks > 0 && (
                          <div className="flex items-center justify-between p-2 rounded-md bg-purple-50 dark:bg-purple-900/20">
                            <span className="text-sm flex items-center gap-1">
                              <span className="text-lg">◆</span>
                              <span className="font-medium">DGB</span>
                            </span>
                            <span className="font-bold">{entry.dgb_blocks}</span>
                          </div>
                        )}
                      </div>
                      
                      <div className="flex items-center justify-between pt-2 border-t border-border">
                        <span className="text-sm text-muted-foreground">Total Blocks</span>
                        <span className="px-2 py-1 rounded text-xs font-bold border border-border">
                          {entry.total_blocks}
                        </span>
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
