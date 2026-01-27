import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Trophy, Zap, Calendar, TrendingUp, Award, Flame } from 'lucide-react'

interface LeaderboardEntry {
  id: number
  rank: number
  miner_id: number
  miner_name: string
  miner_type: string
  coin: string
  pool_name: string
  difficulty: number
  difficulty_formatted: string
  network_difficulty: number | null
  was_block_solve: boolean
  percent_of_block: number | null
  badge: string | null
  hashrate: number | null
  hashrate_unit: string
  miner_mode: string | null
  timestamp: string
  days_ago: number
}

interface LeaderboardResponse {
  entries: LeaderboardEntry[]
  total_count: number
  filter_coin: string | null
  filter_days: number
}

export function Leaderboard() {
  const [selectedDays, setSelectedDays] = useState(90)
  const [selectedCoin, setSelectedCoin] = useState<string | null>(null)

  const { data, isLoading } = useQuery<LeaderboardResponse>({
    queryKey: ['leaderboard', selectedDays, selectedCoin],
    queryFn: async () => {
      const params = new URLSearchParams({
        days: selectedDays.toString(),
        limit: '10',
      })
      if (selectedCoin) params.append('coin', selectedCoin)
      
      const response = await fetch(`/api/leaderboard?${params}`)
      if (!response.ok) throw new Error('Failed to fetch leaderboard')
      return response.json()
    },
    refetchInterval: 30000,
  })

  const getRankStyle = (rank: number) => {
    switch (rank) {
      case 1:
        return 'text-yellow-500 text-4xl'
      case 2:
        return 'text-gray-400 text-3xl'
      case 3:
        return 'text-orange-600 text-2xl'
      default:
        return 'text-muted-foreground text-xl'
    }
  }

  const getRankIcon = (rank: number) => {
    switch (rank) {
      case 1:
        return '🥇'
      case 2:
        return '🥈'
      case 3:
        return '🥉'
      default:
        return `#${rank}`
    }
  }

  const getBadgeColor = (badge: string | null) => {
    if (!badge) return ''
    if (badge.includes('Emotional Damage')) return 'bg-red-100 text-red-800 border-red-300'
    if (badge.includes('Pain')) return 'bg-orange-100 text-orange-800 border-orange-300'
    if (badge.includes('So Close')) return 'bg-yellow-100 text-yellow-800 border-yellow-300'
    return 'bg-gray-100 text-gray-800 border-gray-300'
  }

  const coins = ['BTC', 'BCH', 'BC2', 'DGB']
  const dayOptions = [7, 30, 90, 180, 365]

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Hall of Pain</h1>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted-foreground">Loading leaderboard...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Trophy className="h-8 w-8 text-yellow-500" />
            Hall of Pain
          </h1>
          <p className="text-muted-foreground mt-1">
            The highest difficulty shares that almost won blocks
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold">{data?.total_count || 0}</div>
          <div className="text-sm text-muted-foreground">epic fails</div>
        </div>
      </div>

      {/* Filters */}
      <Card className="p-4">
        <div className="flex flex-wrap gap-4 items-center">
          {/* Time Range Filter */}
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Time Range:</span>
            <div className="flex gap-2">
              {dayOptions.map((days) => (
                <button
                  key={days}
                  onClick={() => setSelectedDays(days)}
                  className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                    selectedDays === days
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  }`}
                >
                  {days}d
                </button>
              ))}
            </div>
          </div>

          {/* Coin Filter */}
          <div className="flex items-center gap-2 ml-auto">
            <Zap className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Coin:</span>
            <div className="flex gap-2">
              <button
                onClick={() => setSelectedCoin(null)}
                className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                  selectedCoin === null
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                }`}
              >
                All
              </button>
              {coins.map((coin) => (
                <button
                  key={coin}
                  onClick={() => setSelectedCoin(coin)}
                  className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                    selectedCoin === coin
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  }`}
                >
                  {coin}
                </button>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Leaderboard Entries */}
      <div className="space-y-3">
        {data?.entries.map((entry) => (
          <Card
            key={entry.id}
            className={`p-6 transition-all hover:shadow-lg ${
              entry.rank <= 3 ? 'border-2' : ''
            } ${
              entry.rank === 1
                ? 'border-yellow-500/50 bg-yellow-50/50 dark:bg-yellow-950/20'
                : entry.rank === 2
                ? 'border-gray-400/50 bg-gray-50/50 dark:bg-gray-950/20'
                : entry.rank === 3
                ? 'border-orange-600/50 bg-orange-50/50 dark:bg-orange-950/20'
                : ''
            }`}
          >
            <div className="flex items-start gap-6">
              {/* Rank */}
              <div className="flex flex-col items-center justify-center min-w-[80px]">
                <div className={`font-bold ${getRankStyle(entry.rank)}`}>
                  {entry.rank <= 3 ? getRankIcon(entry.rank) : `#${entry.rank}`}
                </div>
                {entry.rank <= 3 && (
                  <div className="text-xs text-muted-foreground mt-1">
                    {entry.rank === 1 ? 'Gold' : entry.rank === 2 ? 'Silver' : 'Bronze'}
                  </div>
                )}
              </div>

              {/* Content */}
              <div className="flex-1 space-y-3">
                {/* Miner Info */}
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-semibold">{entry.miner_name}</h3>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground font-medium">
                        {entry.miner_type}
                      </span>
                      {entry.was_block_solve && (
                        <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800 border border-green-300 font-medium">
                          <Award className="h-3 w-3" />
                          Block Solved!
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground mt-1">
                      {entry.pool_name} • {entry.days_ago} {entry.days_ago === 1 ? 'day' : 'days'} ago
                    </div>
                  </div>

                  {/* Badge */}
                  {entry.badge && (
                    <div
                      className={`px-3 py-1 rounded-full text-sm font-semibold border ${getBadgeColor(
                        entry.badge
                      )}`}
                    >
                      {entry.badge}
                    </div>
                  )}
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {/* Difficulty */}
                  <div className="space-y-1">
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <TrendingUp className="h-3 w-3" />
                      Share Difficulty
                    </div>
                    <div className="text-xl font-bold">{entry.difficulty_formatted}</div>
                  </div>

                  {/* Network % */}
                  {entry.percent_of_block !== null && (
                    <div className="space-y-1">
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Flame className="h-3 w-3" />
                        Network %
                      </div>
                      <div className="text-xl font-bold text-orange-600">
                        {entry.percent_of_block.toFixed(1)}%
                      </div>
                    </div>
                  )}

                  {/* Hashrate */}
                  {entry.hashrate !== null && (
                    <div className="space-y-1">
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Zap className="h-3 w-3" />
                        Hashrate
                      </div>
                      <div className="text-xl font-bold">
                        {entry.hashrate.toFixed(0)} {entry.hashrate_unit}
                      </div>
                    </div>
                  )}

                  {/* Coin */}
                  <div className="space-y-1">
                    <div className="text-xs text-muted-foreground">Coin</div>
                    <div className="text-xl font-bold text-primary">{entry.coin}</div>
                  </div>
                </div>

                {/* Mode */}
                {entry.miner_mode && (
                  <div className="text-xs text-muted-foreground">
                    Mode: <span className="font-medium text-foreground uppercase">{entry.miner_mode}</span>
                  </div>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Empty State */}
      {data?.entries.length === 0 && (
        <Card className="p-12 text-center">
          <Trophy className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No Epic Fails Yet</h3>
          <p className="text-muted-foreground">
            No high difficulty shares found for the selected time range and coin.
          </p>
        </Card>
      )}
    </div>
  )
}
