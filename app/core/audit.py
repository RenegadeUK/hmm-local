"""
Audit logging service for tracking configuration changes
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import AuditLog
from fastapi import Request

logger = logging.getLogger(__name__)


class AuditLogger:
    """Service for creating audit log entries"""
    
    def __init__(self, db: AsyncSession, request: Optional[Request] = None):
        self.db = db
        self.request = request
    
    async def log(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[int] = None,
        resource_name: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        user: str = "system"
    ):
        """
        Create an audit log entry
        
        Args:
            action: Action performed (create, update, delete, execute, enable, disable)
            resource_type: Type of resource (miner, pool, strategy, automation, etc)
            resource_id: ID of the resource
            resource_name: Name of the resource
            changes: Dictionary of changes (before/after values)
            status: success or failure
            error_message: Error message if status is failure
            user: User who performed the action (default: system)
        """
        try:
            # Extract IP and user agent from request if available
            ip_address = None
            user_agent = None
            
            if self.request:
                # Try to get real IP from proxy headers
                ip_address = (
                    self.request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                    self.request.headers.get("X-Real-IP") or
                    self.request.client.host if self.request.client else None
                )
                user_agent = self.request.headers.get("User-Agent")
            
            audit_entry = AuditLog(
                timestamp=datetime.utcnow(),
                user=user,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                changes=changes,
                ip_address=ip_address,
                user_agent=user_agent,
                status=status,
                error_message=error_message
            )
            
            self.db.add(audit_entry)
            await self.db.commit()
            
            logger.info(
                f"Audit: {action} {resource_type} "
                f"{'#' + str(resource_id) if resource_id else ''} "
                f"({resource_name or 'N/A'}) by {user} - {status}"
            )
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            # Don't raise - audit logging shouldn't break the application


def create_change_dict(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a changes dictionary showing before/after values
    
    Args:
        before: Dictionary of values before change
        after: Dictionary of values after change
    
    Returns:
        Dictionary with changed fields
    """
    changes = {}
    
    # Find changed fields
    all_keys = set(before.keys()) | set(after.keys())
    
    for key in all_keys:
        before_val = before.get(key)
        after_val = after.get(key)
        
        if before_val != after_val:
            changes[key] = {
                "before": before_val,
                "after": after_val
            }
    
    return changes


async def log_audit(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    resource_name: Optional[str] = None,
    changes: Optional[Dict[str, Any]] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    user: str = "system",
    request: Optional[Request] = None
):
    """
    Convenience function to create an audit log entry
    
    Usage:
        await log_audit(
            db, "create", "miner",
            resource_id=miner.id,
            resource_name=miner.name,
            changes={"name": {"before": None, "after": "Bitaxe01"}}
        )
    """
    auditor = AuditLogger(db, request)
    await auditor.log(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        changes=changes,
        status=status,
        error_message=error_message,
        user=user
    )
