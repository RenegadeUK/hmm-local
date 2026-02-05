"""
Pool Templates API

Provides access to pre-configured pool templates from all registered plugins.
Templates define validated pool configurations that work across the platform.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging

from integrations.pool_registry import PoolRegistry

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/pool-templates", response_model=List[Dict[str, Any]])
async def get_all_pool_templates():
    """
    Get all available pool templates from all registered plugins.
    
    Returns:
        List of PoolTemplate objects serialized as dictionaries
    """
    try:
        PoolRegistry._ensure_initialized()
        
        all_templates = []
        
        for pool_type, pool_integration in PoolRegistry._pools.items():
            try:
                templates = pool_integration.get_pool_templates()
                
                for template in templates:
                    # Convert PoolTemplate to dict and add pool_type
                    template_dict = {
                        "pool_type": pool_type,
                        "pool_display_name": pool_integration.display_name,
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
                    all_templates.append(template_dict)
                    
            except Exception as e:
                logger.error(f"Error getting templates from {pool_type}: {e}")
                continue
        
        return all_templates
        
    except Exception as e:
        logger.error(f"Error fetching pool templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/pool-templates/{pool_type}", response_model=List[Dict[str, Any]])
async def get_pool_templates_by_type(pool_type: str):
    """
    Get templates for a specific pool type.
    
    Args:
        pool_type: Pool type (solopool, braiins, mmfp, etc.)
    
    Returns:
        List of PoolTemplate objects for that pool type
    """
    try:
        PoolRegistry._ensure_initialized()
        
        pool_integration = PoolRegistry.get(pool_type)
        if not pool_integration:
            raise HTTPException(status_code=404, detail=f"Pool type '{pool_type}' not found")
        
        templates = pool_integration.get_pool_templates()
        
        result = []
        for template in templates:
            template_dict = {
                "pool_type": pool_type,
                "pool_display_name": pool_integration.display_name,
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
    Get templates for a specific pool type and coin.
    
    Args:
        pool_type: Pool type (solopool, braiins, etc.)
        coin: Coin symbol (BTC, DGB, BCH, etc.)
    
    Returns:
        List of PoolTemplate objects filtered by coin
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
                detail=f"No templates found for {pool_type} with coin {coin}"
            )
        
        return filtered
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching templates for {pool_type}/{coin}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
