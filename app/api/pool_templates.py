"""
Pool Templates API

Provides access to pool configurations from /config/pools/ loaded by drivers.
Templates are YAML files that reference drivers in /config/drivers/.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging

from core.pool_loader import get_pool_loader

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/pool-templates", response_model=List[Dict[str, Any]])
async def get_all_pool_templates():
    """
    Get all available pool configurations from /config/pools/.
    
    Returns:
        List of pool configs as PoolTemplate-compatible dictionaries
    """
    try:
        loader = get_pool_loader()
        templates = loader.get_all_pool_templates()
        
        result = []
        for template in templates:
            # Get pool config to access driver info
            config = loader.get_pool_config(template.template_id)
            if not config:
                continue
            
            # Get driver display name
            driver = loader.get_driver(config.driver)
            driver_display = driver.display_name if driver and hasattr(driver, 'display_name') else config.driver
            
            template_dict = {
                "pool_type": config.driver,
                "pool_display_name": driver_display,
                "template_id": template.template_id,
                "display_name": template.display_name,
                "url": template.url,
                "port": template.port,
                "coin": template.coin,
                "mining_model": template.mining_model.value,
                "region": template.region,
                "requires_auth": template.requires_auth,
                "supports_shares": template.supports_shares,
                "supports_earnings": template.supports_earnings,
                "supports_balance": template.supports_balance,
                "description": template.description,
                "fee_percent": template.fee_percent
            }
            result.append(template_dict)
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching pool templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/pool-templates/{pool_type}", response_model=List[Dict[str, Any]])
async def get_pool_templates_by_type(pool_type: str):
    """
    Get templates for a specific driver type.
    
    Args:
        pool_type: Driver type (solopool, braiins, mmfp, etc.)
    
    Returns:
        List of pool configs that use that driver
    """
    try:
        loader = get_pool_loader()
        
        # Check driver exists
        driver = loader.get_driver(pool_type)
        if not driver:
            raise HTTPException(status_code=404, detail=f"Driver '{pool_type}' not found")
        
        templates = loader.get_templates_by_driver(pool_type)
        
        result = []
        for template in templates:
            driver_display = driver.display_name if hasattr(driver, 'display_name') else pool_type
            
            template_dict = {
                "pool_type": pool_type,
                "pool_display_name": driver_display,
                "template_id": template.template_id,
                "display_name": template.display_name,
                "url": template.url,
                "port": template.port,
                "coin": template.coin,
                "mining_model": template.mining_model.value,
                "region": template.region,
                "requires_auth": template.requires_auth,
                "supports_shares": template.supports_shares,
                "supports_earnings": template.supports_earnings,
                "supports_balance": template.supports_balance,
                "description": template.description,
                "fee_percent": template.fee_percent
            }
            result.append(template_dict)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching templates for {pool_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/pool-templates/{pool_type}/{coin}", response_model=List[Dict[str, Any]])
async def get_pool_templates_by_coin(pool_type: str, coin: str):
    """
    Get templates for a specific driver type and coin.
    
    Args:
        pool_type: Driver type (solopool, braiins, etc.)
        coin: Coin symbol (BTC, DGB, BCH, etc.)
    
    Returns:
        List of pool configs filtered by driver and coin
    """
    try:
        # Get all templates for pool type
        templates = await get_pool_templates_by_type(pool_type)
        
        # Filter by coin (case-insensitive)
        coin_upper = coin.upper()
        filtered = [t for t in templates if t["coin"].upper() == coin_upper]
        
        if not filtered:
            raise HTTPException(
                status_code=404,
                detail=f"No pool configs found for driver '{pool_type}' with coin {coin}"
            )
        
        return filtered
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching templates for {pool_type}/{coin}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

        raise HTTPException(status_code=500, detail=str(e))
