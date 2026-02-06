import React, { useState, useEffect } from 'react';
import { RefreshCw, Download, AlertCircle, CheckCircle, Package } from 'lucide-react';

interface DriverInfo {
  name: string;
  driver_type: string;
  display_name: string;
  current_version: string | null;
  available_version: string;
  status: 'up_to_date' | 'update_available' | 'not_installed';
  description: string | null;
}

const DriverUpdates: React.FC = () => {
  const [drivers, setDrivers] = useState<DriverInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [restartRequired, setRestartRequired] = useState(false);
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    fetchDriverStatus();
  }, []);

  const fetchDriverStatus = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/drivers/status');
      if (response.ok) {
        const data = await response.json();
        setDrivers(data);
      } else {
        throw new Error('Failed to fetch driver status');
      }
    } catch (error) {
      console.error('Error fetching driver status:', error);
      setMessage({ type: 'error', text: 'Failed to load driver information' });
    } finally {
      setLoading(false);
    }
  };

  const restartContainer = async () => {
    if (!confirm('Restart the container now? This will briefly interrupt service.')) {
      return;
    }

    try {
      setRestarting(true);
      const response = await fetch('/api/settings/restart', {
        method: 'POST'
      });

      if (response.ok) {
        setMessage({
          type: 'success',
          text: 'Container restart initiated. Page will reload in 10 seconds...'
        });
        
        // Wait 10 seconds then reload the page
        setTimeout(() => {
          window.location.reload();
        }, 10000);
      } else {
        throw new Error('Restart request failed');
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: `Failed to restart container: ${error.message}`
      });
      setRestarting(false);
    }
  };

  const updateDriver = async (driverName: string) => {
    try {
      setUpdating(driverName);
      setMessage(null);
      
      const response = await fetch(`/api/drivers/update/${driverName}`, {
        method: 'POST'
      });
      
      const result = await response.json();
      
      if (response.ok) {
        setMessage({
          type: 'success',
          text: `${driverName} updated successfully! Restart required to load new version.`
        });
        setRestartRequired(true);
        await fetchDriverStatus(); // Refresh list
      } else {
        throw new Error(result.detail || 'Update failed');
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: `Failed to update ${driverName}: ${error.message}`
      });
    } finally {
      setUpdating(null);
    }
  };

  const installDriver = async (driverName: string) => {
    try {
      setUpdating(driverName);
      setMessage(null);
      
      const response = await fetch(`/api/drivers/install/${driverName}`, {
        method: 'POST'
      });
      
      const result = await response.json();
      
      if (response.ok) {
        setMessage({
          type: 'success',
          text: `${driverName} installed successfully! Restart required to load driver.`
        });
        setRestartRequired(true);
        await fetchDriverStatus(); // Refresh list
      } else {
        throw new Error(result.detail || 'Installation failed');
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: `Failed to install ${driverName}: ${error.message}`
      });
    } finally {
      setUpdating(null);
    }
  };

  const updateAllDrivers = async () => {
    try {
      setUpdating('all');
      setMessage(null);
      
      const response = await fetch('/api/drivers/update-all', {
        method: 'POST'
      });
      
      const result = await response.json();
      
      if (response.ok) {
        const updateCount = result.updated.length;
        const failCount = result.failed.length;
        
        if (failCount > 0) {
          setMessage({
            type: 'error',
            text: `Updated ${updateCount} driver(s), but ${failCount} failed. Check logs for details.`
          });
        } else {
          setMessage({
            type: 'success',
            text: `Successfully updated ${updateCount} driver(s)! Restart required.`
          });
        }
        
        setRestartRequired(true);
        await fetchDriverStatus(); // Refresh list
      } else {
        throw new Error(result.detail || 'Update all failed');
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: `Failed to update drivers: ${error.message}`
      });
    } finally {
      setUpdating(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'up_to_date':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircle className="w-3 h-3 mr-1" />
            Up to Date
          </span>
        );
      case 'update_available':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
            <AlertCircle className="w-3 h-3 mr-1" />
            Update Available
          </span>
        );
      case 'not_installed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            <Package className="w-3 h-3 mr-1" />
            Not Installed
          </span>
        );
      default:
        return null;
    }
  };

  const updatesAvailable = drivers.filter(d => d.status === 'update_available').length;
  const notInstalled = drivers.filter(d => d.status === 'not_installed');
  const installed = drivers.filter(d => d.status !== 'not_installed');

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100">Pool Driver Management</h1>
        <p className="mt-1 text-sm text-gray-400">
          Manage pool driver versions and install new drivers
        </p>
      </div>

      {/* Message Banner */}
      {message && (
        <div className={`mb-6 p-4 rounded-md ${message.type === 'success' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <div className="flex">
            <div className="flex-shrink-0">
              {message.type === 'success' ? (
                <CheckCircle className="h-5 w-5 text-green-400" />
              ) : (
                <AlertCircle className="h-5 w-5 text-red-400" />
              )}
            </div>
            <div className="ml-3">
              <p className={`text-sm font-medium ${message.type === 'success' ? 'text-green-800' : 'text-red-800'}`}>
                {message.text}
              </p>
            </div>
            <div className="ml-auto pl-3">
              <button
                type="button"
                onClick={() => setMessage(null)}
                className="inline-flex rounded-md p-1.5 hover:bg-opacity-75 focus:outline-none"
              >
                <span className="sr-only">Dismiss</span>
                <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Restart Required Banner */}
      {restartRequired && (
        <div className="mb-6 p-4 rounded-md bg-yellow-900/40 border border-yellow-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <AlertCircle className="h-5 w-5 text-yellow-400 mr-3" />
              <div>
                <p className="text-sm font-medium text-yellow-200">
                  Container restart required to load updated drivers
                </p>
                <p className="text-xs text-yellow-300 mt-1">
                  You can restart now or manually restart the container later
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => setRestartRequired(false)}
                className="text-sm text-gray-400 hover:text-gray-300"
              >
                Ignore
              </button>
              <button
                onClick={restartContainer}
                disabled={restarting}
                className="inline-flex items-center px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-yellow-600 hover:bg-yellow-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-yellow-500 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 mr-2 ${restarting ? 'animate-spin' : ''}`} />
                {restarting ? 'Restarting...' : 'Restart Now'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Bar */}
      <div className="mb-6 flex items-center justify-between bg-gray-900/80 border border-gray-800 p-4 rounded-lg">
        <div className="flex items-center space-x-4">
          <button
            onClick={fetchDriverStatus}
            disabled={loading}
            className="inline-flex items-center px-4 py-2 border border-gray-700 rounded-md text-sm font-medium text-gray-300 bg-gray-800 hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          
          {updatesAvailable > 0 && (
            <button
              onClick={updateAllDrivers}
              disabled={updating !== null}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              <Download className={`w-4 h-4 mr-2 ${updating === 'all' ? 'animate-bounce' : ''}`} />
              Update All ({updatesAvailable})
            </button>
          )}
        </div>
        
        <div className="text-sm text-gray-500">
          {installed.length} installed • {notInstalled.length} available
        </div>
      </div>

      {/* Installed Drivers Table */}
      {installed.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Installed Drivers</h2>
          <div className="bg-gray-900/80 border border-gray-800 overflow-hidden rounded-lg">
            <table className="min-w-full divide-y divide-gray-800">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Driver
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Current Version
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Available Version
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="bg-gray-900/40 divide-y divide-gray-800">
                {installed.map((driver) => (
                  <tr key={driver.name}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <div className="text-sm font-medium text-gray-100">
                          {driver.display_name}
                        </div>
                        <div className="text-sm text-gray-400">{driver.name}</div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                      {driver.driver_type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-200">
                      {driver.current_version || 'unknown'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-200">
                      {driver.available_version}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getStatusBadge(driver.status)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      {driver.status === 'update_available' ? (
                        <button
                          onClick={() => updateDriver(driver.name)}
                          disabled={updating !== null}
                          className="text-blue-600 hover:text-blue-900 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {updating === driver.name ? 'Updating...' : 'Update'}
                        </button>
                      ) : (
                        <span className="text-gray-400">Up to date</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Available Drivers (Not Installed) */}
      {notInstalled.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Available Drivers</h2>
          <div className="bg-gray-900/80 border border-gray-800 overflow-hidden rounded-lg">
            <table className="min-w-full divide-y divide-gray-800">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Driver
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Version
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Description
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="bg-gray-900/40 divide-y divide-gray-800">
                {notInstalled.map((driver) => (
                  <tr key={driver.name}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <div className="text-sm font-medium text-gray-100">
                          {driver.display_name}
                        </div>
                        <div className="text-sm text-gray-400">{driver.name}</div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                      {driver.driver_type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-200">
                      {driver.available_version}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-400">
                      {driver.description || 'No description available'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button
                        onClick={() => installDriver(driver.name)}
                        disabled={updating !== null}
                        className="inline-flex items-center px-3 py-1 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {updating === driver.name ? (
                          <>
                            <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                            Installing...
                          </>
                        ) : (
                          <>
                            <Download className="w-4 h-4 mr-1" />
                            Install
                          </>
                        )}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Restart Notice */}
      {(message?.type === 'success') && (
        <div className="mt-6 bg-yellow-50 border-l-4 border-yellow-400 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <AlertCircle className="h-5 w-5 text-yellow-400" />
            </div>
            <div className="ml-3">
              <p className="text-sm text-yellow-700">
                <strong>Important:</strong> Container restart required for driver changes to take effect.
                Run: <code className="bg-yellow-100 px-2 py-1 rounded">docker-compose restart</code>
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DriverUpdates;
