import React, { useState, useEffect } from 'react';
import { RefreshCw, Download, AlertTriangle, CheckCircle, Info, ExternalLink } from 'lucide-react';

interface ContainerInfo {
  id: string;
  name: string;
  image: string;
  network_mode: string;
  ip_address: string;
  restart_policy: string;
}

interface VersionInfo {
  current_image: string;
  current_tag: string;
  current_commit: string | null;
  current_message: string | null;
  current_date: string | null;
  latest_commit: string;
  latest_tag: string;
  latest_message: string;
  latest_date: string;
  latest_image: string;
  update_available: boolean;
  commits_behind: number;
}

interface CommitInfo {
  sha: string;
  sha_short: string;
  message: string;
  author: string;
  date: string;
  url: string;
}

interface UpdateStatus {
  status: 'idle' | 'checking' | 'pulling' | 'stopping' | 'starting' | 'completed' | 'error';
  message: string;
  progress: number;
  error: string | null;
}

interface UpdaterHealth {
  status: 'healthy' | 'unhealthy' | 'unknown';
  service: string;
  timestamp: string | null;
  error: string | null;
}

const PlatformUpdates: React.FC = () => {
  const [containerInfo, setContainerInfo] = useState<ContainerInfo | null>(null);
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [changelog, setChangelog] = useState<CommitInfo[]>([]);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [updaterHealth, setUpdaterHealth] = useState<UpdaterHealth>({ status: 'unknown', service: '', timestamp: null, error: null });
  const [loading, setLoading] = useState(true);
  const [showConfirm, setShowConfirm] = useState(false);
  const [pollingInterval, setPollingInterval] = useState<number | null>(null);

  const fetchContainerInfo = async () => {
    try {
      const response = await fetch('/api/updates/container');
      if (response.ok) {
        const data = await response.json();
        setContainerInfo(data);
      }
    } catch (error) {
      console.error('Failed to fetch container info:', error);
    }
  };

  const fetchVersionInfo = async () => {
    try {
      const response = await fetch('/api/updates/check');
      if (response.ok) {
        const data = await response.json();
        setVersionInfo(data);
      }
    } catch (error) {
      console.error('Failed to fetch version info:', error);
    }
  };

  const fetchChangelog = async () => {
    try {
      const response = await fetch('/api/updates/changelog');
      if (response.ok) {
        const data = await response.json();
        setChangelog(data);
      }
    } catch (error) {
      console.error('Failed to fetch changelog:', error);
    }
  };

  const fetchUpdaterHealth = async () => {
    try {
      const response = await fetch('/api/updates/updater-health');
      if (response.ok) {
        const data = await response.json();
        setUpdaterHealth({
          status: 'healthy',
          service: data.service || 'hmm-local-updater',
          timestamp: data.timestamp,
          error: null
        });
      } else {
        const error = await response.json();
        setUpdaterHealth({
          status: 'unhealthy',
          service: 'hmm-local-updater',
          timestamp: null,
          error: error.detail || 'Connection failed'
        });
      }
    } catch (error) {
      setUpdaterHealth({
        status: 'unhealthy',
        service: 'hmm-local-updater',
        timestamp: null,
        error: error instanceof Error ? error.message : 'Connection failed'
      });
    }
  };

  const fetchUpdateStatus = async () => {
    try {
      const response = await fetch('/api/updates/status');
      if (response.ok) {
        const data = await response.json();
        setUpdateStatus(data);
        
        // If update completed successfully or hit restarting status, start checking for container availability
        if (data.status === 'restarting' || data.status === 'success' || (data.progress >= 60 && data.message.includes('restart'))) {
          // Container is restarting - start checking if it's back online
          startContainerHealthCheck();
          return false; // Stop status polling, switch to health check
        }
        
        // If update is in progress, continue polling
        if (data.status !== 'idle' && data.status !== 'completed' && data.status !== 'error') {
          return true;
        } else if (data.status === 'completed' || data.status === 'error') {
          // Stop polling, refresh info
          setTimeout(() => {
            fetchContainerInfo();
            fetchVersionInfo();
            fetchChangelog();
          }, 2000);
          return false;
        }
      }
      return false;
    } catch (error) {
      console.error('Failed to fetch update status:', error);
      return false;
    }
  };

  const startContainerHealthCheck = () => {
    console.log('🔄 Starting container health check...');
    
    // Show restarting message
    setUpdateStatus(prev => prev ? {
      ...prev,
      status: 'starting',
      message: 'Container restarting... Checking health...',
      progress: 70
    } : null);

    let attempts = 0;
    const maxAttempts = 60; // 60 seconds max (increased for production)
    
    const checkHealth = setInterval(async () => {
      attempts++;
      
      // Update progress every few seconds
      if (attempts % 5 === 0) {
        const progressPercent = Math.min(70 + (attempts / maxAttempts) * 25, 95);
        setUpdateStatus(prev => prev ? {
          ...prev,
          message: `Container restarting... (${attempts}s)`,
          progress: progressPercent
        } : null);
      }
      
      try {
        // Use health endpoint with timestamp to prevent caching
        const timestamp = Date.now();
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000); // 2 second timeout per request
        
        const response = await fetch(`/health?t=${timestamp}`, {
          method: 'GET',
          cache: 'no-cache',
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (response.ok) {
          console.log('✅ Container is healthy! Redirecting to home...');
          clearInterval(checkHealth);
          
          // Show success message briefly
          setUpdateStatus({
            status: 'completed',
            message: 'Update completed successfully! Redirecting...',
            progress: 100,
            error: null
          });
          
          // Redirect to home page with full reload to ensure new version loads
          setTimeout(() => {
            window.location.href = '/';
          }, 1500);
        } else {
          console.log(`⏳ Health check attempt ${attempts}: not ready yet (status ${response.status})`);
        }
      } catch (error) {
        // Container not ready yet, keep checking
        console.log(`⏳ Health check attempt ${attempts}: ${error instanceof Error ? error.message : 'connection failed'}`);
        
        if (attempts >= maxAttempts) {
          console.error('❌ Container health check timed out');
          clearInterval(checkHealth);
          setUpdateStatus({
            status: 'error',
            message: 'Container restart is taking longer than expected. Redirecting to home...',
            progress: 95,
            error: 'Timeout waiting for container'
          });
          
          // Try redirecting to home after showing error
          setTimeout(() => {
            console.log('🔄 Redirecting to home page...');
            window.location.href = '/';
          }, 3000);
        }
      }
    }, 1000); // Check every second
  };

  const startPolling = () => {
    if (pollingInterval) return; // Already polling
    
    const interval = setInterval(async () => {
      const shouldContinue = await fetchUpdateStatus();
      if (!shouldContinue) {
        clearInterval(interval);
        setPollingInterval(null);
      }
    }, 2000);
    
    setPollingInterval(interval);
  };

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        fetchContainerInfo(),
        fetchVersionInfo(),
        fetchChangelog(),
        fetchUpdateStatus(),
        fetchUpdaterHealth()
      ]);
      setLoading(false);
    };
    
    loadData();
    
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, []);

  const handleRefresh = async () => {
    setLoading(true);
    
    // Trigger immediate GitHub cache refresh
    try {
      await fetch('/api/updates/refresh', { method: 'POST' });
    } catch (error) {
      console.error('Failed to refresh GitHub cache:', error);
    }
    
    // Wait a moment for cache to update, then fetch
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    await Promise.all([
      fetchVersionInfo(),
      fetchChangelog()
    ]);
    setLoading(false);
  };

  const handleUpdate = async () => {
    try {
      const response = await fetch('/api/updates/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (response.ok) {
        setShowConfirm(false);
        startPolling();
      } else {
        const error = await response.json();
        alert(`Update failed: ${error.detail}`);
      }
    } catch (error) {
      console.error('Failed to start update:', error);
      alert('Failed to start update');
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    return date.toLocaleString('en-GB', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-400';
      case 'error': return 'text-red-400';
      case 'checking':
      case 'pulling':
      case 'stopping':
      case 'starting': return 'text-yellow-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-5 h-5" />;
      case 'error': return <AlertTriangle className="w-5 h-5" />;
      default: return <RefreshCw className="w-5 h-5 animate-spin" />;
    }
  };

  if (loading && !versionInfo) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-900">
        <RefreshCw className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100">
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold mb-2">Platform Updates</h1>
            <p className="text-gray-400">Manage system updates from GitHub Container Registry</p>
            
            {/* Updater Service Status */}
            <div className="mt-3 flex items-center gap-2">
              <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm ${
                updaterHealth.status === 'healthy' 
                  ? 'bg-green-900 bg-opacity-30 text-green-400 border border-green-600' 
                  : updaterHealth.status === 'unhealthy'
                  ? 'bg-red-900 bg-opacity-30 text-red-400 border border-red-600'
                  : 'bg-gray-800 text-gray-400 border border-gray-600'
              }`}>
                {updaterHealth.status === 'healthy' && <CheckCircle className="w-4 h-4" />}
                {updaterHealth.status === 'unhealthy' && <AlertTriangle className="w-4 h-4" />}
                {updaterHealth.status === 'unknown' && <Info className="w-4 h-4" />}
                <span>
                  {updaterHealth.status === 'healthy' && 'Updater Connected'}
                  {updaterHealth.status === 'unhealthy' && 'Updater Disconnected'}
                  {updaterHealth.status === 'unknown' && 'Checking updater...'}
                </span>
              </div>
              {updaterHealth.error && (
                <span className="text-xs text-red-400">({updaterHealth.error})</span>
              )}
            </div>
          </div>
          <button
            onClick={handleRefresh}
            disabled={loading || updateStatus?.status !== 'idle'}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Deployment Requirements Warning */}
        {updateStatus && updateStatus.error && updateStatus.error.includes('docker.sock') && (
          <div className="bg-yellow-900 bg-opacity-30 border-2 border-yellow-600 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2 text-yellow-400">
              <AlertTriangle className="w-5 h-5" />
              Docker Socket Not Mounted
            </h2>
            <p className="text-gray-300 mb-4">
              Platform Updates requires access to the Docker socket. Add this to your deployment:
            </p>
            <div className="bg-gray-900 rounded p-4 font-mono text-sm overflow-x-auto">
              <div className="text-gray-400 mb-2"># For docker run:</div>
              <div className="text-green-400">-v /var/run/docker.sock:/var/run/docker.sock</div>
              <div className="mt-4 text-gray-400 mb-2"># Complete example:</div>
              <div className="text-gray-300">
                docker run -d \<br/>
                &nbsp;&nbsp;--name hmm-local \<br/>
                &nbsp;&nbsp;--network bridge \<br/>
                &nbsp;&nbsp;-p 8080:8080 \<br/>
                &nbsp;&nbsp;-v /data/hmm-local:/config \<br/>
                &nbsp;&nbsp;<span className="text-green-400">-v /var/run/docker.sock:/var/run/docker.sock \</span><br/>
                &nbsp;&nbsp;--restart unless-stopped \<br/>
                &nbsp;&nbsp;ghcr.io/renegadeuk/hmm-local:latest
              </div>
            </div>
            <p className="text-yellow-200 text-sm mt-4">
              ⚠️ After adding the Docker socket, restart your container for Platform Updates to work.
            </p>
          </div>
        )}

        {/* Container Info */}
        {containerInfo && (
          <div className="bg-gray-800 rounded-lg p-6 mb-6 border border-gray-700">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <Info className="w-5 h-5 text-purple-500" />
              Container Information
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <span className="text-gray-400">Container Name:</span>
                <span className="ml-2 font-mono">{containerInfo.name}</span>
              </div>
              <div>
                <span className="text-gray-400">Image:</span>
                <span className="ml-2 font-mono">{containerInfo.image}</span>
              </div>
              <div>
                <span className="text-gray-400">Network:</span>
                <span className="ml-2 font-mono">{containerInfo.network_mode}</span>
              </div>
              <div>
                <span className="text-gray-400">IP Address:</span>
                <span className="ml-2 font-mono">{containerInfo.ip_address}</span>
              </div>
            </div>
          </div>
        )}
        
        {/* Container Info Warning - Docker socket not mounted */}
        {!containerInfo && versionInfo && (
          <div className="bg-yellow-900/30 border border-yellow-600/50 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-3 flex items-center gap-2 text-yellow-500">
              <Info className="w-5 h-5" />
              Container Information Unavailable
            </h2>
            <p className="text-gray-300 mb-3">
              Docker socket is not mounted. To enable full container detection, add this to your deployment:
            </p>
            <div className="bg-gray-900 rounded p-3 font-mono text-sm text-gray-300 overflow-x-auto">
              -v /var/run/docker.sock:/var/run/docker.sock
            </div>
            <p className="text-gray-400 text-sm mt-3">
              Without the socket, Platform Updates can still check for new versions but cannot detect the current container's metadata.
            </p>
          </div>
        )}

        {/* Update Status Banner */}
        {updateStatus && updateStatus.status !== 'idle' && (
          <div className={`bg-gray-800 rounded-lg p-6 mb-6 border-2 ${
            updateStatus.status === 'completed' ? 'border-green-600' :
            updateStatus.status === 'error' ? 'border-red-600' : 'border-yellow-600'
          }`}>
            <div className="flex items-center gap-4 mb-4">
              <div className={getStatusColor(updateStatus.status)}>
                {getStatusIcon(updateStatus.status)}
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold capitalize">{updateStatus.status}</h3>
                <p className="text-gray-400">{updateStatus.message}</p>
                {updateStatus.error && (
                  <p className="text-red-400 text-sm mt-1">{updateStatus.error}</p>
                )}
              </div>
              <div className="text-2xl font-bold">{updateStatus.progress}%</div>
            </div>
            {updateStatus.status !== 'completed' && updateStatus.status !== 'error' && (
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div
                  className="bg-purple-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${updateStatus.progress}%` }}
                />
              </div>
            )}
          </div>
        )}

        {/* Version Comparison */}
        {versionInfo && (
          <div className="bg-gray-800 rounded-lg p-6 mb-6 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Version Information</h2>
              {versionInfo.update_available && (
                <span className="px-3 py-1 bg-yellow-600 text-white rounded-full text-sm font-semibold">
                  Update Available ({versionInfo.commits_behind} commits behind)
                </span>
              )}
              {!versionInfo.update_available && (
                <span className="px-3 py-1 bg-green-600 text-white rounded-full text-sm font-semibold flex items-center gap-1">
                  <CheckCircle className="w-4 h-4" />
                  Up to Date
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Current Version */}
              <div className="bg-gray-900 rounded-lg p-4">
                <h3 className="text-lg font-semibold text-gray-400 mb-3">Current Version</h3>
                <div className="space-y-2">
                  <div>
                    <span className="text-gray-500 text-sm">Image:</span>
                    <p className="font-mono text-sm">{versionInfo.current_image}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 text-sm">Tag:</span>
                    <p className="font-mono">{versionInfo.current_tag}</p>
                  </div>
                  {versionInfo.current_commit && (
                    <>
                      <div>
                        <span className="text-gray-500 text-sm">Commit:</span>
                        <p className="font-mono text-sm">{versionInfo.current_commit.substring(0, 7)}</p>
                      </div>
                      {versionInfo.current_message && (
                        <div>
                          <span className="text-gray-500 text-sm">Message:</span>
                          <p className="text-sm">{versionInfo.current_message}</p>
                        </div>
                      )}
                      {versionInfo.current_date && (
                        <div>
                          <span className="text-gray-500 text-sm">Date:</span>
                          <p className="text-sm">{formatDate(versionInfo.current_date)}</p>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* Latest Version */}
              <div className="bg-gray-900 rounded-lg p-4 border-2 border-purple-600">
                <h3 className="text-lg font-semibold text-purple-400 mb-3">Latest Version</h3>
                <div className="space-y-2">
                  <div>
                    <span className="text-gray-500 text-sm">Image:</span>
                    <p className="font-mono text-sm">{versionInfo.latest_image}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 text-sm">Tag:</span>
                    <p className="font-mono">{versionInfo.latest_tag}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 text-sm">Commit:</span>
                    <p className="font-mono text-sm">{versionInfo.latest_commit.substring(0, 7)}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 text-sm">Message:</span>
                    <p className="text-sm">{versionInfo.latest_message}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 text-sm">Date:</span>
                    <p className="text-sm">{formatDate(versionInfo.latest_date)}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Update Button */}
            {versionInfo.update_available && updateStatus?.status === 'idle' && (
              <div className="mt-6">
                <button
                  onClick={() => setShowConfirm(true)}
                  className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 rounded-lg font-semibold transition-colors"
                >
                  <Download className="w-5 h-5" />
                  Update to {versionInfo.latest_tag}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Changelog */}
        {changelog.length > 0 && (
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h2 className="text-xl font-semibold mb-4">Recent Commits</h2>
            <div className="space-y-3">
              {changelog.slice(0, 10).map((commit) => (
                <div
                  key={commit.sha}
                  className="bg-gray-900 rounded-lg p-4 hover:bg-gray-850 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <p className="font-semibold mb-1">{commit.message}</p>
                      <div className="flex items-center gap-4 text-sm text-gray-400">
                        <span className="font-mono">{commit.sha_short}</span>
                        <span>{commit.author}</span>
                        <span>{formatDate(commit.date)}</span>
                      </div>
                    </div>
                    <a
                      href={commit.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-purple-500 hover:text-purple-400 transition-colors"
                      title="View on GitHub"
                    >
                      <ExternalLink className="w-5 h-5" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Confirmation Dialog */}
      {showConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full border border-gray-700">
            <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <AlertTriangle className="w-6 h-6 text-yellow-500" />
              Confirm Update
            </h3>
            <div className="mb-6 space-y-3">
              <p className="text-gray-300">
                This will update the system to the latest version from GitHub Container Registry.
              </p>
              <div className="bg-gray-900 rounded p-3 space-y-1 text-sm">
                <p><span className="text-gray-400">From:</span> <span className="font-mono">{versionInfo?.current_tag}</span></p>
                <p><span className="text-gray-400">To:</span> <span className="font-mono text-purple-400">{versionInfo?.latest_tag}</span></p>
              </div>
              <div className="bg-yellow-900 bg-opacity-30 border border-yellow-600 rounded p-3">
                <p className="text-yellow-200 text-sm">
                  ⚠️ The container will restart during the update. Your network settings and configuration will be preserved.
                </p>
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirm(false)}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleUpdate}
                className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg font-semibold transition-colors"
              >
                Confirm Update
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PlatformUpdates;
