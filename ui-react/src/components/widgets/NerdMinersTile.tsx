import { Card, CardContent } from "@/components/ui/card";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

interface NerdMinersTileProps {
  workersOnline: number;
  hashrate: string;
  shares: number;
  lastShare: string | null;
  lastShareTimestamp: number | null;
  bestShare: number;
  bestEver: number;
  poolTotalWorkers: number;
  poolDifficulty: number;
  walletAddress: string;
  isStrategyActive?: boolean;
  isStrategyInactive?: boolean;
}

export function NerdMinersTile({
  workersOnline,
  hashrate,
  shares,
  lastShare,
  bestShare,
  bestEver,
  poolTotalWorkers,
  poolDifficulty,
  walletAddress,
  isStrategyActive,
  isStrategyInactive,
}: NerdMinersTileProps) {
  const accountUrl = `https://pool.nerdminers.org/users/${walletAddress}`;

  return (
    <div
      className={cn(
        "rounded-lg p-1 transition-all",
        isStrategyActive && "border-4 border-orange-500/90",
        isStrategyInactive && "border-2 border-muted opacity-60"
      )}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {/* Tile 1: Workers Online + Hashrate */}
        <Card className="hover:shadow-md transition-all bg-orange-500/10">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1">
              NerdMiners Workers
            </div>
            <div className="text-2xl font-bold">
              {workersOnline}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {hashrate}
            </div>
          </CardContent>
        </Card>

        {/* Tile 2: Shares + Last Share */}
        <Card className="hover:shadow-md transition-all bg-orange-500/10">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1">
              Shares
            </div>
            <div className="text-2xl font-bold">
              {shares.toLocaleString()}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {lastShare || "No shares yet"}
            </div>
          </CardContent>
        </Card>

        {/* Tile 3: Best Share + Best Ever */}
        <Card className="hover:shadow-md transition-all bg-orange-500/10">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1">
              Best Share
            </div>
            <div className="text-2xl font-bold">
              {bestShare.toFixed(2)}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Best Ever: {bestEver.toFixed(2)}
            </div>
          </CardContent>
        </Card>

        {/* Tile 4: Pool Total Workers + Difficulty */}
        <Card className="hover:shadow-md transition-all bg-orange-500/10">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-muted-foreground mb-1">
              Pool Workers
            </div>
            <div className="text-2xl font-bold">
              {poolTotalWorkers.toLocaleString()}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Diff: {poolDifficulty}
            </div>
            <a
              href={accountUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-1"
            >
              View Account <ExternalLink className="h-3 w-3" />
            </a>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
