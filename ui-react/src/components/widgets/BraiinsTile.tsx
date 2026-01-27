import { Card, CardContent } from "@/components/ui/card";
import { ExternalLink } from "lucide-react";

interface BraiinsTileProps {
  workersOnline: number;
  workersOffline: number;
  hashrate5m: string | null;
  hashrateRaw: number;
  currentBalance: number;
  todayReward: number;
  allTimeReward: number;
  username: string;
  btcPriceGBP: number;
  isStrategyActive?: boolean;
  isStrategyInactive?: boolean;
}

export function BraiinsTile({
  workersOnline,
  workersOffline,
  hashrate5m,
  currentBalance,
  todayReward,
  allTimeReward,
  username,
  btcPriceGBP,
  isStrategyActive,
  isStrategyInactive,
}: BraiinsTileProps) {
  const balanceBTC = currentBalance / 100000000;
  const todayBTC = todayReward / 100000000;
  const allTimeBTC = allTimeReward / 100000000;

  const balanceGBP = (balanceBTC * btcPriceGBP).toFixed(2);
  const todayGBP = (todayBTC * btcPriceGBP).toFixed(2);

  const accountUrl = username ? `https://pool.braiins.com/accounts/${username}` : "https://pool.braiins.com";

  return (
    <div
      className={`rounded-lg p-1 transition-all ${
        isStrategyActive ? "border-4 border-orange-500/90" : ""
      } ${isStrategyInactive ? "border-2 border-muted opacity-60" : ""}`}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {/* Workers Online/Offline */}
        <Card className="hover:shadow-md transition-all bg-orange-500/10">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1">
              ₿ Workers (Online/Offline)
            </div>
            <div className="text-2xl font-bold">
              {workersOnline} / {workersOffline}
            </div>
            {hashrate5m && (
              <div className="text-xs text-muted-foreground mt-1">{hashrate5m}</div>
            )}
          </CardContent>
        </Card>

        {/* Current Balance */}
        <Card
          className="hover:shadow-md transition-all cursor-pointer"
          onClick={() => window.open(accountUrl, "_blank")}
        >
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
              ₿ Current Balance
              <ExternalLink className="h-3 w-3" />
            </div>
            <div className="text-lg font-bold">
              {balanceBTC.toFixed(8)} BTC
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              £{balanceGBP}
            </div>
          </CardContent>
        </Card>

        {/* Today's Reward */}
        <Card
          className="hover:shadow-md transition-all cursor-pointer"
          onClick={() => window.open(accountUrl, "_blank")}
        >
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
              ₿ Today's Reward
              <ExternalLink className="h-3 w-3" />
            </div>
            <div className="text-lg font-bold">
              {todayBTC.toFixed(8)} BTC
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              £{todayGBP}
            </div>
          </CardContent>
        </Card>

        {/* All-Time Reward */}
        <Card
          className="hover:shadow-md transition-all cursor-pointer"
          onClick={() => window.open(accountUrl, "_blank")}
        >
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
              ₿ All-Time Reward
              <ExternalLink className="h-3 w-3" />
            </div>
            <div className="text-lg font-bold">
              {allTimeBTC.toFixed(8)} BTC
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              £{(allTimeBTC * btcPriceGBP).toFixed(2)}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
