import sqlite3
import os

DB_PATH = "leaderboard.db"

if not os.path.exists(DB_PATH):
    print("Database not found. Nothing to migrate.")
    exit(0)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

columns_to_add = [
    ("total_edits", "INTEGER DEFAULT 0"),
    ("file_uploads", "INTEGER DEFAULT 0"),
    ("bytes_added", "INTEGER DEFAULT 0")
]

for col_name, col_type in columns_to_add:
    try:
        cursor.execute(f"ALTER TABLE editors ADD COLUMN {col_name} {col_type}")
        print(f"Successfully added column: {col_name}")
    except sqlite3.OperationalError as e:
        # Ignore error if column already exists
        if "duplicate column name" in str(e).lower():
            print(f"Column {col_name} already exists. Skipping.")
        else:
            print(f"Error adding {col_name}: {e}")

conn.commit()
conn.close()

print("Migration completed successfully! Your names are preserved.")
