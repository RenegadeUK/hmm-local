"""
Agile Mining Strategy - Core Logic Engine
Dynamic mining strategy optimised for Octopus Agile UK pricing
Supports both solo and pooled mining options
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import logging
import asyncio

from core.database import AgileStrategy, MinerStrategy, Miner, Pool, EnergyPrice, Telemetry, AgileStrategyBand, HomeAssistantConfig, HomeAssistantDevice
from core.energy import get_current_energy_price
from core.audit import log_audit
from core.solopool import SolopoolService
from core.agile_bands import ensure_strategy_bands, get_strategy_bands, get_band_for_price

logger = logging.getLogger(__name__)


class AgileSoloStrategy:
    """Agile Solo Strategy execution engine"""
    
    # Hysteresis counter requirement for upgrading bands
    HYSTERESIS_SLOTS = 2
    
    @staticmethod
    async def control_ha_device_for_miner(db: AsyncSession, miner: Miner, turn_on: bool) -> bool:
        """
        Control Home Assistant device linked to a miner
        
        Args:
            db: Database session
            miner: Miner object
            turn_on: True to turn on, False to turn off
            
        Returns:
            True if device was controlled, False if no device linked or control failed
        """
        try:
            # Check if miner has a linked HA device
            result = await db.execute(
                select(HomeAssistantDevice)
                .where(HomeAssistantDevice.miner_id == miner.id)
                .where(HomeAssistantDevice.enrolled == True)
            )
            ha_device = result.scalar_one_or_none()
            
            if not ha_device:
                logger.debug(f"No HA device linked to miner {miner.name}")
                return False
            
            # Get HA config
            config_result = await db.execute(select(HomeAssistantConfig))
            ha_config = config_result.scalar_one_or_none()
            
            if not ha_config or not ha_config.enabled:
                logger.warning(f"HA integration not configured or disabled, cannot control device for {miner.name}")
                return False
            
            # Import here to avoid circular dependencies
            from integrations.homeassistant import HomeAssistantIntegration
            
            # Create HA integration instance
            ha_integration = HomeAssistantIntegration(
                base_url=ha_config.base_url,
                access_token=ha_config.access_token
            )
            
            # Check current state before sending command (optimization)
            current_state = await ha_integration.get_device_state(ha_device.entity_id)
            desired_state = "on" if turn_on else "off"
            
            if current_state and current_state.state == desired_state:
                logger.debug(f"⏭️ HA device {ha_device.name} already {desired_state.upper()} for miner {miner.name} - skipping")
                return True  # Already in desired state, no action needed
            
            # Control device
            action = "turn_on" if turn_on else "turn_off"
            logger.info(f"HA: {action} device {ha_device.name} for miner {miner.name}")
            
            if turn_on:
                success = await ha_integration.turn_on(ha_device.entity_id)
            else:
                success = await ha_integration.turn_off(ha_device.entity_id)
            
            if success:
                logger.info(f"✓ HA device {ha_device.name} {'ON' if turn_on else 'OFF'} for miner {miner.name}")
                return True
            else:
                logger.error(f"✗ Failed to control HA device {ha_device.name} for miner {miner.name}")
                return False
                
        except Exception as e:
            logger.error(f"Error controlling HA device for miner {miner.name}: {e}")
            return False
    
    @staticmethod
    async def get_enrolled_miners(db: AsyncSession) -> List[Miner]:
        """
        Get list of miners enrolled in strategy
        
        Args:
            db: Database session
            
        Returns:
            List of enrolled Miner objects
        """
        result = await db.execute(
            select(Miner)
            .join(MinerStrategy, Miner.id == MinerStrategy.miner_id)
            .where(MinerStrategy.strategy_enabled == True)
            .where(Miner.enabled == True)
        )
        return result.scalars().all()
    
    @staticmethod
    async def validate_required_pools(db: AsyncSession, bands: List[AgileStrategyBand]) -> Tuple[bool, List[str]]:
        """
        Validate that required pools are configured for enabled band coins
        
        Checks that pools exist for any coins configured in bands (not OFF)
        
        Args:
            db: Database session
            bands: List of configured strategy bands
            
        Returns:
            (is_valid, list_of_violations)
        """
        from core.braiins import BraiinsPoolService
        from core.config import app_config
        
        violations = []
        
        # Get unique coins from bands (excluding OFF)
        required_coins = set(band.target_coin for band in bands if band.target_coin != "OFF")
        
        if not required_coins:
            return (True, [])  # No coins configured, nothing to validate
        
        # Get all configured pools
        pools_result = await db.execute(select(Pool))
        all_pools = pools_result.scalars().all()
        
        # Check for each required coin
        for coin in required_coins:
            pool_found = False
            
            if coin == "BTC":
                pool_found = any(SolopoolService.is_solopool_btc_pool(p.url, p.port) for p in all_pools)
                if not pool_found:
                    violations.append("Missing required pool: solopool.org BTC (eu3.solopool.org:8005)")
                    
            elif coin == "BTC_POOLED":
                # Check Braiins pool exists
                pool_found = any(BraiinsPoolService.is_braiins_pool(p.url, p.port) for p in all_pools)
                if not pool_found:
                    violations.append("Missing required pool: Braiins Pool BTC (stratum.braiins.com:3333)")
                
                # Check Braiins API configured
                braiins_enabled = app_config.get("braiins_enabled", False)
                braiins_token = app_config.get("braiins_api_token", "")
                if not braiins_enabled or not braiins_token:
                    violations.append("Braiins Pool API not configured in Settings > Integrations")
                    
            elif coin == "BCH":
                pool_found = any(SolopoolService.is_solopool_bch_pool(p.url, p.port) for p in all_pools)
                if not pool_found:
                    violations.append("Missing required pool: solopool.org BCH (eu2.solopool.org:8002)")
                    
            elif coin == "BC2":
                pool_found = any(SolopoolService.is_solopool_bc2_pool(p.url, p.port) for p in all_pools)
                if not pool_found:
                    violations.append("Missing required pool: solopool.org BC2 (eu3.solopool.org:8001)")
                    
            elif coin == "DGB":
                pool_found = any(SolopoolService.is_solopool_dgb_pool(p.url, p.port) for p in all_pools)
                if not pool_found:
                    violations.append("Missing required pool: solopool.org DGB (eu1.solopool.org:8004)")
        
        return (len(violations) == 0, violations)

    
    @staticmethod
    async def get_next_slot_price(db: AsyncSession) -> Optional[float]:
        """
        Get the price for the next Agile slot (30 minutes from now)
        
        Returns:
            Price in pence/kWh or None if not available
        """
        from core.config import app_config
        
        region = app_config.get("octopus_agile.region", "H")
        now = datetime.utcnow()
        next_slot_start = now + timedelta(minutes=30)
        
        result = await db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.region == region)
            .where(EnergyPrice.valid_from <= next_slot_start)
            .where(EnergyPrice.valid_to > next_slot_start)
            .limit(1)
        )
        next_price = result.scalar_one_or_none()
        return next_price.price_pence if next_price else None
    
    @staticmethod
    async def determine_band_with_hysteresis(
        db: AsyncSession,
        current_price: float,
        strategy: AgileStrategy,
        bands: List[AgileStrategyBand]
    ) -> Tuple[AgileStrategyBand, int]:
        """
        Determine target price band with look-ahead confirmation
        
        When upgrading to a better band, checks if the NEXT slot also
        qualifies for that band. Only upgrades if confirmed, preventing
        oscillation from single cheap slots.
        
        CRITICAL: OFF band is ALWAYS immediate - no confirmation needed.
        
        Args:
            db: Database session
            current_price: Current energy price (p/kWh)
            strategy: Current strategy state
            bands: List of configured price bands (ordered by sort_order)
            
        Returns:
            (target_band_object, new_hysteresis_counter)
        """
        # Get current and new band objects
        current_band_obj = None
        if strategy.current_price_band:
            # Find current band by matching target_coin
            for band in bands:
                if band.target_coin == strategy.current_price_band:
                    current_band_obj = band
                    break
        
        # If no current band, start with first band (worst/OFF)
        if not current_band_obj:
            current_band_obj = bands[0]
        
        # Get new band for current price
        new_band_obj = get_band_for_price(bands, current_price)
        
        if not new_band_obj:
            logger.error("Could not determine band for current price")
            return (bands[0], 0)  # Default to first band (OFF)
        
        # SAFETY: If current price hits OFF band, turn off immediately
        if new_band_obj.target_coin == "OFF":
            logger.warning(f"Price hit OFF threshold: {current_price:.2f}p - IMMEDIATE shutdown")
            return (new_band_obj, 0)
        
        # Compare band positions (higher sort_order = better pricing/lower cost)
        current_idx = current_band_obj.sort_order
        new_idx = new_band_obj.sort_order
        
        # Special case: Transitioning from OFF to any active state
        # When coming from OFF, ensure next slot won't immediately go back to OFF
        if current_band_obj.target_coin == "OFF" and new_band_obj.target_coin != "OFF":
            # Get next slot price to verify we won't immediately turn off again
            next_slot_price = await AgileSoloStrategy.get_next_slot_price(db)
            
            if next_slot_price is None:
                # No future price data, stay OFF to be safe
                logger.warning(f"No next slot price available, staying OFF")
                return (current_band_obj, 0)
            
            next_band_obj = get_band_for_price(bands, next_slot_price)
            
            if not next_band_obj:
                # Invalid next band, stay OFF
                return (current_band_obj, 0)
            
            # Check if next slot is also active (not OFF)
            if next_band_obj.target_coin == "OFF":
                # Next slot goes back to OFF, don't turn on for just 1 slot
                logger.info(f"Skipping OFF→{new_band_obj.target_coin} transition: next slot returns to OFF (current: {current_price:.2f}p → next: {next_slot_price:.2f}p)")
                return (current_band_obj, 0)
            else:
                # Next slot stays active, safe to turn on
                logger.info(f"OFF→{new_band_obj.target_coin} transition confirmed: next slot stays active (current: {current_price:.2f}p → next: {next_slot_price:.2f}p)")
                return (new_band_obj, 0)
        
        # If price improved (higher sort_order = better band) 
        if new_idx > current_idx:
            # Upgrading band - check next slot for confirmation
            next_slot_price = await AgileSoloStrategy.get_next_slot_price(db)
            
            if next_slot_price is None:
                # No future price data, stay in current band
                logger.warning(f"No next slot price available, staying in {current_band_obj.target_coin}")
                return (current_band_obj, 0)
            
            next_band_obj = get_band_for_price(bands, next_slot_price)
            
            if not next_band_obj:
                # Invalid next band, stay safe
                return (current_band_obj, 0)
            
            next_idx = next_band_obj.sort_order
            
            # Check if next slot is also in the better band (or even better)
            if next_idx >= new_idx:
                # Next slot confirms the improvement, upgrade immediately
                logger.info(f"Next slot confirms improvement (current: {current_price:.2f}p → next: {next_slot_price:.2f}p), upgrading from {current_band_obj.target_coin} to {new_band_obj.target_coin}")
                return (new_band_obj, 0)
            else:
                # Next slot goes back to worse band, stay put
                logger.info(f"Next slot returns to worse pricing (current: {current_price:.2f}p → next: {next_slot_price:.2f}p), staying in {current_band_obj.target_coin}")
                return (current_band_obj, 0)
        
        # If price worsened (lower sort_order = worse band)
        elif new_idx < current_idx:
            # Immediate downgrade
            logger.info(f"Price worsened, immediate downgrade from {current_band_obj.target_coin} to {new_band_obj.target_coin}")
            return (new_band_obj, 0)
        
        # Price unchanged
        else:
            # Stay in current band
            return (current_band_obj, 0)
    
    @staticmethod
    async def find_pool_for_coin(db: AsyncSession, coin: str) -> Optional[Pool]:
        """
        Find appropriate pool for given coin (solo or pooled)
        
        Args:
            db: Database session
            coin: Coin symbol (DGB, BCH, BTC, BC2, BTC_POOLED)
            
        Returns:
            Pool object or None
        """
        from core.braiins import BraiinsPoolService
        
        result = await db.execute(
            select(Pool)
            .where(Pool.enabled == True)
        )
        all_pools = result.scalars().all()
        
        # Check each pool
        for pool in all_pools:
            if coin == "DGB" and SolopoolService.is_solopool_dgb_pool(pool.url, pool.port):
                return pool
            elif coin == "BCH" and SolopoolService.is_solopool_bch_pool(pool.url, pool.port):
                return pool
            elif coin == "BC2" and SolopoolService.is_solopool_bc2_pool(pool.url, pool.port):
                return pool
            elif coin == "BTC" and SolopoolService.is_solopool_btc_pool(pool.url, pool.port):
                return pool
            elif coin == "BTC_POOLED" and BraiinsPoolService.is_braiins_pool(pool.url, pool.port):
                return pool
        
        return None
    
    @staticmethod
    async def execute_strategy(db: AsyncSession) -> Dict:
        """
        Execute the Agile Strategy
        
        Returns:
            Execution report dict with actions taken
        """
        logger.info("=" * 60)
        logger.info("EXECUTING AGILE STRATEGY")
        logger.info("=" * 60)
        
        # Get strategy config
        result = await db.execute(select(AgileStrategy))
        strategy = result.scalar_one_or_none()
        
        if not strategy or not strategy.enabled:
            logger.info("Strategy disabled, skipping execution")
            return {"enabled": False, "message": "Strategy is disabled"}
        
        # Ensure bands are initialized (handles migration from old versions)
        await ensure_strategy_bands(db, strategy.id)
        
        # Get configured bands
        bands = await get_strategy_bands(db, strategy.id)
        
        if not bands:
            logger.error("No bands configured for strategy")
            return {"error": "NO_BANDS", "message": "No price bands configured"}
        
        # Get enrolled miners
        enrolled_miners = await AgileSoloStrategy.get_enrolled_miners(db)
        
        if not enrolled_miners:
            logger.warning("No miners enrolled in strategy")
            return {"enabled": True, "miners": 0, "message": "No enrolled miners"}
        
        logger.info(f"Enrolled miners: {len(enrolled_miners)}")
        
        # Validate required pools exist for configured bands
        is_valid, violations = await AgileSoloStrategy.validate_required_pools(db, bands)
        
        if not is_valid:
            logger.error(f"Pool validation FAILED: {violations}")
            await log_audit(
                db,
                action="agile_strategy_disabled",
                resource_type="agile_strategy",
                resource_name="Agile Strategy",
                status="error",
                error_message=f"Pool validation failed: {', '.join(violations)}",
                changes={"violations": violations}
            )
            # CRITICAL: Disable strategy on validation failure
            strategy.enabled = False
            await db.commit()
            return {
                "enabled": False,
                "error": "VALIDATION_FAILED",
                "violations": violations,
                "message": "Strategy disabled due to missing required pools"
            }
        
        # Get current energy price
        current_price_obj = await get_current_energy_price(db)
        
        if current_price_obj is None:
            logger.error("Failed to get current energy price")
            return {"error": "NO_PRICE_DATA", "message": "No energy price data available"}
        
        current_price = current_price_obj.price_pence
        logger.info(f"Current energy price: {current_price}p/kWh")
        
        # Apply hysteresis logic to determine target band with look-ahead confirmation
        target_band_obj, new_counter = await AgileSoloStrategy.determine_band_with_hysteresis(
            db, current_price, strategy, bands
        )
        
        if not target_band_obj:
            logger.error("Could not determine band for current price")
            return {"error": "BAND_ERROR", "message": "Could not determine price band"}
        
        logger.info(f"Target band: {target_band_obj.target_coin} @ {current_price}p/kWh")
        
        # Store band identifier for state tracking (use sort_order as identifier)
        target_band_id = target_band_obj.sort_order
        
        # Update strategy state  
        strategy.current_price_band = target_band_obj.target_coin  # Store coin for backward compatibility
        strategy.last_price_checked = current_price
        strategy.last_action_time = datetime.utcnow()
        strategy.hysteresis_counter = new_counter
        
        # Get target coin from band
        target_coin = target_band_obj.target_coin
        
        actions_taken = []
        
        # Handle OFF state - turn off HA devices
        if target_coin == "OFF":
            logger.info(f"Target coin is OFF (price: {current_price}p/kWh) - turning off linked HA devices")
            
            ha_actions = []
            for miner in enrolled_miners:
                controlled = await AgileSoloStrategy.control_ha_device_for_miner(db, miner, turn_on=False)
                if controlled:
                    ha_actions.append(f"{miner.name}: HA device turned OFF")
                else:
                    ha_actions.append(f"{miner.name}: No HA device linked")
            
            await log_audit(
                db,
                action="agile_strategy_off_detected",
                resource_type="agile_strategy",
                resource_name="Agile Solo Strategy",
                changes={
                    "price": current_price,
                    "miners_enrolled": len(enrolled_miners),
                    "ha_devices_controlled": len([a for a in ha_actions if "turned OFF" in a])
                }
            )
            
            await db.commit()
            
            return {
                "enabled": True,
                "price": current_price,
                "band": "OFF",
                "coin": None,
                "miners": len(enrolled_miners),
                "message": f"OFF state - {len([a for a in ha_actions if 'turned OFF' in a])} HA devices turned off",
                "actions": ha_actions
            }
        
        else:
            # Find target pool (solo or pooled)
            target_pool = await AgileSoloStrategy.find_pool_for_coin(db, target_coin)
            
            if not target_pool:
                logger.error(f"No pool found for {target_coin}")
                return {
                    "error": "NO_POOL",
                    "message": f"No pool configured for {target_coin}"
                }
            
            logger.info(f"Target pool: {target_pool.name} ({target_coin})")
            
            # Apply changes to each miner
            from adapters import get_adapter
            
            for miner in enrolled_miners:
                # Get target mode from band based on miner type
                if miner.miner_type == "bitaxe":
                    target_mode = target_band_obj.bitaxe_mode
                elif miner.miner_type == "nerdqaxe":
                    target_mode = target_band_obj.nerdqaxe_mode
                elif miner.miner_type == "avalon_nano":
                    target_mode = target_band_obj.avalon_nano_mode
                elif miner.miner_type == "nmminer":
                    target_mode = "fixed"  # NMMiner has no configurable modes
                else:
                    logger.warning(f"Unknown miner type {miner.miner_type} for {miner.name}")
                    target_mode = None
                
                # Managed externally mode doubles as HA-off per band
                if target_mode == "managed_externally":
                    controlled = await AgileSoloStrategy.control_ha_device_for_miner(db, miner, turn_on=False)
                    if controlled:
                        actions_taken.append(f"{miner.name}: HA device OFF (band control)")
                    else:
                        actions_taken.append(f"{miner.name}: External control (no HA link)")
                    continue
                else:
                    await AgileSoloStrategy.control_ha_device_for_miner(db, miner, turn_on=True)
                
                logger.info(f"Miner {miner.name} ({miner.miner_type}): target mode = {target_mode}")
                
                # Get adapter
                adapter = get_adapter(miner)
                if not adapter:
                    logger.error(f"No adapter for miner {miner.name}")
                    actions_taken.append(f"{miner.name}: FAILED (no adapter)")
                    continue
                
                # Check current state to avoid unnecessary restarts
                try:
                    # Refresh miner from DB to get latest mode (in case reconciliation just updated it)
                    await db.refresh(miner)
                    
                    telemetry = await adapter.get_telemetry()
                    current_pool = telemetry.pool_in_use if telemetry else None
                    current_mode = miner.current_mode
                    
                    # Build expected pool URL
                    target_pool_url = f"{target_pool.url}:{target_pool.port}"
                    
                    # Check if already on correct pool and mode
                    pool_already_correct = current_pool and target_pool_url in current_pool
                    mode_already_correct = current_mode == target_mode
                    
                    if pool_already_correct and mode_already_correct:
                        logger.info(f"{miner.name} already on {target_pool.name} with mode {target_mode}, skipping")
                        actions_taken.append(f"{miner.name}: Already correct (no change)")
                        continue
                    
                except Exception as e:
                    logger.warning(f"Could not check current state for {miner.name}: {e}")
                    # Continue with switch attempt if we can't verify current state
                
                # Switch pool (only if needed)
                try:
                    pool_switched = await adapter.switch_pool(
                        pool_url=target_pool.url,
                        pool_port=target_pool.port,
                        pool_user=target_pool.user,
                        pool_password=target_pool.password
                    )
                    
                    if not pool_switched:
                        logger.warning(f"Failed to switch {miner.name} to {target_pool.name}")
                        actions_taken.append(f"{miner.name}: Pool switch FAILED")
                        continue
                    
                    logger.info(f"Switched {miner.name} to pool {target_pool.name}")
                    
                    # Wait for miner to finish rebooting after pool switch
                    logger.debug(f"Waiting 8 seconds for {miner.name} to reboot after pool switch...")
                    await asyncio.sleep(8)
                except Exception as e:
                    logger.error(f"Error switching pool for {miner.name}: {e}")
                    actions_taken.append(f"{miner.name}: Pool switch ERROR - {e}")
                    continue
                
                # Set mode
                if target_mode:
                    try:
                        mode_set = await adapter.set_mode(target_mode)
                        
                        if not mode_set:
                            logger.warning(f"Failed to set mode {target_mode} on {miner.name}")
                            actions_taken.append(f"{miner.name}: {target_coin} pool OK, mode change FAILED")
                        else:
                            logger.info(f"Set {miner.name} to mode {target_mode}")
                            actions_taken.append(f"{miner.name}: {target_coin} pool, mode={target_mode}")
                            
                            # Update miner's last mode change time
                            miner.current_mode = target_mode
                            miner.last_mode_change = datetime.utcnow()
                    except Exception as e:
                        logger.error(f"Error setting mode for {miner.name}: {e}")
                        actions_taken.append(f"{miner.name}: Mode change ERROR - {e}")
                else:
                    actions_taken.append(f"{miner.name}: {target_coin} pool (mode unchanged)")
            
            await log_audit(
                db,
                action="agile_strategy_executed",
                resource_type="agile_strategy",
                resource_name="Agile Solo Strategy",
                changes={
                    "price": current_price,
                    "band": f"Band {target_band_obj.sort_order}: {target_band_obj.target_coin}",
                    "coin": target_coin,
                    "pool": target_pool.name,
                    "miners_affected": len(enrolled_miners),
                    "hysteresis_counter": new_counter
                }
            )
            
            # Log system event
            from core.database import Event
            event = Event(
                event_type="info",
                source="agile_strategy",
                message=f"Agile strategy executed: {target_coin} @ {current_price}p/kWh ({len(enrolled_miners)} miners)"
            )
            db.add(event)
        
        await db.commit()
        
        report = {
            "enabled": True,
            "price": current_price,
            "band": f"Band {target_band_obj.sort_order}: {target_band_obj.target_coin}",
            "coin": target_coin,
            "miners": len(enrolled_miners),
            "actions": actions_taken,
            "hysteresis_counter": new_counter
        }
        
        logger.info(f"Strategy execution complete: {report}")
        
        return report
    
    @staticmethod
    async def reconcile_strategy(db: AsyncSession) -> Dict:
        """
        Reconcile strategy - ensure enrolled miners match intended state
        Runs every 5 minutes to catch drift from manual changes or failures
        
        Returns:
            Reconciliation report dict
        """
        logger.debug("Reconciling Agile Solo Strategy")
        
        # Get strategy config
        result = await db.execute(select(AgileStrategy))
        strategy = result.scalar_one_or_none()
        
        if not strategy or not strategy.enabled:
            return {"reconciled": False, "message": "Strategy disabled"}
        
        # Ensure bands exist
        from core.agile_bands import ensure_strategy_bands, get_strategy_bands, get_band_for_price
        await ensure_strategy_bands(db, strategy.id)
        
        # Get enrolled miners
        enrolled_miners = await AgileSoloStrategy.get_enrolled_miners(db)
        
        if not enrolled_miners:
            return {"reconciled": False, "message": "No enrolled miners"}
        
        # Get current state
        current_band = strategy.current_price_band
        if not current_band:
            logger.debug("No current band set, skipping reconciliation")
            return {"reconciled": False, "message": "No band state"}
        
        # Get bands and find matching band
        bands = await get_strategy_bands(db, strategy.id)
        
        # Get current price to find the band
        current_price_obj = await get_current_energy_price(db)
        if current_price_obj is None:
            logger.warning("Could not fetch current price for reconciliation")
            return {"reconciled": False, "message": "No price data"}
        
        current_price_p_kwh = current_price_obj.price_pence
        band = get_band_for_price(bands, current_price_p_kwh)
        
        if not band:
            logger.warning("No matching band found for reconciliation")
            return {"reconciled": False, "message": "No matching band"}
        
        target_coin = band.target_coin
        
        # If OFF state, ensure HA devices are actually off
        if target_coin == "OFF":
            ha_corrections = []
            for miner in enrolled_miners:
                # Check if HA device is enrolled and linked
                result = await db.execute(
                    select(HomeAssistantDevice)
                    .where(HomeAssistantDevice.miner_id == miner.id)
                    .where(HomeAssistantDevice.enrolled == True)
                )
                ha_device = result.scalar_one_or_none()
                
                if ha_device:
                    # Get current device state from HA
                    try:
                        config_result = await db.execute(select(HomeAssistantConfig))
                        ha_config = config_result.scalar_one_or_none()
                        
                        if ha_config and ha_config.enabled:
                            from integrations.homeassistant import HomeAssistantIntegration
                            ha_integration = HomeAssistantIntegration(
                                base_url=ha_config.base_url,
                                access_token=ha_config.access_token
                            )
                            
                            state = await ha_integration.get_device_state(ha_device.entity_id)
                            if state and state.state == "on":
                                # Device is ON but should be OFF
                                logger.warning(f"Reconciliation: HA device {ha_device.name} for {miner.name} is ON during OFF period - turning off")
                                success = await ha_integration.turn_off(ha_device.entity_id)
                                if success:
                                    ha_corrections.append(f"{miner.name}: HA device turned OFF")
                                else:
                                    ha_corrections.append(f"{miner.name}: HA device turn OFF FAILED")
                    except Exception as e:
                        logger.error(f"Reconciliation: Failed to check HA device for {miner.name}: {e}")
            
            if ha_corrections:
                await log_audit(
                    db,
                    action="agile_strategy_reconciled_ha_devices",
                    resource_type="agile_strategy",
                    resource_name="Agile Solo Strategy",
                    changes={"corrections": ha_corrections, "band": "OFF"}
                )
                await db.commit()
        
            # ALWAYS return after OFF handling - don't fall through to active mining logic
            return {
                "reconciled": True,
                "band": "OFF",
                "coin": None,
                "corrections": 0,
                "ha_corrections": len(ha_corrections),
                "details": ha_corrections if ha_corrections else ["All HA devices already OFF"]
            }
        
        # Find target pool
        target_pool = await AgileSoloStrategy.find_pool_for_coin(db, target_coin)
        if not target_pool:
            logger.warning(f"No solo pool found for {target_coin} during reconciliation")
            return {"reconciled": False, "error": "NO_POOL"}
        
        # Check each miner and re-apply if needed
        from adapters import get_adapter
        corrections = []
        ha_corrections = []
        
        # Build target pool URL for comparison
        target_pool_url = f"{target_pool.url}:{target_pool.port}"
        
        for miner in enrolled_miners:
            # Determine target mode based on miner type
            if miner.miner_type in ["bitaxe", "nerdqaxe"]:
                target_mode = band.bitaxe_mode if miner.miner_type == "bitaxe" else band.nerdqaxe_mode
            elif miner.miner_type == "avalon_nano":
                target_mode = band.avalon_nano_mode
            else:
                target_mode = None
            
            if target_mode == "managed_externally":
                controlled = await AgileSoloStrategy.control_ha_device_for_miner(db, miner, turn_on=False)
                if controlled:
                    ha_corrections.append(f"{miner.name}: HA device enforced OFF")
                continue
            else:
                await AgileSoloStrategy.control_ha_device_for_miner(db, miner, turn_on=True)
            
            # Check both pool AND mode in single pass
            pool_correct = False
            mode_correct = miner.current_mode == target_mode
            
            adapter = get_adapter(miner)
            if adapter:
                try:
                    # Get current pool from telemetry
                    telemetry = await adapter.get_telemetry()
                    if telemetry and telemetry.pool_in_use:
                        pool_correct = target_pool_url in telemetry.pool_in_use
                except Exception as e:
                    logger.warning(f"Reconciliation: Could not check pool for {miner.name}: {e}")
            
            # If either pool or mode is wrong, correct both
            if not pool_correct or not mode_correct:
                issues = []
                if not pool_correct:
                    issues.append("pool")
                if not mode_correct:
                    issues.append(f"mode ({miner.current_mode} → {target_mode})")
                
                logger.info(f"Reconciliation: {miner.name} drift detected: {', '.join(issues)}")
                
                if adapter:
                    try:
                        # Switch pool if needed
                        if not pool_correct:
                            await adapter.switch_pool(
                                pool_url=target_pool.url,
                                pool_port=target_pool.port,
                                pool_user=target_pool.user,
                                pool_password=target_pool.password
                            )
                            logger.info(f"Reconciliation: Corrected {miner.name} to pool {target_pool.name}")
                            # Wait for miner to reboot after pool switch
                            await asyncio.sleep(8)
                        
                        # Apply correct mode
                        if target_mode:
                            await adapter.set_mode(target_mode)
                            miner.current_mode = target_mode
                            miner.last_mode_change = datetime.utcnow()
                        
                        corrections.append(f"{miner.name}: corrected {', '.join(issues)}")
                        logger.info(f"Reconciliation: {miner.name} fully corrected")
                    except Exception as e:
                        logger.error(f"Reconciliation failed for {miner.name}: {e}")
                        corrections.append(f"{miner.name}: correction FAILED - {e}")
        
        await db.commit()
        
        if corrections or ha_corrections:
            await log_audit(
                db,
                action="agile_strategy_reconciled",
                resource_type="agile_strategy",
                resource_name="Agile Solo Strategy",
                changes={
                    "corrections": corrections,
                    "ha_corrections": ha_corrections,
                    "band": current_band,
                    "coin": target_coin
                }
            )
            await db.commit()
        
        return {
            "reconciled": True,
            "band": current_band,
            "coin": target_coin,
            "corrections": len(corrections),
            "ha_corrections": len(ha_corrections),
            "details": corrections + ha_corrections
        }
