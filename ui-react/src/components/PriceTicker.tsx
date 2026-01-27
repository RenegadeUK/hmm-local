import { useQuery } from "@tanstack/react-query";

interface PriceTickerProps {
  className?: string;
}

export function PriceTicker({ className = "" }: PriceTickerProps) {
  const { data: cryptoPrices } = useQuery({
    queryKey: ["crypto-prices"],
    queryFn: async () => {
      const response = await fetch("/api/settings/crypto-prices");
      return response.json();
    },
    refetchInterval: 30000, // 30 seconds
  });

  const { data: dashboardData } = useQuery({
    queryKey: ["dashboard", "ticker"],
    queryFn: async () => {
      const response = await fetch("/api/dashboard/all?dashboard_type=all");
      return response.json();
    },
    refetchInterval: 30000, // 30 seconds
  });

  const getEnergyPriceColor = (price: number) => {
    if (price < 0) return "#3b82f6"; // blue (negative pricing!)
    if (price >= 30) return "#ef4444"; // red
    if (price >= 20) return "#f59e0b"; // orange
    return "#10b981"; // green
  };

  if (!cryptoPrices?.success && !dashboardData) return null;

  const prices: React.ReactNode[] = [];

  // Energy price
  const energyPrice = dashboardData?.stats?.current_energy_price_pence;
  if (energyPrice !== null && energyPrice !== undefined) {
    const color = getEnergyPriceColor(energyPrice);
    prices.push(
      <span key="energy" style={{ color }}>
        {energyPrice.toFixed(2)}p/kWh
      </span>
    );
  }

  // Crypto prices
  if (cryptoPrices?.success) {
    if (cryptoPrices.bitcoin > 0) {
      prices.push(
        <span key="btc">
          BTC £{cryptoPrices.bitcoin.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}
        </span>
      );
    }

    if (cryptoPrices["bitcoin-cash"] > 0) {
      prices.push(
        <span key="bch">
          BCH £{cryptoPrices["bitcoin-cash"].toFixed(0)}
        </span>
      );
    }

    if (cryptoPrices.bellscoin > 0) {
      prices.push(
        <span key="bc2">
          BC2 £{cryptoPrices.bellscoin.toFixed(6)}
        </span>
      );
    }

    if (cryptoPrices.digibyte > 0) {
      prices.push(
        <span key="dgb">
          DGB £{cryptoPrices.digibyte.toFixed(4)}
        </span>
      );
    }
  }

  if (prices.length === 0) return null;

  return (
    <div className={`flex items-center gap-3 text-sm ${className}`}>
      {prices.map((price, index) => (
        <span key={index}>
          {price}
          {index < prices.length - 1 && (
            <span className="mx-2 text-muted-foreground">|</span>
          )}
        </span>
      ))}
    </div>
  );
}
