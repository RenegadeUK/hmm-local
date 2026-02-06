"""
Platform Update Management API
Checks GitHub Container Registry for new image versions and manages updates
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from pathlib import Path
import subprocess
import logging
import httpx
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from core.database import get_db
from core.audit import log_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/updates", tags=["Platform Updates"])

# GitHub Container Registry configuration
GHCR_OWNER = "renegadeuk"
GHCR_REPO = "hmm-local"
GHCR_IMAGE = f"ghcr.io/{GHCR_OWNER}/{GHCR_REPO}"
GITHUB_API_URL = f"https://api.github.com/repos/{GHCR_OWNER}/{GHCR_REPO}"

# Local paths
GIT_COMMIT_FILE = Path("/app/.git_commit")
CONTAINER_NAME = "hmm-local"  # Default, will be detected


class VersionInfo(BaseModel):
    current_image: str
    current_tag: str
    current_commit: str
    current_message: Optional[str]
    current_date: Optional[str]
    latest_commit: str
    latest_tag: str
    latest_message: str
    latest_date: str
    latest_image: str
    update_available: bool
    commits_behind: int


class CommitInfo(BaseModel):
    sha: str
    sha_short: str
    message: str
    author: str
    date: str
    url: str


class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    network_mode: str
    ip_address: Optional[str]
    volumes: Dict[str, str]
    environment: Dict[str, str]
    restart_policy: str


class UpdateStatus(BaseModel):
    status: str  # 'idle', 'checking', 'pulling', 'stopping', 'starting', 'success', 'error'
    message: str
    progress: int  # 0-100
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]


# Global update status tracker
update_status = UpdateStatus(
    status="idle",
    message="No update in progress",
    progress=0,
    started_at=None,
    completed_at=None,
    error=None
)


def get_current_container_name() -> str:
    """Detect current container name from hostname"""
    try:
        import socket
        hostname = socket.gethostname()
        # Docker uses container ID as hostname, but we want the name
        # Try to find it via docker inspect
        result = subprocess.run(
            ["docker", "ps", "--filter", f"id={hostname}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return CONTAINER_NAME
    except:
        return CONTAINER_NAME


def get_container_info(container_name: Optional[str] = None) -> ContainerInfo:
    """Get current container configuration via docker inspect"""
    try:
        if not container_name:
            container_name = get_current_container_name()
        
        result = subprocess.run(
            ["docker", "inspect", container_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise Exception(f"Failed to inspect container: {result.stderr}")
        
        data = json.loads(result.stdout)[0]
        
        # Extract network settings
        network_mode = data["HostConfig"]["NetworkMode"]
        ip_address = None
        if "Networks" in data["NetworkSettings"]:
            for net_name, net_data in data["NetworkSettings"]["Networks"].items():
                if net_data.get("IPAddress"):
                    ip_address = net_data["IPAddress"]
                    break
        
        # Extract volumes
        volumes = {}
        if "Mounts" in data:
            for mount in data["Mounts"]:
                volumes[mount["Source"]] = mount["Destination"]
        
        # Extract environment variables
        env_dict = {}
        if "Config" in data and "Env" in data["Config"]:
            for env in data["Config"]["Env"]:
                if "=" in env:
                    key, value = env.split("=", 1)
                    env_dict[key] = value
        
        # Extract restart policy
        restart_policy = data["HostConfig"]["RestartPolicy"]["Name"]
        
        return ContainerInfo(
            id=data["Id"][:12],
            name=data["Name"].lstrip("/"),
            image=data["Config"]["Image"],
            network_mode=network_mode,
            ip_address=ip_address,
            volumes=volumes,
            environment=env_dict,
            restart_policy=restart_policy
        )
        
    except Exception as e:
        logger.error(f"Error getting container info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get container info: {str(e)}")


def get_current_commit() -> tuple[str, Optional[str], Optional[str]]:
    """Get current running commit hash from build"""
    try:
        if GIT_COMMIT_FILE.exists():
            commit_info = GIT_COMMIT_FILE.read_text().strip()
            # Format: "main-abc1234" or just "abc1234"
            if "-" in commit_info:
                branch, commit_hash = commit_info.split("-", 1)
            else:
                commit_hash = commit_info
            
            logger.info(f"Current commit from file: {commit_hash}")
            return commit_hash, None, None
        
        return "unknown", None, None
        
    except Exception as e:
        logger.error(f"Error getting current commit: {e}")
        return "unknown", None, None


async def get_github_commits(limit: int = 10) -> List[CommitInfo]:
    """Fetch recent commits from GitHub"""
    try:
        url = f"{GITHUB_API_URL}/commits"
        params = {
            "sha": "main",
            "per_page": limit
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            commits = []
            data = response.json()
            
            for commit_data in data:
                commit = CommitInfo(
                    sha=commit_data["sha"],
                    sha_short=commit_data["sha"][:7],
                    message=commit_data["commit"]["message"].split("\n")[0],  # First line only
                    author=commit_data["commit"]["author"]["name"],
                    date=commit_data["commit"]["author"]["date"],
                    url=commit_data["html_url"]
                )
                commits.append(commit)
            
            return commits
            
    except Exception as e:
        logger.error(f"Error fetching GitHub commits: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch commits from GitHub: {str(e)}")


@router.get("/container")
async def get_current_container() -> ContainerInfo:
    """Get current container configuration"""
    return get_container_info()


@router.get("/check")
async def check_for_updates() -> VersionInfo:
    """Check if updates are available from GitHub"""
    try:
        # Get current version
        current_commit, current_message, current_date = get_current_commit()
        
        # Get current container image
        try:
            container = get_container_info()
            current_image = container.image
            # Extract tag from image (e.g., "ghcr.io/renegadeuk/hmm-local:main-abc1234")
            current_tag = current_image.split(":")[-1] if ":" in current_image else "latest"
        except:
            current_image = f"{GHCR_IMAGE}:unknown"
            current_tag = "unknown"
        
        # Get latest commit from GitHub
        commits = await get_github_commits(limit=1)
        if not commits:
            raise HTTPException(status_code=500, detail="Could not fetch latest version from GitHub")
        
        latest = commits[0]
        latest_tag = f"main-{latest.sha_short}"
        latest_image = f"{GHCR_IMAGE}:{latest_tag}"
        
        # Check if update available
        update_available = current_commit != "unknown" and not current_commit.startswith(latest.sha_short)
        
        # Count commits behind (check if current commit is in recent history)
        commits_behind = 0
        if update_available and current_commit != "unknown":
            all_commits = await get_github_commits(limit=50)
            found_current = False
            for idx, commit in enumerate(all_commits):
                if commit.sha.startswith(current_commit):
                    found_current = True
                    commits_behind = idx
                    break
            if not found_current:
                commits_behind = len(all_commits)  # More than 50 behind
        
        return VersionInfo(
            current_image=current_image,
            current_tag=current_tag,
            current_commit=current_commit,
            current_message=current_message,
            current_date=current_date,
            latest_commit=latest.sha,
            latest_tag=latest_tag,
            latest_message=latest.message,
            latest_date=latest.date,
            latest_image=latest_image,
            update_available=update_available,
            commits_behind=commits_behind
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changelog")
async def get_changelog(limit: int = 20) -> List[CommitInfo]:
    """Get recent commits/changelog from GitHub"""
    try:
        commits = await get_github_commits(limit=limit)
        return commits
        
    except Exception as e:
        logger.error(f"Error fetching changelog: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_update_status() -> UpdateStatus:
    """Get current update operation status"""
    return update_status


@router.post("/apply")
async def apply_update(db: AsyncSession = Depends(get_db)):
    """
    Apply platform update by pulling latest image and recreating container
    
    NOTE: This will restart the container with the same configuration!
    Your /config data and network settings will be preserved.
    """
    global update_status
    
    if update_status.status not in ["idle", "success", "error"]:
        raise HTTPException(status_code=409, detail="Update already in progress")
    
    # Get version info to ensure update is available
    version_info = await check_for_updates()
    if not version_info.update_available:
        raise HTTPException(status_code=400, detail="Already on latest version")
    
    # Reset status
    update_status = UpdateStatus(
        status="checking",
        message="Preparing update...",
        progress=10,
        started_at=datetime.utcnow().isoformat(),
        completed_at=None,
        error=None
    )
    
    # Audit log
    await log_audit(
        db=db,
        action="update",
        resource_type="platform",
        resource_name="hmm-local",
        changes={
            "from_image": version_info.current_image,
            "to_image": version_info.latest_image,
            "commits_behind": version_info.commits_behind
        }
    )
    
    # Start update in background
    asyncio.create_task(run_update(db, version_info.latest_image))
    
    return {
        "success": True,
        "message": "Update started. Container will restart shortly.",
        "new_image": version_info.latest_image,
        "status": update_status
    }


async def run_update(db: AsyncSession, new_image: str):
    """Background task to perform the actual update"""
    global update_status
    
    try:
        # Get current container configuration
        update_status.status = "checking"
        update_status.message = "Reading current container configuration..."
        update_status.progress = 20
        logger.info("Getting current container config...")
        
        container = get_container_info()
        logger.info(f"Current container: {container.name}, Image: {container.image}")
        
        # Step 1: Pull new image
        update_status.status = "pulling"
        update_status.message = f"Pulling new image: {new_image}..."
        update_status.progress = 40
        logger.info(f"Pulling image: {new_image}")
        
        result = subprocess.run(
            ["docker", "pull", new_image],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes
        )
        
        if result.returncode != 0:
            raise Exception(f"Failed to pull image: {result.stderr}")
        
        logger.info(f"Image pulled successfully")
        
        # Step 2: Stop current container
        update_status.status = "stopping"
        update_status.message = "Stopping current container..."
        update_status.progress = 60
        logger.info(f"Stopping container: {container.name}")
        
        result = subprocess.run(
            ["docker", "stop", container.name],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            raise Exception(f"Failed to stop container: {result.stderr}")
        
        # Step 3: Remove old container
        logger.info(f"Removing old container: {container.name}")
        
        result = subprocess.run(
            ["docker", "rm", container.name],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.warning(f"Failed to remove container (non-fatal): {result.stderr}")
        
        # Step 4: Start new container with same configuration
        update_status.status = "starting"
        update_status.message = "Starting updated container..."
        update_status.progress = 80
        logger.info(f"Starting new container with image: {new_image}")
        
        # Build docker run command
        docker_cmd = ["docker", "run", "-d", "--name", container.name]
        
        # Add network configuration
        if container.network_mode and container.network_mode != "default":
            docker_cmd.extend(["--network", container.network_mode])
        
        if container.ip_address:
            docker_cmd.extend(["--ip", container.ip_address])
        
        # Add volumes
        for source, dest in container.volumes.items():
            docker_cmd.extend(["-v", f"{source}:{dest}"])
        
        # Add environment variables
        for key, value in container.environment.items():
            # Skip system env vars
            if key not in ["PATH", "HOSTNAME"]:
                docker_cmd.extend(["-e", f"{key}={value}"])
        
        # Add restart policy
        if container.restart_policy and container.restart_policy != "no":
            docker_cmd.extend(["--restart", container.restart_policy])
        
        # Add new image
        docker_cmd.append(new_image)
        
        logger.info(f"Docker command: {' '.join(docker_cmd)}")
        
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            raise Exception(f"Failed to start new container: {result.stderr}")
        
        new_container_id = result.stdout.strip()
        logger.info(f"New container started: {new_container_id}")
        
        # Success!
        update_status.status = "success"
        update_status.message = "Update completed successfully! New container is running."
        update_status.progress = 100
        update_status.completed_at = datetime.utcnow().isoformat()
        
        # Audit log success
        await log_audit(
            db=db,
            action="update",
            resource_type="platform",
            resource_name="hmm-local",
            changes={"status": "success", "new_container_id": new_container_id}
        )
        
        logger.info("Platform update completed successfully")
        
    except subprocess.TimeoutExpired:
        update_status.status = "error"
        update_status.message = "Update timed out"
        update_status.error = "Operation took too long and was cancelled"
        update_status.completed_at = datetime.utcnow().isoformat()
        logger.error("Update timed out")
        
    except Exception as e:
        update_status.status = "error"
        update_status.message = "Update failed"
        update_status.error = str(e)
        update_status.completed_at = datetime.utcnow().isoformat()
        logger.error(f"Update failed: {e}")
        
        # Audit log failure
        try:
            await log_audit(
                db=db,
                action="update",
                resource_type="platform",
                resource_name="hmm-local",
                changes={"status": "error", "error": str(e)}
            )
        except:
            pass
