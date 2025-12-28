#!/usr/bin/env python3
"""
Test script to explore P2Pool API endpoints and response structure
"""
import asyncio
import aiohttp
import json

API_URL = "http://10.200.204.87:5000"  # Your P2Pool API

async def test_endpoint(endpoint, description):
    print(f"\n{'='*80}")
    print(f"Testing: {description}")
    print(f"Endpoint: {endpoint}")
    print('='*80)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}{endpoint}", timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✓ Status: {response.status}")
                    print(f"Response structure:")
                    print(json.dumps(data, indent=2))
                    
                    # If it's a log with lines, parse the JSON in lines
                    if data.get("success") and data.get("lines"):
                        print(f"\n📋 Found {len(data['lines'])} log lines")
                        for i, line in enumerate(data['lines'][:3], 1):  # First 3 lines
                            try:
                                parsed = json.loads(line)
                                print(f"\nLine {i} parsed structure:")
                                print(json.dumps(parsed, indent=2))
                            except:
                                print(f"\nLine {i} (raw): {line[:200]}")
                else:
                    print(f"✗ Status: {response.status}")
                    text = await response.text()
                    print(f"Response: {text[:500]}")
    except Exception as e:
        print(f"✗ Error: {e}")

async def main():
    print("P2Pool API Explorer")
    print("=" * 80)
    
    # Test known endpoints
    await test_endpoint("/api/status", "API Status/Health Check")
    await test_endpoint("/api/log/local/stratum/tail/1", "Local Stratum Stats (aggregate)")
    await test_endpoint("/api/log/local/stratum/tail/10", "Local Stratum Stats (last 10 lines)")
    await test_endpoint("/api/log/pool/stats/tail/1", "Pool Stats")
    await test_endpoint("/api/log/network/stats/tail/1", "Network Stats")
    
    # Try potential endpoints for connections
    await test_endpoint("/api/connections", "Active Connections")
    await test_endpoint("/api/stratum/connections", "Stratum Connections")
    await test_endpoint("/api/workers", "Workers")
    await test_endpoint("/api/miners", "Miners")
    
    # Try log file listing
    await test_endpoint("/api/logs", "List Available Logs")

if __name__ == "__main__":
    asyncio.run(main())
