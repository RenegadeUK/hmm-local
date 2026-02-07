import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useEffect, useRef } from "react";

interface ChartDataPoint {
  x: number;  // timestamp in milliseconds
  y: number;  // value
}

interface StatsCardProps {
  label: string;
  value: string | number;
  subtext?: React.ReactNode;
  onClick?: () => void;
  className?: string;
  badge?: React.ReactNode;
  borderColor?: string;
  chartData?: ChartDataPoint[];  // Sparkline data
  chartColor?: string;  // Custom sparkline color
}

export function StatsCard({ 
  label, 
  value, 
  subtext, 
  onClick, 
  className, 
  badge, 
  borderColor,
  chartData,
  chartColor = "rgba(59, 130, 246, 0.3)"  // Default blue
}: StatsCardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  // Draw sparkline in background
  useEffect(() => {
    if (!canvasRef.current || !chartData || chartData.length < 2) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const parent = canvas.parentElement;
    if (!parent) return;
    
    const rect = parent.getBoundingClientRect();
    const width = Math.max(rect.width, 100);
    const height = Math.max(rect.height, 50);
    
    // Set canvas size with device pixel ratio
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);
    
    // Sort data by timestamp
    const sortedData = [...chartData]
      .filter(d => d && d.y !== null && d.y !== undefined)
      .sort((a, b) => a.x - b.x);
    
    if (sortedData.length < 2) return;
    
    // Get min/max for scaling
    const yValues = sortedData.map(d => d.y);
    const minY = Math.min(...yValues);
    const maxY = Math.max(...yValues);
    const range = maxY - minY;
    
    // If all values are the same (including all zeros), show a flat line in middle
    const isFlat = range === 0;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Draw area fill
    ctx.beginPath();
    ctx.moveTo(0, height);
    
    sortedData.forEach((point, i) => {
      const x = (i / (sortedData.length - 1)) * width;
      const y = isFlat 
        ? height / 2  // Flat line in middle when all values are same
        : height - ((point.y - minY) / range) * height * 0.9 - height * 0.05;
      if (i === 0) {
        ctx.lineTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    
    ctx.lineTo(width, height);
    ctx.closePath();
    ctx.fillStyle = chartColor;
    ctx.fill();
    
    // Draw line
    ctx.beginPath();
    sortedData.forEach((point, i) => {
      const x = (i / (sortedData.length - 1)) * width;
      const y = isFlat 
        ? height / 2  // Flat line in middle when all values are same
        : height - ((point.y - minY) / range) * height * 0.9 - height * 0.05;
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.strokeStyle = chartColor.replace('0.3)', '0.6)');  // Darker line
    ctx.lineWidth = isFlat ? 2 : 1.5;  // Thicker line when flat for visibility
    ctx.stroke();
  }, [chartData, chartColor]);
  
  return (
    <Card
      className={cn(
        "transition-all hover:shadow-md",
        onClick && "cursor-pointer hover:scale-105",
        borderColor && `border-l-4 ${borderColor}`,
        className
      )}
      onClick={onClick}
    >
      <CardContent className="p-4 relative overflow-hidden">
        {/* Background sparkline chart */}
        {chartData && chartData.length >= 2 && (
          <canvas
            ref={canvasRef}
            className="absolute inset-0 pointer-events-none opacity-40"
            style={{ zIndex: 0 }}
          />
        )}
        
        {/* Content overlay */}
        <div className="relative z-10">
          {badge && (
            <div className="absolute top-3 right-3">
              {badge}
            </div>
          )}
          <div className="text-xs font-medium text-muted-foreground mb-1.5">{label}</div>
          <div className="text-2xl font-bold mb-1.5">{value}</div>
          {subtext && (
            <div className="text-sm text-muted-foreground space-y-1">
              {subtext}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
