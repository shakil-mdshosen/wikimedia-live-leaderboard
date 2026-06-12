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

# 3. Import new SQLAlchemy Models to initialize the new schema safely
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.database import SessionLocal, engine
from backend import models

print("Initializing new database tables...")
models.Base.metadata.create_all(bind=engine)

db = SessionLocal()

# 4. Create MdsShakil User
admin = db.query(models.User).filter(models.User.username == "MdsShakil").first()
if not admin:
    print("Creating superadmin user MdsShakil...")
    admin = models.User(username="MdsShakil", role="superadmin")
    db.add(admin)
    db.commit()
    db.refresh(admin)

# 5. Create Legacy Event
event_slug = "live-edit-a-thon"
legacy_event = db.query(models.Event).filter(models.Event.slug == event_slug).first()
if not legacy_event:
    print("Creating legacy event to house current editors...")
    # Using the old hardcoded times
    start_time = datetime(2026, 6, 11, 18, 0, 0) # UTC equivalent to 12th midnight BST
    end_time = datetime(2026, 6, 12, 17, 59, 59) # UTC equivalent to 12th 11:59pm BST
    
    legacy_event = models.Event(
        slug=event_slug,
        name="Dhaka Live Edit-a-thon (Legacy)",
        description="The original live leaderboard event.",
        start_time=start_time,
        end_time=end_time,
        target_wikis="commons.wikimedia.org",
        creator_id=admin.id
    )
    db.add(legacy_event)
    db.commit()
    db.refresh(legacy_event)

# 6. Port editors
print(f"Porting {len(legacy_editors)} editors to the new event...")
ported_count = 0
for e in legacy_editors:
    username, added_at_str, edits, uploads, b_added = e
    
    # Check if they exist
    existing = db.query(models.EventEditor).filter(
        models.EventEditor.event_id == legacy_event.id,
        models.EventEditor.username == username
    ).first()
    
    if not existing:
        # Convert added_at string back to datetime if necessary
        try:
            added_at = datetime.strptime(added_at_str, "%Y-%m-%d %H:%M:%S.%f")
        except:
            added_at = datetime.utcnow()
            
        new_ee = models.EventEditor(
            event_id=legacy_event.id,
            username=username,
            added_at=added_at,
            total_edits=edits,
            file_uploads=uploads,
            bytes_added=b_added
        )
        db.add(new_ee)
        ported_count += 1

db.commit()
db.close()

# 7. Clean up legacy table
try:
    cursor.execute("DROP TABLE editors")
    conn.commit()
    print("Dropped legacy 'editors' table to free up space.")
except Exception as e:
    print(f"Could not drop legacy table: {e}")

conn.close()

print(f"Migration V2 Complete! Successfully ported {ported_count} legacy editors into the new SaaS structure.")
