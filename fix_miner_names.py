#!/usr/bin/env python3
"""
Fix miner names in leaderboard tables to match current miner names.
This prevents duplicate entries in Coin Hunter leaderboard when miners are renamed.

Usage:
    python fix_miner_names.py --preview  # Show what will change
    python fix_miner_names.py --execute  # Apply changes
"""
import sqlite3
import sys
from datetime import datetime

DB_PATH = "/config/data.db"

def get_miner_name_mappings(conn):
    """Get mapping of miner_id -> current_name from miners table"""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM miners ORDER BY id")
    return {row[0]: row[1] for row in cursor.fetchall()}

def preview_changes(conn, miner_mappings):
    """Show what will be changed without modifying anything"""
    cursor = conn.cursor()
    
    print("\n" + "="*80)
    print("PREVIEW MODE - No changes will be made")
    print("="*80)
    
    # Check blocks_found
    print("\n📦 BLOCKS_FOUND TABLE:")
    cursor.execute("""
        SELECT miner_id, miner_name, COUNT(*) as count 
        FROM blocks_found 
        GROUP BY miner_id, miner_name
        ORDER BY miner_id
    """)
    
    blocks_changes = []
    for miner_id, old_name, count in cursor.fetchall():
        current_name = miner_mappings.get(miner_id)
        if current_name and old_name != current_name:
            blocks_changes.append((miner_id, old_name, current_name, count))
            print(f"  Miner ID {miner_id}: '{old_name}' -> '{current_name}' ({count} blocks)")
    
    if not blocks_changes:
        print("  ✅ No changes needed - all names match current miner names")
    
    # Check high_diff_shares
    print("\n🏆 HIGH_DIFF_SHARES TABLE:")
    cursor.execute("""
        SELECT miner_id, miner_name, COUNT(*) as count 
        FROM high_diff_shares 
        GROUP BY miner_id, miner_name
        ORDER BY miner_id
    """)
    
    shares_changes = []
    for miner_id, old_name, count in cursor.fetchall():
        current_name = miner_mappings.get(miner_id)
        if current_name and old_name != current_name:
            shares_changes.append((miner_id, old_name, current_name, count))
            print(f"  Miner ID {miner_id}: '{old_name}' -> '{current_name}' ({count} shares)")
    
    if not shares_changes:
        print("  ✅ No changes needed - all names match current miner names")
    
    # Check for duplicate miner_id entries (the problem we're fixing)
    print("\n⚠️  DUPLICATE DETECTION (entries with same miner_id, different names):")
    cursor.execute("""
        SELECT miner_id, COUNT(DISTINCT miner_name) as name_count,
               GROUP_CONCAT(DISTINCT miner_name) as names
        FROM blocks_found
        GROUP BY miner_id
        HAVING name_count > 1
    """)
    
    duplicates = cursor.fetchall()
    if duplicates:
        print("  🚨 DUPLICATES FOUND IN COIN HUNTER:")
        for miner_id, count, names in duplicates:
            current_name = miner_mappings.get(miner_id, "Unknown")
            print(f"    Miner ID {miner_id} (current name: '{current_name}'):")
            print(f"      Has {count} different names: {names}")
            print(f"      This will show as {count} separate entries in Coin Hunter!")
    else:
        print("  ✅ No duplicates found")
    
    print("\n" + "="*80)
    print(f"SUMMARY:")
    print(f"  Blocks to update: {sum(c[3] for c in blocks_changes)}")
    print(f"  Shares to update: {sum(c[3] for c in shares_changes)}")
    print("="*80)
    
    return len(blocks_changes) > 0 or len(shares_changes) > 0

def execute_changes(conn, miner_mappings):
    """Apply the name changes to the database"""
    cursor = conn.cursor()
    
    print("\n" + "="*80)
    print("EXECUTE MODE - Applying changes to database")
    print("="*80)
    
    total_blocks_updated = 0
    total_shares_updated = 0
    
    # Update blocks_found
    print("\n📦 Updating BLOCKS_FOUND table...")
    for miner_id, current_name in miner_mappings.items():
        cursor.execute("""
            UPDATE blocks_found 
            SET miner_name = ? 
            WHERE miner_id = ? AND miner_name != ?
        """, (current_name, miner_id, current_name))
        
        if cursor.rowcount > 0:
            total_blocks_updated += cursor.rowcount
            print(f"  ✓ Miner ID {miner_id}: Updated {cursor.rowcount} blocks to '{current_name}'")
    
    # Update high_diff_shares
    print("\n🏆 Updating HIGH_DIFF_SHARES table...")
    for miner_id, current_name in miner_mappings.items():
        cursor.execute("""
            UPDATE high_diff_shares 
            SET miner_name = ? 
            WHERE miner_id = ? AND miner_name != ?
        """, (current_name, miner_id, current_name))
        
        if cursor.rowcount > 0:
            total_shares_updated += cursor.rowcount
            print(f"  ✓ Miner ID {miner_id}: Updated {cursor.rowcount} shares to '{current_name}'")
    
    # Commit changes
    conn.commit()
    
    print("\n" + "="*80)
    print(f"✅ CHANGES APPLIED SUCCESSFULLY")
    print(f"   Blocks updated: {total_blocks_updated}")
    print(f"   Shares updated: {total_shares_updated}")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print("="*80)

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ['--preview', '--execute']:
        print("Usage:")
        print("  python fix_miner_names.py --preview   # Show what will change")
        print("  python fix_miner_names.py --execute   # Apply changes")
        sys.exit(1)
    
    mode = sys.argv[1]
    
    try:
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        
        # Get current miner names
        miner_mappings = get_miner_name_mappings(conn)
        
        if not miner_mappings:
            print("❌ No miners found in database")
            sys.exit(1)
        
        print(f"\n📋 Current Miners ({len(miner_mappings)}):")
        for miner_id, name in sorted(miner_mappings.items()):
            print(f"  ID {miner_id}: {name}")
        
        if mode == '--preview':
            has_changes = preview_changes(conn, miner_mappings)
            if has_changes:
                print("\n💡 To apply these changes, run:")
                print("   python fix_miner_names.py --execute")
        else:
            # Show preview first
            has_changes = preview_changes(conn, miner_mappings)
            
            if not has_changes:
                print("\n✅ No changes needed. Database is already up to date.")
                sys.exit(0)
            
            # Ask for confirmation
            print("\n⚠️  This will modify your database. Are you sure?")
            print("   Type 'yes' to continue: ", end='')
            confirm = input().strip().lower()
            
            if confirm == 'yes':
                execute_changes(conn, miner_mappings)
            else:
                print("\n❌ Cancelled. No changes made.")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
