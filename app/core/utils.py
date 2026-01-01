"""
Utility functions for Home Miner Manager
"""
from datetime import datetime


def format_time_elapsed(start_time: datetime, compact: bool = True) -> str:
    """
    Format elapsed time since start_time in compact P2Pool-style format.
    
    Args:
        start_time: The starting datetime (UTC)
        compact: If True, uses compact format (1m 35s, 1h 10m, 1d 10h 32m)
                 If False, uses format with "ago" suffix
    
    Returns:
        Formatted time string (e.g., "1m 35s", "1h 10m", "1d 10h 32m")
        Returns None if start_time is None
    
    Examples:
        - 45 seconds: "45s"
        - 5 minutes 30 seconds: "5m 30s"
        - 2 hours 15 minutes: "2h 15m"
        - 1 day 10 hours 32 minutes: "1d 10h 32m"
        - 3 days 0 hours 0 minutes: "3d"
    """
    if not start_time:
        return None
    
    elapsed = datetime.utcnow() - start_time
    total_seconds = int(elapsed.total_seconds())
    
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if days > 0:
        if hours > 0 and minutes > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{days}d {hours}h"
        else:
            return f"{days}d"
    elif hours > 0:
        if minutes > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{hours}h"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"
