// v0 Miner Controller - Main JavaScript

// Utility function for API calls
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`API call failed: ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API call error:', error);
        throw error;
    }
}

// Format hashrate with unit awareness
function formatHashrate(value, unit = 'GH/s') {
    if (!value) return '0.00 ' + unit;
    
    // Handle different units
    if (unit === 'KH/s') {
        // CPU miners - keep in KH/s
        return value.toFixed(2) + ' KH/s';
    } else if (unit === 'GH/s') {
        // ASIC miners - convert to TH/s if > 1000
        if (value >= 1000) {
            return (value / 1000).toFixed(2) + ' TH/s';
        }
        return value.toFixed(2) + ' GH/s';
    } else if (unit === 'TH/s') {
        return value.toFixed(2) + ' TH/s';
    }
    // Fallback
    return value.toFixed(2) + ' ' + unit;
}

// Format timestamp
function formatTimestamp(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString();
}

// Show notification (basic implementation)
function showNotification(message, type = 'info') {
    // TODO: Implement proper notification system
    console.log(`[${type}] ${message}`);
}

// WCAG AA - Announce status updates to screen readers
function announceStatus(message) {
    const announcer = document.getElementById('status-announcer');
    if (announcer) {
        announcer.textContent = message;
        // Clear after 1 second to allow repeated announcements
        setTimeout(() => {
            announcer.textContent = '';
        }, 1000);
    }
}

console.log('v0 Miner Controller initialized');
