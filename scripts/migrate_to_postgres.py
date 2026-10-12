#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL.
This script copies all organizational data from the SQLite database to PostgreSQL.
"""

import sqlite3
import psycopg2
from pathlib import Path

# Paths and connection info
SQLITE_DB = Path(__file__).parent.parent / 'db' / 'terran_society.db'
PG_HOST = 'localhost'
PG_DATABASE = 'terran_society'
PG_USER = 'rock'
PG_PASSWORD = 'river'

def get_sqlite_conn():
    """Connect to SQLite database"""
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_pg_conn():
    """Connect to PostgreSQL database"""
    return psycopg2.connect(
        host=PG_HOST,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
    )

def migrate_table(sqlite_cur, pg_cur, sqlite_table, pg_table, column_mapping):
    """
    Migrate data from SQLite table to PostgreSQL table.
    
    Args:
        sqlite_cur: SQLite cursor
        pg_cur: PostgreSQL cursor
        sqlite_table: SQLite table name (e.g., 'tTier')
        pg_table: PostgreSQL table name (e.g., 'ts_data.tier')
        column_mapping: dict mapping SQLite columns to PostgreSQL columns
    """
    # Fetch all rows from SQLite
    sqlite_cur.execute(f"SELECT * FROM {sqlite_table}")
    rows = sqlite_cur.fetchall()
    
    if not rows:
        print(f"  No data in {sqlite_table}")
        return 0
    
    # Get column names
    sqlite_cols = list(column_mapping.keys())
    pg_cols = list(column_mapping.values())
    
    # Build INSERT statement
    placeholders = ','.join(['%s'] * len(pg_cols))
    columns = ','.join(pg_cols)
    insert_sql = f"INSERT INTO {pg_table} ({columns}) VALUES ({placeholders})"
    
    # Insert each row
    count = 0
    for row in rows:
        values = []
        for col in sqlite_cols:
            if col in row.keys():
                val = row[col]
                # Convert integer 0/1 to boolean for PostgreSQL
                if col in ['IsExample', 'Limit'] and isinstance(val, int):
                    val = bool(val)
                values.append(val)
            else:
                values.append(None)
        try:
            pg_cur.execute(insert_sql, values)
            count += 1
        except Exception as e:
            print(f"    Error inserting row: {e}")
            print(f"    Values: {values}")
    
    return count

def main():
    print("=" * 80)
    print("Migrating Terran Society Database from SQLite to PostgreSQL")
    print("=" * 80)
    
    sqlite_conn = get_sqlite_conn()
    pg_conn = get_pg_conn()
    
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    
    try:
        # Disable triggers temporarily for faster insertion
        pg_cur.execute("SET session_replication_role = replica;")
        
        print("\n1. Migrating Tiers...")
        count = migrate_table(
            sqlite_cur, pg_cur,
            'tTier', 'ts_data.tier',
            {
                'TierName': 'tier_name',
                'TierCode': 'tier_code',
                'SortOrder': 'sort_order',
                'DocLoc': 'doc_loc',
                'IsExample': 'is_example',
                'ExampleNote': 'example_note'
            }
        )
        print(f"  ✓ Migrated {count} tiers")
        
        # Get tier ID mapping
        sqlite_cur.execute("SELECT TierName FROM tTier")
        tier_names = [r[0] for r in sqlite_cur.fetchall()]
        tier_id_map = {}
        for name in tier_names:
            pg_cur.execute("SELECT tier_id FROM ts_data.tier WHERE tier_name = %s", (name,))
            tier_id_map[name] = pg_cur.fetchone()[0]
        
        print("\n2. Migrating Tier Explanations...")
        sqlite_cur.execute("SELECT * FROM tTierExplain")
        count = 0
        for row in sqlite_cur.fetchall():
            tier_name = row['TierName']
            if tier_name in tier_id_map:
                pg_cur.execute("""
                    INSERT INTO ts_data.tier_explain 
                    (tier_id, explain_header, explain_desc, doc_loc, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    tier_id_map[tier_name],
                    row['TierExplainHeader'],
                    row['TierExplainDesc'],
                    row['DocLoc'],
                    row['SortOrder']
                ))
                count += 1
        print(f"  ✓ Migrated {count} tier explanations")
        
        print("\n3. Migrating Branches...")
        count = migrate_table(
            sqlite_cur, pg_cur,
            'tBranch', 'ts_data.branch',
            {
                'BranchName': 'branch_name',
                'BranchCode': 'branch_code',
                'BranchHeader': 'branch_header',
                'BranchDesc': 'branch_desc',
                'SortOrder': 'sort_order',
                'DocLoc': 'doc_loc',
                'IsExample': 'is_example',
                'ExampleNote': 'example_note'
            }
        )
        print(f"  ✓ Migrated {count} branches")
        
        # Get branch ID mapping
        sqlite_cur.execute("SELECT BranchName FROM tBranch")
        branch_names = [r[0] for r in sqlite_cur.fetchall()]
        branch_id_map = {}
        for name in branch_names:
            pg_cur.execute("SELECT branch_id FROM ts_data.branch WHERE branch_name = %s", (name,))
            branch_id_map[name] = pg_cur.fetchone()[0]
        
        print("\n4. Migrating Branch Explanations...")
        sqlite_cur.execute("SELECT * FROM tBranchExplain")
        count = 0
        for row in sqlite_cur.fetchall():
            branch_name = row['BranchName']
            if branch_name in branch_id_map:
                pg_cur.execute("""
                    INSERT INTO ts_data.branch_explain 
                    (branch_id, explain_header, explain_desc, doc_loc, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    branch_id_map[branch_name],
                    row['BranchExplainHeader'],
                    row['BranchExplainDesc'],
                    row['DocLoc'],
                    row['SortOrder']
                ))
                count += 1
        print(f"  ✓ Migrated {count} branch explanations")
        
        print("\n5. Migrating Institutions...")
        sqlite_cur.execute("""
            SELECT i.*, t.TierName, b.BranchName
            FROM tInstitution i
            JOIN tTier t ON i.TierName = t.TierName
            JOIN tBranch b ON i.BranchName = b.BranchName
        """)
        
        institution_id_map = {}
        count = 0
        for row in sqlite_cur.fetchall():
            tier_id = tier_id_map.get(row['TierName'])
            branch_id = branch_id_map.get(row['BranchName'])
            
            if tier_id and branch_id:
                pg_cur.execute("""
                    INSERT INTO ts_data.institution 
                    (institution_name, tier_id, branch_id, institution_header, 
                     institution_desc, doc_loc, sort_order, is_example, example_note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING institution_id
                """, (
                    row['InstitutionName'],
                    tier_id,
                    branch_id,
                    row['InstitutionHeader'],
                    row['InstitutionDesc'],
                    row['DocLoc'],
                    row['SortOrder'],
                    bool(row['IsExample']) if row['IsExample'] is not None else False,
                    row['ExampleNote']
                ))
                new_id = pg_cur.fetchone()[0]
                institution_id_map[row['InstitutionID']] = new_id
                count += 1
        print(f"  ✓ Migrated {count} institutions")
        
        print("\n6. Migrating Roles...")
        sqlite_cur.execute("SELECT * FROM tRole")
        role_id_map = {}
        count = 0
        for row in sqlite_cur.fetchall():
            inst_id = institution_id_map.get(row['InstitutionID'])
            if inst_id:
                pg_cur.execute("""
                    INSERT INTO ts_data.role 
                    (role_name, institution_id, role_title, role_desc, term_length_years,
                     has_term_limit, term_limit_years, max_consecutive_terms, election_method,
                     doc_loc, sort_order, is_example, example_note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING role_id
                """, (
                    row['RoleName'],
                    inst_id,
                    row['RoleTitle'],
                    row['RoleDesc'],
                    row['TermLengthYears'],
                    bool(row['HasTermLimit']) if row['HasTermLimit'] is not None else False,
                    row['TermLimitYears'],
                    row['MaxConsecutiveTerms'],
                    row['ElectionMethod'],
                    row['DocLoc'],
                    row['SortOrder'],
                    bool(row['IsExample']) if row['IsExample'] is not None else False,
                    row['ExampleNote']
                ))
                new_id = pg_cur.fetchone()[0]
                role_id_map[row['RoleID']] = new_id
                count += 1
        print(f"  ✓ Migrated {count} roles")
        
        print("\n7. Migrating Role Duties...")
        sqlite_cur.execute("SELECT * FROM tRoleDuty")
        count = 0
        for row in sqlite_cur.fetchall():
            role_id = role_id_map.get(row['RoleID'])
            if role_id:
                pg_cur.execute("""
                    INSERT INTO ts_data.role_duty 
                    (role_id, duty_header, duty_desc, doc_loc, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    role_id,
                    row['RoleDutyHeader'],
                    row['RoleDutyDesc'],
                    row['DocLoc'],
                    row['SortOrder']
                ))
                count += 1
        print(f"  ✓ Migrated {count} role duties")
        
        # Re-enable triggers
        pg_cur.execute("SET session_replication_role = DEFAULT;")
        
        # Commit all changes
        pg_conn.commit()
        
        print("\n" + "=" * 80)
        print("✓ Migration Complete!")
        print("=" * 80)
        
        # Show summary
        print("\nDatabase Statistics:")
        pg_cur.execute("SELECT COUNT(*) FROM ts_data.tier")
        print(f"  Tiers:        {pg_cur.fetchone()[0]}")
        
        pg_cur.execute("SELECT COUNT(*) FROM ts_data.branch")
        print(f"  Branches:     {pg_cur.fetchone()[0]}")
        
        pg_cur.execute("SELECT COUNT(*) FROM ts_data.institution")
        print(f"  Institutions: {pg_cur.fetchone()[0]}")
        
        pg_cur.execute("SELECT COUNT(*) FROM ts_data.role")
        print(f"  Roles:        {pg_cur.fetchone()[0]}")
        
        pg_cur.execute("SELECT COUNT(*) FROM ts_data.role_duty")
        print(f"  Duties:       {pg_cur.fetchone()[0]}")
        
        print("\nVerify with:")
        print("  PGPASSWORD=river psql -h localhost -U rock -d terran_society")
        print("  SELECT * FROM ts_data.v_role_full;")
        
    except Exception as e:
        pg_conn.rollback()
        print(f"\n✗ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        sqlite_cur.close()
        sqlite_conn.close()
        pg_cur.close()
        pg_conn.close()

if __name__ == '__main__':
    main()
