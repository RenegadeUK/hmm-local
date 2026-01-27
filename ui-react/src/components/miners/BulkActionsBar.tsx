import { CheckCircle, XCircle, RefreshCw, Sliders, Network, X } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface BulkActionsBarProps {
  selectedCount: number;
  onClear: () => void;
  onEnable: () => void;
  onDisable: () => void;
  onRestart: () => void;
  onSetMode: () => void;
  onSwitchPool: () => void;
}

export default function BulkActionsBar({
  selectedCount,
  onClear,
  onEnable,
  onDisable,
  onRestart,
  onSetMode,
  onSwitchPool,
}: BulkActionsBarProps) {
  return (
    <Card className="bg-blue-500/5 border-blue-500/20">
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-1 h-8 bg-blue-500 rounded-full"></div>
            <p className="font-semibold">
              {selectedCount} miner{selectedCount !== 1 ? 's' : ''} selected
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={onEnable}
              className="gap-2"
            >
              <CheckCircle className="h-4 w-4" />
              Enable
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onDisable}
              className="gap-2"
            >
              <XCircle className="h-4 w-4" />
              Disable
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onSetMode}
              className="gap-2"
            >
              <Sliders className="h-4 w-4" />
              Set Mode
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onSwitchPool}
              className="gap-2"
            >
              <Network className="h-4 w-4" />
              Switch Pool
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onRestart}
              className="gap-2 text-orange-400 hover:text-orange-300 border-orange-500/20 hover:border-orange-500/40"
            >
              <RefreshCw className="h-4 w-4" />
              Restart
            </Button>
            <div className="w-px h-6 bg-gray-700"></div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClear}
              className="gap-2"
            >
              <X className="h-4 w-4" />
              Clear
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
