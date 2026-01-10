"""
Notification service for sending alerts via Telegram and Discord
"""
import aiohttp
import asyncio
from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import AsyncSessionLocal, NotificationConfig, NotificationLog


class NotificationService:
    """Service for sending notifications to various channels"""
    
    async def send_notification(
        self,
        channel_type: str,
        message: str,
        alert_type: str = "general"
    ) -> bool:
        """
        Send notification to specified channel
        
        Args:
            channel_type: telegram or discord
            message: Message to send
            alert_type: Type of alert (for logging)
        
        Returns:
            True if sent successfully, False otherwise
        """
        async with AsyncSessionLocal() as db:
            # Get channel config
            result = await db.execute(
                select(NotificationConfig).where(
                    NotificationConfig.channel_type == channel_type,
                    NotificationConfig.enabled == True
                )
            )
            channel = result.scalar_one_or_none()
            
            if not channel:
                return False
            
            # Send based on channel type
            success = False
            error = None
            
            try:
                if channel_type == "telegram":
                    success = await self._send_telegram(channel.config, message)
                elif channel_type == "discord":
                    success = await self._send_discord(channel.config, message)
                else:
                    error = f"Unknown channel type: {channel_type}"
            except Exception as e:
                error = str(e)
                success = False
            
            # Log the notification attempt
            log = NotificationLog(
                timestamp=datetime.utcnow(),
                channel_type=channel_type,
                alert_type=alert_type,
                message=message,
                success=success,
                error=error
            )
            db.add(log)
            await db.commit()
            
            return success
    
    async def _send_telegram(self, config: dict, message: str) -> bool:
        """Send message via Telegram Bot API"""
        bot_token = config.get("bot_token")
        chat_id = config.get("chat_id")
        
        if not bot_token or not chat_id:
            raise ValueError("Telegram bot_token and chat_id are required")
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    return True
                else:
                    error_data = await response.text()
                    raise Exception(f"Telegram API error: {error_data}")
    
    async def _send_discord(self, config: dict, message: str) -> bool:
        """Send message via Discord Webhook"""
        webhook_url = config.get("webhook_url")
        
        if not webhook_url:
            raise ValueError("Discord webhook_url is required")
        
        payload = {
            "content": message,
            "username": "v0 Miner Controller"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as response:
                if response.status in [200, 204]:
                    return True
                else:
                    error_data = await response.text()
                    raise Exception(f"Discord webhook error: {error_data}")
    
    async def send_to_all_channels(self, message: str, alert_type: str = "general") -> dict:
        """
        Send notification to all enabled channels
        
        Returns:
            Dict with results for each channel: {channel_type: success}
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(NotificationConfig).where(NotificationConfig.enabled == True)
            )
            channels = result.scalars().all()
            
            results = {}
            for channel in channels:
                success = await self.send_notification(
                    channel_type=channel.channel_type,
                    message=message,
                    alert_type=alert_type
                )
                results[channel.channel_type] = success
            
            return results


# Global service instance
notification_service = NotificationService()


async def send_alert(message: str, alert_type: str = "general"):
    """
    Convenience function to send alert to all enabled channels
    
    Args:
        message: Alert message
        alert_type: Type of alert (high_temperature, block_found)
    """
    await notification_service.send_to_all_channels(message, alert_type)


# Default alert configurations that should always exist
# Note: label and description are frontend-only (in notifications.html)
DEFAULT_ALERT_TYPES = [
    {"alert_type": "high_temperature", "config": {"threshold_celsius": 75}, "enabled": True},
    {"alert_type": "block_found", "config": {}, "enabled": True}
]


async def ensure_default_alerts():
    """
    Ensure all default alert types exist in the database.
    Adds any missing alert types during startup.
    """
    from core.database import AlertConfig
    
    async with AsyncSessionLocal() as db:
        try:
            # Get existing alert types
            result = await db.execute(select(AlertConfig))
            existing_alerts = result.scalars().all()
            existing_types = {alert.alert_type for alert in existing_alerts}
            
            # Add missing alert types
            for default_alert in DEFAULT_ALERT_TYPES:
                if default_alert["alert_type"] not in existing_types:
                    new_alert = AlertConfig(
                        alert_type=default_alert["alert_type"],
                        config=default_alert["config"],
                        enabled=default_alert["enabled"]
                    )
                    db.add(new_alert)
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise e
