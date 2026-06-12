import json
from sseclient import SSEClient as EventSource
from datetime import datetime
from backend.database import SessionLocal
from backend import models
from worker.config import is_within_event

STREAM_URL = 'https://stream.wikimedia.org/v2/stream/recentchange'

def get_registered_users(db):
    return {user.username for user in db.query(models.Editor).all()}

def run_listener():
    print("Starting stream listener for Wikimedia Commons...")
    
    # We open a DB session to periodically refresh the registered users
    db = SessionLocal()
    registered_editors = get_registered_users(db)
    
    # To avoid querying DB for every single edit to refresh users,
    # we can reload the list periodically. For a true live sync,
    # a cache or Redis is used, but for simplicity we'll just reload it
    # every 100 events processed, or if a user isn't found, maybe re-check.
    event_counter = 0

    for event in EventSource(STREAM_URL):
        if event.event == 'message':
            try:
                change = json.loads(event.data)
            except ValueError:
                continue
                
            if change.get('server_name') == 'commons.wikimedia.org':
                username = change.get('user')
                
                # Periodically refresh the user list
                event_counter += 1
                if event_counter % 50 == 0:
                    registered_editors = get_registered_users(db)
                
                if username in registered_editors:
                    # Check timestamp
                    ts = change.get('timestamp') # Unix timestamp
                    if ts:
                        dt = datetime.utcfromtimestamp(ts)
                        if not is_within_event(dt):
                            continue # Outside the event window
                    
                    edit_id = change.get('revision', {}).get('new')
                    if not edit_id:
                        # Log events (like upload without revision) might not have 'revision'
                        edit_id = change.get('log_id')
                        
                    if not edit_id:
                        continue # Couldn't identify edit ID
                        
                    # Prevent duplicate
                    if db.query(models.EditLog).filter(models.EditLog.edit_id == edit_id).first():
                        continue

                    namespace = change.get('namespace')
                    log_type = change.get('log_type')
                    is_new = change.get('type') == 'new'
                    is_upload = (log_type == 'upload' or (is_new and namespace == 6))
                    
                    try:
                        diff = change.get('length', {}).get('new', 0) - change.get('length', {}).get('old', 0)
                    except:
                        diff = 0
                        
                    log = models.EditLog(
                        edit_id=edit_id,
                        username=username,
                        namespace=namespace,
                        is_new_page=is_new,
                        timestamp=datetime.utcfromtimestamp(ts) if ts else datetime.utcnow(),
                        bytes_changed=diff
                    )
                    db.add(log)
                    
                    # Update global stats
                    stats = db.query(models.GlobalStats).first()
                    if not stats:
                        stats = models.GlobalStats()
                        db.add(stats)
                        
                    stats.total_edits += 1
                    if is_upload:
                        stats.total_uploads += 1
                    stats.bytes_added += diff
                    
                    db.commit()
                    print(f"Logged live edit for {username} (Diff: {diff}, Upload: {is_upload})")

if __name__ == "__main__":
    run_listener()
