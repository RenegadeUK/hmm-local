import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { AlertCircle, Save, X } from 'lucide-react';

interface MinerUpdateData {
  name: string;
  ip_address: string;
  port: number;
  enabled: boolean;
  manual_power_watts?: number;
  config?: {
    admin_password?: string;
  };
}

export default function MinerEdit() {
  const { minerId } = useParams<{ minerId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [name, setName] = useState('');
  const [ipAddress, setIpAddress] = useState('');
  const [port, setPort] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [manualPowerWatts, setManualPowerWatts] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [hasStoredAdminPassword, setHasStoredAdminPassword] = useState(false);
  const [isChangingAdminPassword, setIsChangingAdminPassword] = useState(false);

  // Fetch full miner data (includes IP, port, config)
  const { data: miner, isLoading } = useQuery({
    queryKey: ['minerDetails', minerId],
    queryFn: async () => {
      const response = await fetch(`/api/miners/${minerId}`);
      if (!response.ok) throw new Error('Failed to fetch miner details');
      return response.json();
    },
    enabled: !!minerId,
  });

  // Initialize form fields when miner data is loaded
  useEffect(() => {
    if (miner) {
      setName(miner.name || '');
      setIpAddress(miner.ip_address || '');
      setPort(miner.port?.toString() || miner.effective_port?.toString() || '');
      setEnabled(miner.enabled ?? true);
      setManualPowerWatts(miner.manual_power_watts?.toString() || '');
      setAdminPassword('');
      setHasStoredAdminPassword(Boolean(miner.config?.admin_password));
      setIsChangingAdminPassword(false);
    }
  }, [miner]);

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async (data: MinerUpdateData) => {
      const response = await fetch(`/api/miners/${minerId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update miner');
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['miners'] });
      queryClient.invalidateQueries({ queryKey: ['telemetry', minerId] });
      navigate(`/miners/${minerId}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    const data: MinerUpdateData = {
      name,
      ip_address: ipAddress,
      port: parseInt(port),
      enabled,
    };

    // Add manual_power_watts if provided
    if (manualPowerWatts) {
      data.manual_power_watts = parseInt(manualPowerWatts);
    }

    // Add admin_password for Avalon Nano if provided
    if (miner?.miner_type === 'avalon_nano' && isChangingAdminPassword && adminPassword.trim()) {
      data.config = { admin_password: adminPassword.trim() };
    }

    updateMutation.mutate(data);
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-3 text-gray-400">
              <div className="animate-spin h-5 w-5 border-2 border-gray-400 border-t-transparent rounded-full"></div>
              <p>Loading miner data...</p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!miner) {
    return (
      <div className="p-6">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-3 text-red-400">
              <AlertCircle className="h-5 w-5" />
              <p>Miner not found</p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="max-w-2xl mx-auto">
        <Card>
          <CardHeader>
            <h2 className="text-xl font-semibold">Edit Miner</h2>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Name */}
              <div className="space-y-2">
                <Label htmlFor="name">Miner Name</Label>
                <input
                  type="text"
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-sm text-gray-400">Friendly name for this miner</p>
              </div>

              {/* Miner Type (read-only) */}
              <div className="space-y-2">
                <Label htmlFor="miner-type">Miner Type</Label>
                <input
                  type="text"
                  id="miner-type"
                  value={miner.miner_type}
                  disabled
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-gray-500 cursor-not-allowed"
                />
                <p className="text-sm text-gray-400">Miner type cannot be changed</p>
              </div>

              {/* IP Address */}
              <div className="space-y-2">
                <Label htmlFor="ip-address">IP Address</Label>
                <input
                  type="text"
                  id="ip-address"
                  value={ipAddress}
                  onChange={(e) => setIpAddress(e.target.value)}
                  required
                  pattern="^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Port */}
              <div className="space-y-2">
                <Label htmlFor="port">Port</Label>
                <input
                  type="number"
                  id="port"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  required
                  min="1"
                  max="65535"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Status */}
              <div className="space-y-2">
                <Label htmlFor="enabled">Status</Label>
                <select
                  id="enabled"
                  value={enabled.toString()}
                  onChange={(e) => setEnabled(e.target.value === 'true')}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
                <p className="text-sm text-gray-400">Disabled miners are not monitored</p>
              </div>

              {/* Manual Power Watts */}
              <div className="space-y-2">
                <Label htmlFor="manual-power-watts">Estimated Power Usage (W)</Label>
                <input
                  type="number"
                  id="manual-power-watts"
                  value={manualPowerWatts}
                  onChange={(e) => setManualPowerWatts(e.target.value)}
                  min="1"
                  max="5000"
                  placeholder="e.g., 75"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-sm text-gray-400">
                  Optional: For miners without auto-detection. Leave blank if power is auto-detected.
                </p>
              </div>

              {/* Avalon Nano Admin Password */}
              {miner.miner_type === 'avalon_nano' && (
                <div className="space-y-2">
                  <Label htmlFor="admin-password">Avalon Nano Admin Password</Label>
                  {hasStoredAdminPassword && !isChangingAdminPassword ? (
                    <div className="space-y-2 rounded-lg border border-gray-700 bg-gray-900/60 px-3 py-3">
                      <p className="text-sm text-gray-200">Stored admin password is configured.</p>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => setIsChangingAdminPassword(true)}
                      >
                        Change password
                      </Button>
                    </div>
                  ) : (
                    <>
                      <input
                        type="password"
                        id="admin-password"
                        value={adminPassword}
                        onChange={(e) => setAdminPassword(e.target.value)}
                        placeholder={hasStoredAdminPassword ? 'Enter new password' : "Default is 'admin'"}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm text-gray-400">
                          {hasStoredAdminPassword
                            ? 'Leave blank to keep the current password unchanged.'
                            : 'Set this to enable remote pool configuration for Avalon Nano.'}
                        </p>
                        {hasStoredAdminPassword && isChangingAdminPassword && (
                          <button
                            type="button"
                            className="text-xs text-gray-400 underline-offset-4 hover:underline"
                            onClick={() => {
                              setIsChangingAdminPassword(false)
                              setAdminPassword('')
                            }}
                          >
                            Keep existing password
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Error Message */}
              {updateMutation.isError && (
                <div className="flex items-center gap-3 text-red-400 p-4 bg-red-500/10 rounded-lg border border-red-500/20">
                  <AlertCircle className="h-5 w-5 flex-shrink-0" />
                  <p className="text-sm">
                    {updateMutation.error instanceof Error
                      ? updateMutation.error.message
                      : 'Failed to update miner'}
                  </p>
                </div>
              )}

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <Button
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="flex items-center gap-2"
                >
                  <Save className="h-4 w-4" />
                  {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => navigate(`/miners/${minerId}`)}
                  className="flex items-center gap-2"
                >
                  <X className="h-4 w-4" />
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
