#!/usr/bin/env python3
"""
Test Home Assistant Integration
Run this script to test Home Assistant connectivity and device control

Usage:
    python test_ha_integration.py
    
Before running:
    1. Edit HA_BASE_URL and HA_TOKEN below
    2. Edit TEST_ENTITY_ID to match one of your switches
"""
import asyncio
import logging
from app.integrations.homeassistant import HomeAssistantIntegration

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION - EDIT THESE VALUES
# ============================================================================

# Your Home Assistant URL (include http:// or https://)
HA_BASE_URL = "http://homeassistant.local:8123"

# Your Home Assistant Long-Lived Access Token
# Get from: Profile → Long-Lived Access Tokens → Create Token
HA_TOKEN = "your_token_here"

# Test entity ID (e.g., switch, light, or plug)
TEST_ENTITY_ID = "switch.miner_power"  # Change to your entity

# ============================================================================


async def test_connection():
    """Test 1: Verify we can connect to Home Assistant"""
    print("\n" + "="*80)
    print("TEST 1: Connection Test")
    print("="*80)
    
    ha = HomeAssistantIntegration(HA_BASE_URL, HA_TOKEN)
    
    if await ha.test_connection():
        print("✅ Successfully connected to Home Assistant!")
        return ha
    else:
        print("❌ Failed to connect to Home Assistant")
        print("\nTroubleshooting:")
        print("  1. Check HA_BASE_URL is correct")
        print("  2. Check HA_TOKEN is valid")
        print("  3. Check Home Assistant is running")
        print("  4. Check network connectivity")
        return None


async def test_discovery(ha):
    """Test 2: Discover devices"""
    print("\n" + "="*80)
    print("TEST 2: Device Discovery")
    print("="*80)
    
    # Discover all switches
    print("\n📍 Discovering switches...")
    switches = await ha.discover_devices(domain="switch")
    
    if switches:
        print(f"✅ Found {len(switches)} switches:")
        for device in switches[:10]:  # Show first 10
            print(f"  • {device.entity_id}")
            print(f"    Name: {device.name}")
            print(f"    Capabilities: {', '.join(device.capabilities)}")
    else:
        print("⚠️  No switches found")
    
    # Discover all lights
    print("\n💡 Discovering lights...")
    lights = await ha.discover_devices(domain="light")
    
    if lights:
        print(f"✅ Found {len(lights)} lights:")
        for device in lights[:5]:  # Show first 5
            print(f"  • {device.entity_id} - {device.name}")
    else:
        print("⚠️  No lights found")
    
    # Show all domains available
    print("\n🏠 Discovering all devices...")
    all_devices = await ha.discover_devices()
    domains = {}
    for device in all_devices:
        domains[device.domain] = domains.get(device.domain, 0) + 1
    
    print(f"✅ Found {len(all_devices)} total devices across {len(domains)} domains:")
    for domain, count in sorted(domains.items()):
        print(f"  • {domain}: {count} entities")


async def test_get_state(ha):
    """Test 3: Get device state"""
    print("\n" + "="*80)
    print("TEST 3: Get Device State")
    print("="*80)
    
    print(f"\n🔍 Getting state of: {TEST_ENTITY_ID}")
    state = await ha.get_device_state(TEST_ENTITY_ID)
    
    if state:
        print(f"✅ Current state:")
        print(f"  Entity ID: {state.entity_id}")
        print(f"  Name: {state.name}")
        print(f"  State: {state.state}")
        print(f"  Last Updated: {state.last_updated}")
        print(f"  Attributes: {state.attributes}")
        return state
    else:
        print(f"❌ Failed to get state for {TEST_ENTITY_ID}")
        print("\nTroubleshooting:")
        print(f"  1. Check entity ID '{TEST_ENTITY_ID}' exists in Home Assistant")
        print("  2. Run TEST 2 (discovery) to see available entities")
        return None


async def test_control(ha, current_state):
    """Test 4: Control device (turn on/off)"""
    print("\n" + "="*80)
    print("TEST 4: Device Control")
    print("="*80)
    
    if not current_state:
        print("⚠️  Skipping control test (no current state)")
        return
    
    # Determine action based on current state
    if current_state.state == "on":
        print(f"\n🔴 Device is ON, turning OFF...")
        success = await ha.turn_off(TEST_ENTITY_ID)
        new_action = "off"
    else:
        print(f"\n🟢 Device is OFF, turning ON...")
        success = await ha.turn_on(TEST_ENTITY_ID)
        new_action = "on"
    
    if success:
        print(f"✅ Successfully turned {new_action}!")
        
        # Wait a moment for state to update
        await asyncio.sleep(1)
        
        # Verify new state
        new_state = await ha.get_device_state(TEST_ENTITY_ID)
        if new_state:
            print(f"📊 New state: {new_state.state}")
            
            # Revert to original state
            print(f"\n🔄 Reverting to original state ({current_state.state})...")
            if current_state.state == "on":
                await ha.turn_on(TEST_ENTITY_ID)
            else:
                await ha.turn_off(TEST_ENTITY_ID)
            print("✅ Reverted")
    else:
        print(f"❌ Failed to turn {new_action}")


async def test_service_call(ha):
    """Test 5: Advanced service call"""
    print("\n" + "="*80)
    print("TEST 5: Advanced Service Call")
    print("="*80)
    
    # Example: Call a custom service
    print("\n🔧 Testing direct service call...")
    domain = TEST_ENTITY_ID.split(".")[0]
    success = await ha.call_service(
        domain=domain,
        service="turn_on",
        entity_id=TEST_ENTITY_ID
    )
    
    if success:
        print("✅ Service call successful")
    else:
        print("❌ Service call failed")


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("HOME ASSISTANT INTEGRATION TEST SUITE")
    print("="*80)
    print(f"Base URL: {HA_BASE_URL}")
    print(f"Test Entity: {TEST_ENTITY_ID}")
    
    # Check configuration
    if HA_TOKEN == "your_token_here":
        print("\n❌ ERROR: Please edit test_ha_integration.py and set:")
        print("  - HA_BASE_URL (your Home Assistant URL)")
        print("  - HA_TOKEN (your Long-Lived Access Token)")
        print("  - TEST_ENTITY_ID (an entity to test with)")
        return
    
    # Run tests
    ha = await test_connection()
    if not ha:
        return
    
    await test_discovery(ha)
    current_state = await test_get_state(ha)
    await test_control(ha, current_state)
    await test_service_call(ha)
    
    print("\n" + "="*80)
    print("✅ ALL TESTS COMPLETE")
    print("="*80)
    print("\nNext steps:")
    print("  1. Review the output above")
    print("  2. Verify device control worked as expected")
    print("  3. Ready to integrate into HMM automation!")


if __name__ == "__main__":
    asyncio.run(main())
