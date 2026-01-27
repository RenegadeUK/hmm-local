import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface BulkPoolModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (poolId: number) => void;
}

interface Pool {
  id: number;
  name: string;
  url: string;
  port: number;
}

const API_BASE = 'http://10.200.204.22:8080';

export default function BulkPoolModal({ open, onClose, onSubmit }: BulkPoolModalProps) {
  const [selectedPoolId, setSelectedPoolId] = useState<string>('');

  // Fetch pools
  const { data: pools = [] } = useQuery<Pool[]>({
    queryKey: ['pools'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/pools`);
      if (!response.ok) throw new Error('Failed to fetch pools');
      return response.json();
    },
    enabled: open, // Only fetch when modal is open
  });

  const handleSubmit = () => {
    if (selectedPoolId) {
      onSubmit(parseInt(selectedPoolId));
      setSelectedPoolId('');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Switch Pool for Selected Miners</DialogTitle>
          <DialogDescription>
            Choose the mining pool to apply to all selected miners.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="pool">Mining Pool</Label>
            <Select value={selectedPoolId} onValueChange={setSelectedPoolId}>
              <SelectTrigger id="pool">
                <SelectValue placeholder="Select a pool..." />
              </SelectTrigger>
              <SelectContent>
                {pools.map((pool) => (
                  <SelectItem key={pool.id} value={pool.id.toString()}>
                    {pool.name} ({pool.url}:{pool.port})
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
          <Button onClick={handleSubmit} disabled={!selectedPoolId}>
            Switch Pool
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
