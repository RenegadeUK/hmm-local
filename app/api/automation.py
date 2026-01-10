"""
Automation rules API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from pydantic import BaseModel

from core.database import get_db, AutomationRule


router = APIRouter()


class RuleCreate(BaseModel):
    name: str
    enabled: bool = True
    trigger_type: str
    trigger_config: dict
    action_type: str
    action_config: dict
    priority: int = 0


class RuleUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    trigger_type: str | None = None
    trigger_config: dict | None = None
    action_type: str | None = None
    action_config: dict | None = None
    priority: int | None = None


class RuleResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    trigger_type: str
    trigger_config: dict
    action_type: str
    action_config: dict
    priority: int
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[RuleResponse])
async def list_rules(db: AsyncSession = Depends(get_db)):
    """List all automation rules"""
    result = await db.execute(select(AutomationRule).order_by(AutomationRule.priority))
    rules = result.scalars().all()
    return rules


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Get rule by ID"""
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    return rule


@router.post("/", response_model=RuleResponse)
async def create_rule(rule: RuleCreate, db: AsyncSession = Depends(get_db)):
    """Create new automation rule"""
    # Check for duplicate name
    result = await db.execute(select(AutomationRule).where(AutomationRule.name == rule.name))
    existing_rule = result.scalar_one_or_none()
    if existing_rule:
        raise HTTPException(status_code=400, detail=f"Rule with name '{rule.name}' already exists")
    
    db_rule = AutomationRule(
        name=rule.name,
        enabled=rule.enabled,
        trigger_type=rule.trigger_type,
        trigger_config=rule.trigger_config,
        action_type=rule.action_type,
        action_config=rule.action_config,
        priority=rule.priority
    )
    
    db.add(db_rule)
    await db.commit()
    await db.refresh(db_rule)
    
    return db_rule


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: int, rule_update: RuleUpdate, db: AsyncSession = Depends(get_db)):
    """Update automation rule"""
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Check for duplicate name if name is being updated
    if rule_update.name is not None and rule_update.name != rule.name:
        name_check = await db.execute(select(AutomationRule).where(AutomationRule.name == rule_update.name))
        existing_rule = name_check.scalar_one_or_none()
        if existing_rule:
            raise HTTPException(status_code=400, detail=f"Rule with name '{rule_update.name}' already exists")
    
    # Update fields
    if rule_update.name is not None:
        rule.name = rule_update.name
    if rule_update.enabled is not None:
        rule.enabled = rule_update.enabled
    if rule_update.trigger_type is not None:
        rule.trigger_type = rule_update.trigger_type
    if rule_update.trigger_config is not None:
        rule.trigger_config = rule_update.trigger_config
    if rule_update.action_type is not None:
        rule.action_type = rule_update.action_type
    if rule_update.action_config is not None:
        rule.action_config = rule_update.action_config
    if rule_update.priority is not None:
        rule.priority = rule_update.priority
    
    await db.commit()
    await db.refresh(rule)
    
    return rule


@router.post("/{rule_id}/duplicate", response_model=RuleResponse)
async def duplicate_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Duplicate an automation rule"""
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    original_rule = result.scalar_one_or_none()
    
    if not original_rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Create a copy with "(Copy)" appended to the name
    duplicated_rule = AutomationRule(
        name=f"{original_rule.name} (Copy)",
        enabled=False,  # Start disabled for safety
        trigger_type=original_rule.trigger_type,
        trigger_config=original_rule.trigger_config,
        action_type=original_rule.action_type,
        action_config=original_rule.action_config,
        priority=original_rule.priority
    )
    
    db.add(duplicated_rule)
    await db.commit()
    await db.refresh(duplicated_rule)
    
    return duplicated_rule


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Delete automation rule"""
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    await db.delete(rule)
    await db.commit()
    
    return {"status": "deleted"}


@router.get("/triggers/types")
async def get_trigger_types():
    """Get available trigger types"""
    return {
        "types": [
            {"value": "price_threshold", "label": "Energy Price Threshold"},
            {"value": "time_window", "label": "Time Window"},
            {"value": "miner_overheat", "label": "Miner Overheating"}
        ]
    }


@router.get("/actions/types")
async def get_action_types():
    """Get available action types"""
    return {
        "types": [
            {"value": "apply_mode", "label": "Apply Miner Mode"},
            {"value": "switch_pool", "label": "Switch Mining Pool"},
            {"value": "send_alert", "label": "Send Alert"},
            {"value": "log_event", "label": "Log Event"}
        ]
    }
