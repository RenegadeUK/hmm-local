"""
Fix the 03 - Green DGB block that was incorrectly marked as a miss
The share was accepted by Solopool as a block, but our network difficulty was stale
"""
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker, HighDiffShare, BlockFound


async def fix_green_block():
    async with async_session_maker() as db:
        # Find the share (ID 371, miner_id 4, difficulty 1009141169)
        result = await db.execute(
            select(HighDiffShare).where(
                HighDiffShare.id == 371
            )
        )
        share = result.scalar_one_or_none()
        
        if not share:
            print("❌ Share not found")
            return
        
        print(f"Found share: {share.miner_name} - {share.difficulty:,.0f} / {share.network_difficulty:,.0f}")
        print(f"Currently marked as block solve: {share.was_block_solve}")
        
        # Update to mark as block solve
        share.was_block_solve = True
        
        # Also ensure it's in blocks_found table
        existing_block = await db.execute(
            select(BlockFound).where(
                BlockFound.miner_id == share.miner_id,
                BlockFound.timestamp == share.timestamp,
                BlockFound.difficulty == share.difficulty
            )
        )
        
        if not existing_block.scalar_one_or_none():
            print("Adding to blocks_found table...")
            block = BlockFound(
                miner_id=share.miner_id,
                miner_name=share.miner_name,
                miner_type=share.miner_type,
                coin=share.coin,
                pool_name=share.pool_name,
                difficulty=share.difficulty,
                network_difficulty=share.difficulty,  # Use share diff since it solved the block
                block_height=None,
                block_reward=None,
                hashrate=share.hashrate,
                hashrate_unit=share.hashrate_unit,
                miner_mode=share.miner_mode,
                timestamp=share.timestamp
            )
            db.add(block)
        else:
            print("Already in blocks_found table")
        
        await db.commit()
        print("✅ Fixed! Share now marked as block solve")


if __name__ == "__main__":
    asyncio.run(fix_green_block())
