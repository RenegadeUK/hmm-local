"""
Cloud Backup Integration
Support for Google Drive, OneDrive, and iCloud
"""
import os
import aiofiles
import aiohttp
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CloudBackupProvider:
    """Base class for cloud backup providers"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", False)
    
    async def upload(self, file_path: str, destination_name: str) -> bool:
        """Upload a file to cloud storage"""
        raise NotImplementedError
    
    async def test_connection(self) -> bool:
        """Test if the connection works"""
        raise NotImplementedError


class GoogleDriveProvider(CloudBackupProvider):
    """Google Drive backup provider using OAuth2"""
    
    async def upload(self, file_path: str, destination_name: str) -> bool:
        try:
            access_token = self.config.get("access_token")
            folder_id = self.config.get("folder_id")
            
            if not access_token:
                logger.error("Google Drive: No access token configured")
                return False
            
            # Read file
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            
            # Upload to Google Drive
            metadata = {
                'name': destination_name,
                'parents': [folder_id] if folder_id else []
            }
            
            headers = {
                'Authorization': f'Bearer {access_token}',
            }
            
            async with aiohttp.ClientSession() as session:
                # First, upload metadata
                async with session.post(
                    'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable',
                    json=metadata,
                    headers=headers
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Google Drive metadata upload failed: {resp.status}")
                        return False
                    
                    upload_url = resp.headers.get('Location')
                
                # Then upload file content
                async with session.put(
                    upload_url,
                    data=file_content,
                    headers={'Content-Type': 'application/octet-stream'}
                ) as resp:
                    if resp.status not in [200, 201]:
                        logger.error(f"Google Drive file upload failed: {resp.status}")
                        return False
            
            logger.info(f"✅ Uploaded {destination_name} to Google Drive")
            return True
            
        except Exception as e:
            logger.error(f"Google Drive upload error: {e}")
            return False
    
    async def test_connection(self) -> bool:
        try:
            access_token = self.config.get("access_token")
            if not access_token:
                return False
            
            headers = {'Authorization': f'Bearer {access_token}'}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://www.googleapis.com/drive/v3/about?fields=user',
                    headers=headers
                ) as resp:
                    return resp.status == 200
        except:
            return False


class OneDriveProvider(CloudBackupProvider):
    """OneDrive backup provider using Microsoft Graph API"""
    
    async def upload(self, file_path: str, destination_name: str) -> bool:
        try:
            access_token = self.config.get("access_token")
            folder_path = self.config.get("folder_path", "Backups")
            
            if not access_token:
                logger.error("OneDrive: No access token configured")
                return False
            
            # Read file
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            
            # Upload to OneDrive
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/octet-stream'
            }
            
            url = f'https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}/{destination_name}:/content'
            
            async with aiohttp.ClientSession() as session:
                async with session.put(url, data=file_content, headers=headers) as resp:
                    if resp.status not in [200, 201]:
                        logger.error(f"OneDrive upload failed: {resp.status}")
                        return False
            
            logger.info(f"✅ Uploaded {destination_name} to OneDrive")
            return True
            
        except Exception as e:
            logger.error(f"OneDrive upload error: {e}")
            return False
    
    async def test_connection(self) -> bool:
        try:
            access_token = self.config.get("access_token")
            if not access_token:
                return False
            
            headers = {'Authorization': f'Bearer {access_token}'}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://graph.microsoft.com/v1.0/me/drive',
                    headers=headers
                ) as resp:
                    return resp.status == 200
        except:
            return False


class iCloudProvider(CloudBackupProvider):
    """iCloud Drive backup provider (using WebDAV)"""
    
    async def upload(self, file_path: str, destination_name: str) -> bool:
        try:
            # iCloud uses WebDAV protocol
            apple_id = self.config.get("apple_id")
            app_password = self.config.get("app_password")  # App-specific password
            folder_path = self.config.get("folder_path", "MinerBackups")
            
            if not apple_id or not app_password:
                logger.error("iCloud: Missing credentials")
                return False
            
            # Read file
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            
            # WebDAV URL for iCloud Drive
            url = f'https://{apple_id}:{app_password}@p65-caldavws.icloud.com/published/2/{folder_path}/{destination_name}'
            
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    data=file_content,
                    headers={'Content-Type': 'application/octet-stream'}
                ) as resp:
                    if resp.status not in [200, 201, 204]:
                        logger.error(f"iCloud upload failed: {resp.status}")
                        return False
            
            logger.info(f"✅ Uploaded {destination_name} to iCloud Drive")
            return True
            
        except Exception as e:
            logger.error(f"iCloud upload error: {e}")
            return False
    
    async def test_connection(self) -> bool:
        try:
            apple_id = self.config.get("apple_id")
            app_password = self.config.get("app_password")
            
            if not apple_id or not app_password:
                return False
            
            url = f'https://{apple_id}:{app_password}@p65-caldavws.icloud.com/'
            
            async with aiohttp.ClientSession() as session:
                async with session.request('PROPFIND', url) as resp:
                    return resp.status in [200, 207]
        except:
            return False


class CloudBackupManager:
    """Manage all cloud backup providers"""
    
    def __init__(self):
        self.providers: Dict[str, CloudBackupProvider] = {}
    
    def configure_provider(self, provider_name: str, config: Dict[str, Any]):
        """Configure a cloud backup provider"""
        provider_map = {
            'google_drive': GoogleDriveProvider,
            'onedrive': OneDriveProvider,
            'icloud': iCloudProvider
        }
        
        if provider_name in provider_map:
            self.providers[provider_name] = provider_map[provider_name](config)
            logger.info(f"Configured {provider_name} backup provider")
    
    async def upload_backup(self, file_path: str, provider_name: str) -> bool:
        """Upload backup file to specified provider"""
        if provider_name not in self.providers:
            logger.error(f"Provider {provider_name} not configured")
            return False
        
        provider = self.providers[provider_name]
        if not provider.enabled:
            logger.warning(f"Provider {provider_name} is disabled")
            return False
        
        # Generate destination filename with timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_ext = Path(file_path).suffix
        destination_name = f"miner_backup_{timestamp}{file_ext}"
        
        return await provider.upload(file_path, destination_name)
    
    async def test_provider(self, provider_name: str) -> bool:
        """Test connection to provider"""
        if provider_name not in self.providers:
            return False
        
        return await self.providers[provider_name].test_connection()
    
    def get_enabled_providers(self) -> list:
        """Get list of enabled providers"""
        return [
            name for name, provider in self.providers.items()
            if provider.enabled
        ]


# Global instance
cloud_backup_manager = CloudBackupManager()
