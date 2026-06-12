import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = "leaderboard.db"

if not os.path.exists(DB_PATH):
    print("No database found to migrate.")
    exit(0)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. Check if 'editors' table exists (the legacy table)
try:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='editors'")
    if not cursor.fetchone():
        print("No legacy 'editors' table found. Migration might already be done.")
        exit(0)
except Exception as e:
    print(f"Error checking schema: {e}")
    exit(1)

# 2. Fetch all legacy data
try:
    cursor.execute("SELECT username, added_at, total_edits, file_uploads, bytes_added FROM editors")
    legacy_editors = cursor.fetchall()
except Exception as e:
    print(f"Failed to fetch legacy editors (they might not have the new columns yet). Did you run the first migrate.py? Error: {e}")
    # Fallback to older schema
    cursor.execute("SELECT username, added_at FROM editors")
    legacy_editors = [(row[0], row[1], 0, 0, 0) for row in cursor.fetchall()]

# 3. Create new tables via raw SQL so we don't need SQLAlchemy installed
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username VARCHAR UNIQUE,
    role VARCHAR,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    slug VARCHAR UNIQUE,
    name VARCHAR,
    description VARCHAR,
    start_time DATETIME,
    end_time DATETIME,
    target_wikis VARCHAR,
    creator_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS event_editors (
    id INTEGER PRIMARY KEY,
    event_id INTEGER,
    username VARCHAR,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_edits INTEGER DEFAULT 0,
    file_uploads INTEGER DEFAULT 0,
    bytes_added INTEGER DEFAULT 0
)
''')

# 4. Create MdsShakil User
cursor.execute("SELECT id FROM users WHERE username = 'MdsShakil'")
admin_row = cursor.fetchone()
if not admin_row:
    print("Creating superadmin user MdsShakil...")
    cursor.execute("INSERT INTO users (username, role) VALUES ('MdsShakil', 'superadmin')")
    admin_id = cursor.lastrowid
else:
    admin_id = admin_row[0]

# 5. Create Legacy Event
event_slug = "live-edit-a-thon"
cursor.execute("SELECT id FROM events WHERE slug = ?", (event_slug,))
event_row = cursor.fetchone()
if not event_row:
    print("Creating legacy event to house current editors...")
    start_time = "2026-06-11 18:00:00.000000"
    end_time = "2026-06-12 17:59:59.000000"
    
    cursor.execute("""
        INSERT INTO events (slug, name, description, start_time, end_time, target_wikis, creator_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (event_slug, "Dhaka Live Edit-a-thon (Legacy)", "The original live leaderboard event.", start_time, end_time, "commons.wikimedia.org", admin_id))
    legacy_event_id = cursor.lastrowid
else:
    legacy_event_id = event_row[0]

# 6. Port editors
print(f"Porting {len(legacy_editors)} editors to the new event...")
ported_count = 0
for e in legacy_editors:
    username, added_at_str, edits, uploads, b_added = e
    
    cursor.execute("SELECT id FROM event_editors WHERE event_id = ? AND username = ?", (legacy_event_id, username))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO event_editors (event_id, username, added_at, total_edits, file_uploads, bytes_added)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (legacy_event_id, username, added_at_str, edits, uploads, b_added))
        ported_count += 1

# 7. Clean up legacy table
try:
    cursor.execute("DROP TABLE editors")
    print("Dropped legacy 'editors' table to free up space.")
except Exception as e:
    print(f"Could not drop legacy table: {e}")

conn.commit()
conn.close()

print(f"Migration V2 Complete! Successfully ported {ported_count} legacy editors into the new SaaS structure.")
