import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface BulkModeModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (mode: string) => void;
}

const MODES = [
  { value: 'low', label: 'Low Power' },
  { value: 'med', label: 'Medium Power' },
  { value: 'high', label: 'High Power' },
  { value: 'eco', label: 'Eco' },
  { value: 'standard', label: 'Standard' },
  { value: 'turbo', label: 'Turbo' },
  { value: 'oc', label: 'Overclock' },
];

export default function BulkModeModal({ open, onClose, onSubmit }: BulkModeModalProps) {
  const [selectedMode, setSelectedMode] = useState<string>('');

  const handleSubmit = () => {
    if (selectedMode) {
      onSubmit(selectedMode);
      setSelectedMode('');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Set Mode for Selected Miners</DialogTitle>
          <DialogDescription>
            Choose the operating mode to apply to all selected miners. Note: Not all modes are supported by all miner types.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="mode">Operating Mode</Label>
            <Select value={selectedMode} onValueChange={setSelectedMode}>
              <SelectTrigger id="mode">
                <SelectValue placeholder="Select a mode..." />
              </SelectTrigger>
              <SelectContent>
                {MODES.map((mode) => (
                  <SelectItem key={mode.value} value={mode.value}>
                    {mode.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!selectedMode}>
            Apply Mode
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
