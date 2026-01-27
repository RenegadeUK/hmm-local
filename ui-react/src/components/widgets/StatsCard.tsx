import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatsCardProps {
  label: string;
  value: string | number;
  subtext?: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

export function StatsCard({ label, value, subtext, onClick, className }: StatsCardProps) {
  return (
    <Card
      className={cn(
        "transition-all hover:shadow-md",
        onClick && "cursor-pointer hover:scale-105",
        className
      )}
      onClick={onClick}
    >
      <CardContent className="p-6">
        <div className="text-sm font-medium text-muted-foreground mb-2">{label}</div>
        <div className="text-3xl font-bold mb-2">{value}</div>
        {subtext && (
          <div className="text-sm text-muted-foreground space-y-1">
            {subtext}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
