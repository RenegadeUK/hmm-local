"""
Agile Solo Mining Strategy - Core Logic Engine
Solo-only variance-driven mining optimised for Octopus Agile UK pricing
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import logging

from core.database import AgileStrategy, MinerStrategy, Miner, Pool, EnergyPrice, Telemetry
from core.energy import get_current_energy_price
from core.audit import log_audit
from core.solopool import SolopoolService

logger = logging.getLogger(__name__)


class PriceBand:
    """Price band definitions"""
    OFF = "off"           # ≥20p - Hard OFF
    DGB_HIGH = "dgb_high"  # 12-20p - DGB Eco/Low
    DGB_MED = "dgb_med"    # 7-12p - DGB Std/Med
    DGB_LOW = "dgb_low"    # Unused in current spec
    BCH = "bch"            # 4-7p - BCH High/OC
    BTC = "btc"            # <4p - BTC Max/OC


class AgileSoloStrategy:
    """Agile Solo Strategy execution engine"""
    
    # Price thresholds (pence per kWh)
    THRESHOLD_OFF = 20.0
    THRESHOLD_DGB_HIGH = 12.0
    THRESHOLD_DGB_MED = 7.0
    THRESHOLD_BCH = 4.0
    THRESHOLD_BTC = 0.0
    
    # Hysteresis counter requirement for upgrading bands
    HYSTERESIS_SLOTS = 2
    
    @staticmethod
    def calculate_price_band(price_p_kwh: float) -> str:
        """
        Calculate price band from energy price
        
        Args:
            price_p_kwh: Current energy price in pence per kWh
            
        Returns:
            Price band string (off, dgb_high, dgb_med, bch, btc)
        """
        if price_p_kwh >= AgileSoloStrategy.THRESHOLD_OFF:
            return PriceBand.OFF
        elif price_p_kwh >= AgileSoloStrategy.THRESHOLD_DGB_HIGH:
            return PriceBand.DGB_HIGH
        elif price_p_kwh >= AgileSoloStrategy.THRESHOLD_DGB_MED:
            return PriceBand.DGB_MED
        elif price_p_kwh >= AgileSoloStrategy.THRESHOLD_BCH:
            return PriceBand.BCH
        else:
            return PriceBand.BTC
    
    @staticmethod
    def get_coin_for_band(price_band: str) -> Optional[str]:
        """
        Map price band to target coin
        
        Args:
            price_band: Price band (off, dgb_high, dgb_med, bch, btc)
            
        Returns:
            Coin symbol (DGB, BCH, BTC) or None for OFF
        """
        coin_map = {
            PriceBand.OFF: None,
            PriceBand.DGB_HIGH: "DGB",
            PriceBand.DGB_MED: "DGB",
            PriceBand.BCH: "BCH",
            PriceBand.BTC: "BTC"
        }
        return coin_map.get(price_band)
    
    @staticmethod
    def get_mode_for_band(price_band: str, miner_type: str) -> Optional[str]:
        """
        Get target mode for miner type and price band
        
        Args:
            price_band: Price band
            miner_type: Miner type (bitaxe, nerdqaxe, avalon_nano)
            
        Returns:
            Mode string or None for OFF
        """
        # Mode mappings per spec
        mode_map = {
            PriceBand.OFF: {
                "bitaxe": None,
                "nerdqaxe": None,
                "avalon_nano": None
            },
            PriceBand.DGB_HIGH: {  # 12-20p
                "bitaxe": "eco",  # Can be eco or standard
                "nerdqaxe": "eco",
                "avalon_nano": "low"  # Can be OFF or low
            },
            PriceBand.DGB_MED: {  # 7-12p
                "bitaxe": "standard",
                "nerdqaxe": "standard",
                "avalon_nano": "high"  # Ramps from low to high
            },
            PriceBand.BCH: {  # 4-7p
                "bitaxe": "oc",
                "nerdqaxe": "standard",
                "avalon_nano": "high"
            },
            PriceBand.BTC: {  # <4p
                "bitaxe": "oc",
                "nerdqaxe": "oc",
                "avalon_nano": "high"
            }
        }
        
        band_modes = mode_map.get(price_band, {})
        return band_modes.get(miner_type)
    
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
    async def validate_solo_pools(db: AsyncSession, miners: List[Miner]) -> Tuple[bool, List[str]]:
        """
        Validate that all enrolled miners are using solo pools
        
        Args:
            db: Database session
            miners: List of enrolled miners
            
        Returns:
            (is_valid, list_of_violations)
        """
        violations = []
        
        # Get pools used by enrolled miners only
        # We only care about SHA256 pools that could be assigned to Bitaxe/Avalon Nano
        miner_ids = [m.id for m in miners]
        
        # Get recent telemetry to see what pools these miners are actually using
        recent_telemetry = await db.execute(
            select(Telemetry)
            .filter(Telemetry.miner_id.in_(miner_ids))
            .filter(Telemetry.pool_in_use.isnot(None))
            .order_by(Telemetry.timestamp.desc())
            .limit(len(miner_ids) * 2)  # Get a few recent records per miner
        )
        telemetry_records = recent_telemetry.scalars().all()
        
        # Extract unique pools from telemetry (format: "url:port" or "stratum+tcp://url:port")
        pools_in_use = set()
        for telem in telemetry_records:
            if telem.pool_in_use and ':' in telem.pool_in_use:
                pool_str = telem.pool_in_use
                
                # Strip protocol prefix if present (stratum+tcp://, stratum://)
                if '://' in pool_str:
                    pool_str = pool_str.split('://', 1)[1]
                
                parts = pool_str.rsplit(':', 1)
                if len(parts) == 2:
                    pool_url = parts[0]
                    try:
                        pool_port = int(parts[1])
                        pools_in_use.add((pool_url, pool_port))
                    except ValueError:
                        # Port is not a number, skip this entry
                        continue
        
        # Validate each pool in use
        for pool_url, pool_port in pools_in_use:
            if not SolopoolService.is_solopool(pool_url, pool_port):
                violations.append(
                    f"Enrolled miner using non-solopool.org pool: {pool_url}:{pool_port}"
                )
        
        # If no violations, we're good
        violations = list(set(violations))
        
        return (len(violations) == 0, violations)
    
    @staticmethod
    async def determine_band_with_hysteresis(
        db: AsyncSession,
        current_price: float,
        strategy: AgileStrategy
    ) -> Tuple[str, int]:
        """
        Determine target price band with hysteresis logic
        
        Args:
            db: Database session
            current_price: Current energy price (p/kWh)
            strategy: Current strategy state
            
        Returns:
            (target_band, new_hysteresis_counter)
        """
        current_band = strategy.current_price_band or PriceBand.OFF
        new_band = AgileSoloStrategy.calculate_price_band(current_price)
        counter = strategy.hysteresis_counter
        
        # Define band ordering (worse to better)
        band_order = [
            PriceBand.OFF,
            PriceBand.DGB_HIGH,
            PriceBand.DGB_MED,
            PriceBand.BCH,
            PriceBand.BTC
        ]
        
        try:
            current_idx = band_order.index(current_band)
            new_idx = band_order.index(new_band)
        except ValueError:
            # Invalid band, reset to calculated
            return (new_band, 0)
        
        # If price improved (moving down the list = better pricing)
        if new_idx > current_idx:
            # Upgrading band - need hysteresis
            counter += 1
            if counter >= AgileSoloStrategy.HYSTERESIS_SLOTS:
                # Hysteresis satisfied, upgrade
                logger.info(f"Hysteresis satisfied ({counter} slots), upgrading from {current_band} to {new_band}")
                return (new_band, 0)
            else:
                # Stay in current band, increment counter
                logger.info(f"Price improved but hysteresis not satisfied ({counter}/{AgileSoloStrategy.HYSTERESIS_SLOTS}), staying in {current_band}")
                return (current_band, counter)
        
        # If price worsened (moving up the list = worse pricing)
        elif new_idx < current_idx:
            # Immediate downgrade
            logger.info(f"Price worsened, immediate downgrade from {current_band} to {new_band}")
            return (new_band, 0)
        
        # Price unchanged
        else:
            # Reset counter if we're stable in this band
            return (current_band, 0)
    
    @staticmethod
    async def find_solo_pool(db: AsyncSession, coin: str) -> Optional[Pool]:
        """
        Find solopool.org pool for given coin
        
        Args:
            db: Database session
            coin: Coin symbol (DGB, BCH, BTC)
            
        Returns:
            Pool object or None
        """
        result = await db.execute(
            select(Pool)
            .where(Pool.enabled == True)
        )
        all_pools = result.scalars().all()
        
        # Map coins to solopool.org hostnames
        solopool_hosts = {
            "DGB": "dgb-sha.solopool.org",
            "BCH": "bch.solopool.org",
            "BTC": "btc.solopool.org"
        }
        
        target_host = solopool_hosts.get(coin)
        if not target_host:
            return None
        
        for pool in all_pools:
            if target_host in pool.url.lower():
                return pool
        
        return None
    
    @staticmethod
    async def execute_strategy(db: AsyncSession) -> Dict:
        """
        Execute the Agile Solo Strategy
        
        Returns:
            Execution report dict with actions taken
        """
        logger.info("=" * 60)
        logger.info("EXECUTING AGILE SOLO STRATEGY")
        logger.info("=" * 60)
        
        # Get strategy config
        result = await db.execute(select(AgileStrategy))
        strategy = result.scalar_one_or_none()
        
        if not strategy or not strategy.enabled:
            logger.info("Strategy disabled, skipping execution")
            return {"enabled": False, "message": "Strategy is disabled"}
        
        # Get enrolled miners
        enrolled_miners = await AgileSoloStrategy.get_enrolled_miners(db)
        
        if not enrolled_miners:
            logger.warning("No miners enrolled in strategy")
            return {"enabled": True, "miners": 0, "message": "No enrolled miners"}
        
        logger.info(f"Enrolled miners: {len(enrolled_miners)}")
        
        # Validate solo-only pools
        is_valid, violations = await AgileSoloStrategy.validate_solo_pools(db, enrolled_miners)
        
        if not is_valid:
            logger.error(f"Solo pool validation FAILED: {violations}")
            await log_audit(
                db,
                action="agile_strategy_disabled",
                resource_type="agile_strategy",
                resource_name="Agile Solo Strategy",
                status="error",
                error_message=f"Solo pool validation failed: {', '.join(violations)}",
                changes={"violations": violations}
            )
            # CRITICAL: Disable strategy on violation
            strategy.enabled = False
            await db.commit()
            return {
                "enabled": False,
                "error": "VALIDATION_FAILED",
                "violations": violations,
                "message": "Strategy disabled due to non-solo pool detection"
            }
        
        # Get current energy price
        current_price_obj = await get_current_energy_price(db)
        
        if current_price_obj is None:
            logger.error("Failed to get current energy price")
            return {"error": "NO_PRICE_DATA", "message": "No energy price data available"}
        
        current_price = current_price_obj.price_pence
        logger.info(f"Current energy price: {current_price}p/kWh")
        
        # Determine target band with hysteresis
        target_band, new_counter = await AgileSoloStrategy.determine_band_with_hysteresis(
            db, current_price, strategy
        )
        
        logger.info(f"Target band: {target_band} (hysteresis counter: {new_counter})")
        
        # Update strategy state
        strategy.current_price_band = target_band
        strategy.hysteresis_counter = new_counter
        strategy.last_price_checked = current_price
        strategy.last_action_time = datetime.utcnow()
        
        # Get target coin
        target_coin = AgileSoloStrategy.get_coin_for_band(target_band)
        
        actions_taken = []
        
        # Handle OFF state (≥20p) - managed externally
        if target_band == PriceBand.OFF:
            logger.info(f"Target band is OFF (price: {current_price}p/kWh ≥ 20p) - shutdown managed externally")
            
            await log_audit(
                db,
                action="agile_strategy_off_detected",
                resource_type="agile_strategy",
                resource_name="Agile Solo Strategy",
                changes={"price": current_price, "miners_enrolled": len(enrolled_miners)}
            )
            
            await db.commit()
            
            return {
                "enabled": True,
                "price": current_price,
                "band": PriceBand.OFF,
                "coin": None,
                "miners": len(enrolled_miners),
                "message": "OFF state - shutdown managed externally",
                "actions": ["OFF state detected - external automation will handle shutdown"]
            }
        
        else:
            # Find target pool
            target_pool = await AgileSoloStrategy.find_solo_pool(db, target_coin)
            
            if not target_pool:
                logger.error(f"No solo pool found for {target_coin}")
                return {
                    "error": "NO_POOL",
                    "message": f"No solopool.org pool configured for {target_coin}"
                }
            
            logger.info(f"Target pool: {target_pool.name} ({target_coin})")
            
            # Apply changes to each miner
            from adapters import get_adapter
            
            for miner in enrolled_miners:
                target_mode = AgileSoloStrategy.get_mode_for_band(target_band, miner.miner_type)
                
                logger.info(f"Miner {miner.name} ({miner.miner_type}): target mode = {target_mode}")
                
                # Get adapter
                adapter = get_adapter(miner)
                if not adapter:
                    logger.error(f"No adapter for miner {miner.name}")
                    actions_taken.append(f"{miner.name}: FAILED (no adapter)")
                    continue
                
                # Switch pool
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
                    "band": target_band,
                    "coin": target_coin,
                    "pool": target_pool.name,
                    "miners_affected": len(enrolled_miners),
                    "hysteresis_counter": new_counter
                }
            )
        
        await db.commit()
        
        report = {
            "enabled": True,
            "price": current_price,
            "band": target_band,
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
        
        # Get enrolled miners
        enrolled_miners = await AgileSoloStrategy.get_enrolled_miners(db)
        
        if not enrolled_miners:
            return {"reconciled": False, "message": "No enrolled miners"}
        
        # Get current state
        current_band = strategy.current_price_band
        if not current_band:
            logger.debug("No current band set, skipping reconciliation")
            return {"reconciled": False, "message": "No band state"}
        
        target_coin = AgileSoloStrategy.get_coin_for_band(current_band)
        
        # If OFF state, ensure all miners are disabled
        if current_band == PriceBand.OFF:
            return {"reconciled": True, "message": "OFF state - no reconciliation needed"}
        
        # Find target pool
        target_pool = await AgileSoloStrategy.find_solo_pool(db, target_coin)
        if not target_pool:
            logger.warning(f"No solo pool found for {target_coin} during reconciliation")
            return {"reconciled": False, "error": "NO_POOL"}
        
        # Check each miner and re-apply if needed
        from adapters import get_adapter
        corrections = []
        
        for miner in enrolled_miners:
            target_mode = AgileSoloStrategy.get_mode_for_band(current_band, miner.miner_type)
            
            # Check if miner's current mode matches target
            if miner.current_mode != target_mode:
                logger.info(f"Reconciliation: {miner.name} mode drift detected: {miner.current_mode} → {target_mode}")
                
                adapter = get_adapter(miner)
                if adapter:
                    try:
                        # Re-apply correct mode
                        if target_mode:
                            await adapter.set_mode(target_mode)
                            miner.current_mode = target_mode
                            miner.last_mode_change = datetime.utcnow()
                            corrections.append(f"{miner.name}: mode corrected to {target_mode}")
                            logger.info(f"Reconciliation: Corrected {miner.name} to mode {target_mode}")
                    except Exception as e:
                        logger.error(f"Reconciliation failed for {miner.name}: {e}")
                        corrections.append(f"{miner.name}: correction FAILED - {e}")
        
        await db.commit()
        
        if corrections:
            await log_audit(
                db,
                action="agile_strategy_reconciled",
                resource_type="agile_strategy",
                resource_name="Agile Solo Strategy",
                changes={"corrections": corrections, "band": current_band, "coin": target_coin}
            )
            await db.commit()
        
        return {
            "reconciled": True,
            "band": current_band,
            "coin": target_coin,
            "corrections": len(corrections),
            "details": corrections
        }
