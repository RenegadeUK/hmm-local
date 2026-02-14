"""
Service to sync Avalon Nano miner pool slots to database
"""
import logging
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import Miner, Pool, MinerPoolSlot
from adapters import create_adapter

logger = logging.getLogger(__name__)


async def sync_avalon_nano_pool_slots(db: AsyncSession):
    """
    Query all Avalon Nano miners for their configured pool slots and cache in database.
    This allows strategies to know which pools are available on each miner.
    """
    # Get all enabled Avalon Nano miners
    result = await db.execute(
        select(Miner).where(
            and_(
                Miner.miner_type == "avalon_nano",
                Miner.enabled == True
            )
        )
    )
    miners = result.scalars().all()
    
    if not miners:
        logger.debug("No Avalon Nano miners to sync")
        return
    
    logger.info(f"Syncing pool slots for {len(miners)} Avalon Nano miners")
    
    for miner in miners:
        try:
            adapter = create_adapter(
                miner_type="avalon_nano",
                miner_id=miner.id,
                miner_name=miner.name,
                ip_address=miner.ip_address,
                port=miner.port,
                config=miner.config
            )
            
            if not adapter:
                logger.error(f"Failed to create adapter for miner {miner.id} ({miner.name})")
                continue
            
            # Query pool configuration from miner
            pools_response = await adapter._cgminer_command("pools")
            
            if not pools_response or "POOLS" not in pools_response:
                logger.warning(f"No pool data from miner {miner.id} ({miner.name})")
                continue
            
            pools_list = pools_response["POOLS"]
            
            # Get all pools from database for matching
            all_pools_result = await db.execute(select(Pool))
            all_pools = {f"{p.url}:{p.port}": p for p in all_pools_result.scalars().all()}
            
            # Process each pool slot (Avalon Nano has 3 slots: priority 0, 1, 2)
            for pool_data in pools_list:
                slot_number = pool_data.get("Priority", -1)
                if slot_number < 0 or slot_number > 2:
                    continue
                
                pool_url = pool_data.get("URL", "")
                pool_user = pool_data.get("User", "")
                is_active = pool_data.get("Status") == "Alive" and pool_data.get("Stratum Active", False)
                
                # Parse URL to get host and port
                # Format: stratum+tcp://pool.url:port
                pool_host = ""
                pool_port = 3333
                
                if "://" in pool_url:
                    pool_url_clean = pool_url.split("://")[1]
                    if ":" in pool_url_clean:
                        pool_host, port_str = pool_url_clean.rsplit(":", 1)
                        try:
                            pool_port = int(port_str)
                        except ValueError:
                            pool_host = pool_url_clean
                    else:
                        pool_host = pool_url_clean
                else:
                    if ":" in pool_url:
                        pool_host, port_str = pool_url.rsplit(":", 1)
                        try:
                            pool_port = int(port_str)
                        except ValueError:
                            pool_host = pool_url
                    else:
                        pool_host = pool_url
                
                # Try to match with a Pool in database
                pool_key = f"{pool_host}:{pool_port}"
                matched_pool_id = None
                
                if pool_key in all_pools:
                    matched_pool_id = all_pools[pool_key].id
                
                # Check if slot already exists
                existing_slot_result = await db.execute(
                    select(MinerPoolSlot).where(
                        and_(
                            MinerPoolSlot.miner_id == miner.id,
                            MinerPoolSlot.slot_number == slot_number
                        )
                    )
                )
                existing_slot = existing_slot_result.scalar_one_or_none()
                
                if existing_slot:
                    # Update existing slot
                    existing_slot.pool_id = matched_pool_id
                    existing_slot.pool_url = pool_host
                    existing_slot.pool_port = pool_port
                    existing_slot.pool_user = pool_user
                    existing_slot.is_active = is_active
                    existing_slot.last_seen = datetime.utcnow()
                else:
                    # Create new slot
                    new_slot = MinerPoolSlot(
                        miner_id=miner.id,
                        slot_number=slot_number,
                        pool_id=matched_pool_id,
                        pool_url=pool_host,
                        pool_port=pool_port,
                        pool_user=pool_user,
                        is_active=is_active,
                        last_seen=datetime.utcnow()
                    )
                    db.add(new_slot)
                
                logger.debug(f"Synced slot {slot_number} for miner {miner.id}: {pool_host}:{pool_port} (matched: {matched_pool_id}, active: {is_active})")
            
            await db.commit()
            logger.info(f"✓ Synced pool slots for miner {miner.id} ({miner.name})")
            
        except Exception as e:
            logger.error(f"Failed to sync pool slots for miner {miner.id} ({miner.name}): {e}")
            await db.rollback()
            continue


async def get_common_pools_for_avalon_nanos(db: AsyncSession) -> list[int]:
    """
    Get pool IDs that are configured on ALL Avalon Nano miners.
    These are the only pools that can be used in strategies for Avalon Nano miners.
    """
    # Get all enabled Avalon Nano miners
    result = await db.execute(
        select(Miner.id).where(
            and_(
                Miner.miner_type == "avalon_nano",
                Miner.enabled == True
            )
        )
    )
    nano_miner_ids = [row[0] for row in result.all()]
    
    if not nano_miner_ids:
        # No Avalon Nano miners, return all pools
        result = await db.execute(select(Pool.id).where(Pool.enabled == True))
        return [row[0] for row in result.all()]
    
    # Get pool slots for all Avalon Nano miners
    result = await db.execute(
        select(MinerPoolSlot).where(
            and_(
                MinerPoolSlot.miner_id.in_(nano_miner_ids),
                MinerPoolSlot.pool_id.isnot(None)  # Only slots matched to a Pool
            )
        )
    )
    slots = result.scalars().all()
    
    # Group by miner ID to get pools per miner
    pools_by_miner = {}
    for slot in slots:
        if slot.miner_id not in pools_by_miner:
            pools_by_miner[slot.miner_id] = set()
        pools_by_miner[slot.miner_id].add(slot.pool_id)
    
    # Find intersection (pools present on ALL miners)
    if not pools_by_miner:
        return []
    
    common_pools = set(pools_by_miner[nano_miner_ids[0]])
    for miner_id in nano_miner_ids[1:]:
        if miner_id in pools_by_miner:
            common_pools &= pools_by_miner[miner_id]
        else:
            # If a miner has no slots synced, no pools are common
            return []
    
    return list(common_pools)
