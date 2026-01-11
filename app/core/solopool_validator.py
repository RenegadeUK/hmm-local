"""
Solopool Block Validator - Reconciles our block detection with Solopool's confirmed blocks.

This module provides hourly validation to catch any blocks we missed due to timing issues,
cache staleness, or other edge cases. It queries Solopool's /api/blocks endpoint and
cross-references with our HighDiffShare table.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import sqlite3
import requests
import os

logger = logging.getLogger(__name__)

SOLOPOOL_BLOCKS_ENDPOINTS = {
    'DGB': 'https://dgb-sha.solopool.org/api/blocks',
    'BCH': 'https://bch.solopool.org/api/blocks',
    'BTC': 'https://btc.solopool.org/api/blocks'
}


def get_solopool_blocks(coin: str, hours: int = 24) -> List[Dict]:
    """
    Fetch recent blocks from Solopool API.
    
    Args:
        coin: Coin symbol (DGB, BCH, BTC)
        hours: How many hours back to fetch (default 24)
    
    Returns:
        List of block dicts with keys: height, hash, miner, worker, timestamp,
        difficulty, shareDifficulty, orphan, reward
    """
    endpoint = SOLOPOOL_BLOCKS_ENDPOINTS.get(coin.upper())
    if not endpoint:
        logger.warning(f"No Solopool blocks endpoint configured for {coin}")
        return []
    
    try:
        response = requests.get(endpoint, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Combine immature and matured blocks
        all_blocks = []
        if 'immature' in data and data['immature']:
            all_blocks.extend(data['immature'])
        if 'matured' in data and data['matured']:
            all_blocks.extend(data['matured'])
        
        # Filter by time window
        cutoff = datetime.utcnow().timestamp() - (hours * 3600)
        recent_blocks = [b for b in all_blocks if b.get('timestamp', 0) >= cutoff]
        
        logger.info(f"Fetched {len(recent_blocks)} {coin} blocks from Solopool (last {hours}h)")
        return recent_blocks
        
    except Exception as e:
        logger.error(f"Error fetching Solopool blocks for {coin}: {e}")
        return []


def identify_our_blocks(solopool_blocks: List[Dict]) -> List[Dict]:
    """
    Filter Solopool blocks to only those from our miners.
    Matches by checking if any of our miner names contain the Solopool worker name.
    
    Args:
        solopool_blocks: List of blocks from get_solopool_blocks()
    
    Returns:
        List of blocks belonging to our miners, with 'our_miner_name' added
    """
    # Get all enabled miner names from database
    db_path = os.getenv("DB_PATH", "/config/data.db")
    if not os.path.exists(db_path):
        db_path = "config/data.db"
    
    our_miner_names = []
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT name FROM miners WHERE enabled = 1")
        our_miner_names = [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
    
    our_blocks = []
    for block in solopool_blocks:
        worker = block.get('worker', '').lower()
        
        if not worker:
            continue
        
        # Try to match worker name with our miner names
        # e.g., worker "Green" matches "03 - Green"
        matched_miner = None
        for miner_name in our_miner_names:
            if worker in miner_name.lower():
                matched_miner = miner_name
                break
        
        if matched_miner:
            block['our_miner_name'] = matched_miner
            our_blocks.append(block)
            logger.info(f"Found our block: {matched_miner} (worker: {worker}) - "
                       f"height {block['height']}, diff {block['shareDifficulty']:,}")
    
    return our_blocks


def check_block_in_database(
    miner_name: str, 
    coin: str, 
    share_difficulty: int,
    timestamp: int,
    tolerance_seconds: int = 300
) -> Optional[Tuple[int, bool]]:
    """
    Check if a block from Solopool exists in our HighDiffShare table.
    
    Args:
        miner_name: Our miner name (e.g. "03 - Green")
        coin: Coin symbol
        share_difficulty: Exact share difficulty from Solopool
        timestamp: Unix timestamp of the block
        tolerance_seconds: Time window to search (+/- seconds)
    
    Returns:
        Tuple of (share_id, was_block_solve) if found, None if not found
    """
    # Direct SQLite connection for sync operation
    # Use the main database path
    db_path = os.getenv("DB_PATH", "/config/data.db")
    if not os.path.exists(db_path):
        db_path = "config/data.db"
    
    conn = sqlite3.connect(db_path)
    try:
        # Convert Unix timestamp to datetime for comparison
        # SQLite stores timestamps as ISO format strings
        target_dt = datetime.fromtimestamp(timestamp)
        min_dt = datetime.fromtimestamp(timestamp - tolerance_seconds)
        max_dt = datetime.fromtimestamp(timestamp + tolerance_seconds)
        
        cursor = conn.execute("""
            SELECT id, was_block_solve, miner_id
            FROM high_diff_shares
            WHERE miner_name = ?
            AND coin = ?
            AND difficulty = ?
            AND datetime(timestamp) BETWEEN datetime(?) AND datetime(?)
            ORDER BY ABS(julianday(timestamp) - julianday(?)) ASC
            LIMIT 1
        """, (miner_name, coin, share_difficulty, min_dt.isoformat(), max_dt.isoformat(), target_dt.isoformat()))
        
        result = cursor.fetchone()
        if result:
            return (result[0], bool(result[1]), result[2])  # (id, was_block_solve, miner_id)
        return None
        
    finally:
        conn.close()


def validate_and_fix_blocks(coin: str, hours: int = 24, dry_run: bool = False) -> Dict:
    """
    Main validation function: fetch Solopool blocks and reconcile with our database.
    
    Args:
        coin: Coin symbol (DGB, BCH, BTC)
        hours: How many hours back to validate
        dry_run: If True, only report discrepancies without fixing
    
    Returns:
        Dict with validation results: {
            'checked': int,
            'matched': int,
            'missing': List[Dict],
            'fixed': List[Dict],
            'errors': List[str]
        }
    """
    results = {
        'checked': 0,
        'matched': 0,
        'missing': [],
        'fixed': [],
        'errors': []
    }
    
    # Fetch blocks from Solopool
    solopool_blocks = get_solopool_blocks(coin, hours)
    our_blocks = identify_our_blocks(solopool_blocks)
    
    results['checked'] = len(our_blocks)
    
    if not our_blocks:
        logger.info(f"No blocks found for our miners in last {hours}h")
        return results
    
    # Check each block against our database
    for block in our_blocks:
        miner_name = block['our_miner_name']
        share_diff = block['shareDifficulty']
        timestamp = block['timestamp']
        height = block['height']
        
        db_result = check_block_in_database(miner_name, coin, share_diff, timestamp)
        
        if db_result is None:
            # Block not in our database at all - this is BAD
            logger.error(f"MISSING BLOCK: {miner_name} {coin} block {height} "
                        f"(diff {share_diff:,}) not found in database!")
            results['missing'].append({
                'miner': miner_name,
                'coin': coin,
                'height': height,
                'difficulty': share_diff,
                'timestamp': timestamp,
                'reason': 'Share not recorded'
            })
            
        else:
            share_id, was_block_solve, miner_id = db_result
            
            if was_block_solve:
                # Correctly marked as block
                results['matched'] += 1
                logger.debug(f"✓ Block {height} correctly marked (share {share_id})")
                
            else:
                # In database but NOT marked as block - this is our bug!
                logger.warning(f"FALSE NEGATIVE: Share {share_id} ({miner_name}) "
                              f"is block {height} but was_block_solve=false")
                results['missing'].append({
                    'miner': miner_name,
                    'coin': coin,
                    'height': height,
                    'difficulty': share_diff,
                    'timestamp': timestamp,
                    'share_id': share_id,
                    'reason': 'Marked as miss instead of block'
                })
                
                # Fix it if not dry run
                if not dry_run:
                    try:
                        # Direct database update
                        db_path = os.getenv("DB_PATH", "/config/data.db")
                        if not os.path.exists(db_path):
                            db_path = "config/data.db"
                        
                        conn = sqlite3.connect(db_path)
                        try:
                            # Get actual network difficulty from Solopool block data
                            actual_network_diff = block.get('difficulty', share_diff)
                            
                            # Mark as block in high_diff_shares and update network_difficulty
                            conn.execute("""
                                UPDATE high_diff_shares 
                                SET was_block_solve = 1,
                                    network_difficulty = ?
                                WHERE id = ?
                            """, (actual_network_diff, share_id))
                            
                            # Add to BlockFound table if not exists (use actual network diff)
                            conn.execute("""
                                INSERT OR IGNORE INTO blocks_found 
                                (miner_id, miner_name, miner_type, coin, pool_name, difficulty, 
                                 network_difficulty, hashrate, hashrate_unit, 
                                 miner_mode, timestamp)
                                SELECT miner_id, miner_name, miner_type, coin, pool_name, 
                                       difficulty, ?,
                                       hashrate, hashrate_unit, miner_mode, timestamp
                                FROM high_diff_shares
                                WHERE id = ?
                            """, (actual_network_diff, share_id))
                            
                            conn.commit()
                        finally:
                            conn.close()
                        
                        results['fixed'].append({
                            'share_id': share_id,
                            'miner': miner_name,
                            'height': height
                        })
                        logger.info(f"✓ Fixed share {share_id} - marked as block")
                    except Exception as e:
                        error_msg = f"Failed to fix share {share_id}: {e}"
                        logger.error(error_msg)
                        results['errors'].append(error_msg)
    
    return results


def run_validation_for_all_coins(hours: int = 24, dry_run: bool = False) -> Dict:
    """
    Run validation across all supported coins.
    
    Args:
        hours: How many hours back to validate
        dry_run: If True, only report discrepancies without fixing
    
    Returns:
        Dict mapping coin -> validation results
    """
    logger.info(f"Starting Solopool validation (last {hours}h, dry_run={dry_run})")
    
    all_results = {}
    for coin in SOLOPOOL_BLOCKS_ENDPOINTS.keys():
        logger.info(f"Validating {coin}...")
        all_results[coin] = validate_and_fix_blocks(coin, hours, dry_run)
    
    # Summary
    total_checked = sum(r['checked'] for r in all_results.values())
    total_matched = sum(r['matched'] for r in all_results.values())
    total_missing = sum(len(r['missing']) for r in all_results.values())
    total_fixed = sum(len(r['fixed']) for r in all_results.values())
    
    logger.info(f"Validation complete: {total_checked} blocks checked, "
               f"{total_matched} matched, {total_missing} discrepancies found, "
               f"{total_fixed} fixed")
    
    return all_results


if __name__ == '__main__':
    # Run validation in dry-run mode
    logging.basicConfig(level=logging.INFO)
    results = run_validation_for_all_coins(hours=48, dry_run=True)
    
    print("\n=== VALIDATION RESULTS ===")
    for coin, result in results.items():
        print(f"\n{coin}:")
        print(f"  Checked: {result['checked']}")
        print(f"  Matched: {result['matched']}")
        print(f"  Missing: {len(result['missing'])}")
        if result['missing']:
            for miss in result['missing']:
                print(f"    - {miss['miner']} block {miss['height']}: {miss['reason']}")
