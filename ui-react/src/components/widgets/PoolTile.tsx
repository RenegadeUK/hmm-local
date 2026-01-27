import { Card, CardContent } from "@/components/ui/card";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

interface PoolTileProps {
  coin: "BTC" | "BCH" | "DGB" | "BC2";
  workersOnline: number;
  hashrate: string;
  currentLuck: number | null;
  ettb: string | null;
  lastBlockTime: string | null;
  blocks24h: number;
  blocks7d: number;
  blocks30d: number;
  shares: number;
  lastShare: string | null;
  totalPaid: string;
  paidValue: string;
  accountUrl: string;
  isStrategyActive?: boolean;
  isStrategyInactive?: boolean;
}

const coinConfig = {
  BTC: { name: "Bitcoin", color: "border-orange-500/90", bg: "bg-orange-500/10", logo: "₿" },
  BCH: { name: "Bitcoin Cash", color: "border-green-500/90", bg: "bg-green-500/10", logo: "BCH" },
  DGB: { name: "DigiByte", color: "border-blue-500/90", bg: "bg-blue-500/10", logo: "DGB" },
  BC2: { name: "BellsCoin", color: "border-purple-500/90", bg: "bg-purple-500/10", logo: "BC2" },
};

export function PoolTile({
  coin,
  workersOnline,
  hashrate,
  currentLuck,
  ettb,
  lastBlockTime,
  blocks24h,
  blocks7d,
  blocks30d,
  shares,
  lastShare,
  totalPaid,
  paidValue,
  accountUrl,
  isStrategyActive,
  isStrategyInactive,
}: PoolTileProps) {
  const config = coinConfig[coin];
  
  const formatLuck = (luck: number | null) => {
    if (luck === null) return "N/A";
    if (luck >= 1000) return `${(luck / 1000).toFixed(1)}k%`;
    return `${luck.toFixed(0)}%`;
  };

  return (
    <div
      className={cn(
        "rounded-lg p-1 transition-all",
        isStrategyActive && `border-4 ${config.color}`,
        isStrategyInactive && "border-2 border-muted opacity-60"
      )}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {/* Workers Online */}
        <Card className={cn("hover:shadow-md transition-all", config.bg)}>
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1">
              {config.logo} Workers Online
            </div>
            <div className="text-2xl font-bold">{workersOnline}</div>
            {hashrate && (
              <div className="text-xs text-muted-foreground mt-1">{hashrate}</div>
            )}
          </CardContent>
        </Card>

        {/* Current Round Luck */}
        <Card
          className="hover:shadow-md transition-all cursor-pointer"
          onClick={() => window.open(accountUrl, "_blank")}
        >
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
              {config.logo} Current Round Luck
              <ExternalLink className="h-3 w-3" />
            </div>
            <div className="text-2xl font-bold">{formatLuck(currentLuck)}</div>
            {ettb && (
              <div className="text-xs text-muted-foreground mt-1">
                ETTB: {ettb}
                {lastBlockTime && <div className="text-xs mt-0.5">{lastBlockTime}</div>}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Blocks Found */}
        <Card
          className="hover:shadow-md transition-all cursor-pointer"
          onClick={() => window.open(accountUrl, "_blank")}
        >
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
              {config.logo} Blocks (24h/7d/30d)
              <ExternalLink className="h-3 w-3" />
            </div>
            <div className="text-2xl font-bold">
              {blocks24h} / {blocks7d} / {blocks30d}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Shares: {shares.toLocaleString()}
              {lastShare && <div className="text-xs mt-0.5">{lastShare}</div>}
            </div>
          </CardContent>
        </Card>

        {/* Total Paid */}
        <Card
          className="hover:shadow-md transition-all cursor-pointer"
          onClick={() => window.open(accountUrl, "_blank")}
        >
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
              {config.logo} Total Paid
              <ExternalLink className="h-3 w-3" />
            </div>
            <div className="text-lg font-bold">{totalPaid}</div>
            <div className="text-xs text-muted-foreground mt-1">{paidValue}</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
