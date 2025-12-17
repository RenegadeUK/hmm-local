# XMRig CPU Miner Setup Guide

This guide explains how to configure XMRig for use with Home Miner Manager.

## Prerequisites

- XMRig 6.x or later installed on your system
- XMRig running on a network-accessible machine

## Enable XMRig HTTP API

XMRig needs its HTTP API enabled for Home Miner Manager to collect telemetry and control the miner.

### Method 1: Configuration File (Recommended)

Edit your XMRig `config.json` file to include:

```json
{
    "api": {
        "id": null,
        "worker-id": "my-cpu-miner"
    },
    "http": {
        "enabled": true,
        "host": "0.0.0.0",
        "port": 8080,
        "access-token": null,
        "restricted": true
    },
    "pools": [
        {
            "url": "eu1.solopool.org:8010",
            "user": "YOUR_XMR_ADDRESS",
            "pass": "x",
            "keepalive": true,
            "tls": false
        }
    ]
}
```

**Configuration Options:**

- `worker-id`: Custom name for your miner (optional, defaults to hostname)
- `host`: Set to `0.0.0.0` to allow network access
- `port`: HTTP API port (default 8080)
- `access-token`: Optional authentication token (leave as `null` for no auth)
- `restricted`: `true` limits API to read-only operations (recommended)

### Method 2: Command Line Arguments

Start XMRig with these additional flags:

```bash
xmrig --http-enabled --http-host=0.0.0.0 --http-port=8080 --http-restricted
```

**For authenticated access (optional):**

```bash
xmrig --http-enabled --http-host=0.0.0.0 --http-port=8080 --http-access-token=YOUR_SECRET_TOKEN --http-restricted
```

## Security Considerations

### Restricted vs Non-Restricted Mode

- **Restricted Mode** (`--http-restricted` or `"restricted": true`):
  - **Recommended** for most users
  - Read-only API access
  - Can view stats but cannot change configuration
  - Cannot pause/resume/restart mining
  - Safe to expose on local network

- **Non-Restricted Mode**:
  - Full API access including configuration changes
  - Can pause/resume mining
  - Can switch pools
  - Can restart miner
  - **Should only be used if you trust all devices on your network**

### Access Token

If you want to add an extra layer of security:

1. Set an access token in your XMRig config:
   ```json
   "access-token": "your-secret-token-here"
   ```

2. When adding the miner to Home Miner Manager, include the token in the configuration

### Firewall

If XMRig is running on a different machine, ensure port 8080 (or your custom port) is open in the firewall:

**Linux (ufw):**
```bash
sudo ufw allow 8080/tcp
```

**Windows Firewall:**
- Open Windows Firewall
- Allow inbound TCP connections on port 8080

## Adding XMRig to Home Miner Manager

### Option 1: Network Discovery

1. Navigate to **Miners** → **Discover**
2. Enter your network range (e.g., `192.168.1.0/24`)
3. Click **Scan Network**
4. XMRig miners will appear in the results
5. Click **+ Add Miner** next to the discovered XMRig instance

### Option 2: Manual Entry

1. Navigate to **Miners** → **Add Miner**
2. Select **XMRig** as miner type
3. Enter:
   - **Name**: Custom name for your miner
   - **IP Address**: IP address where XMRig is running
   - **Port**: HTTP API port (default 8080)
   - **Access Token**: If you configured one (optional)

## Telemetry Data

Home Miner Manager will collect the following data from XMRig:

- **Hashrate**: Current, 1-minute, and 15-minute averages (displayed in GH/s for consistency)
- **Shares**: Accepted and rejected shares
- **Pool**: Currently connected pool
- **CPU**: CPU brand and thread count
- **Algorithm**: Mining algorithm (e.g., RandomX)
- **Uptime**: Miner uptime
- **Temperature**: CPU temperature (if available)
- **Version**: XMRig version

## Limitations

### Power Monitoring

XMRig does not report power consumption. CPU mining power usage varies widely based on:
- CPU model (50-150W typical)
- Number of threads used
- CPU frequency/voltage settings

You can manually estimate power usage or use a hardware power meter.

### Mode Control

Unlike ASIC miners, XMRig doesn't have preset "modes" (low/med/high). Mining intensity is controlled by:
- Number of CPU threads allocated
- CPU thread affinity settings
- These must be configured in the XMRig config file

### Pool Switching

**Restricted Mode**: Pool switching is disabled (read-only API)

**Non-Restricted Mode**: Pool switching is available via Home Miner Manager automation

## Troubleshooting

### Miner Not Discovered

1. **Check XMRig is running**:
   ```bash
   curl http://MINER_IP:8080/1/summary
   ```
   Should return JSON with miner stats

2. **Verify API is enabled**:
   Check XMRig console output for:
   ```
   * HTTP API started on 0.0.0.0:8080
   ```

3. **Check firewall**: Ensure port 8080 is accessible

4. **Verify network connectivity**: Ping the XMRig machine from the Home Miner Manager host

### No Telemetry Data

1. **Check access token**: If configured, ensure it matches in both XMRig and Home Miner Manager
2. **Check restricted mode**: Some features require non-restricted mode
3. **View logs**: Check Home Miner Manager logs for XMRig connection errors

### API Access Denied

If you get 401 Unauthorized errors:
- Your XMRig has an access token configured
- Add the token to the miner configuration in Home Miner Manager

## Example XMRig Configurations

### Minimal Configuration (Restricted API)

```json
{
    "http": {
        "enabled": true,
        "host": "0.0.0.0",
        "port": 8080,
        "restricted": true
    },
    "pools": [
        {
            "url": "eu1.solopool.org:8010",
            "user": "YOUR_XMR_ADDRESS",
            "pass": "x"
        }
    ]
}
```

### Full Configuration with Security

```json
{
    "api": {
        "id": null,
        "worker-id": "office-pc"
    },
    "http": {
        "enabled": true,
        "host": "0.0.0.0",
        "port": 8080,
        "access-token": "my-secret-token-12345",
        "restricted": false
    },
    "cpu": {
        "enabled": true,
        "huge-pages": true,
        "hw-aes": null,
        "priority": null,
        "asm": true,
        "max-threads-hint": 75
    },
    "pools": [
        {
            "url": "eu1.solopool.org:8010",
            "user": "YOUR_XMR_ADDRESS",
            "pass": "x",
            "keepalive": true,
            "tls": false
        }
    ]
}
```

## Further Reading

- [XMRig Official Documentation](https://xmrig.com/docs)
- [XMRig API Reference](https://xmrig.com/docs/miner/api)
- [XMRig Configuration Guide](https://xmrig.com/docs/miner/config)
