import time
import requests
import sys
import os
from datetime import datetime, timezone

# Bulletproof path resolution so it can import backend regardless of where it's run from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend import models

HEADERS = {
    "User-Agent": "WikimediaLiveLeaderboard/2.0 (https://github.com/shakil-mdshosen/wikimedia-live-leaderboard; mds.shakil@example.com)"
}

def fetch_user_stats(username: str, event: models.Event) -> tuple[int, int, int]:
    """
    Fetches the number of edits, file uploads, and bytes added for a specific user 
    within the given event's time boundary and target wikis.
    """
    
    # Event times are stored as Bangladesh Local Time (UTC+6) in the database.
    # We must convert them to UTC for the Wikimedia API (UTC = BD - 6 hours)
    from datetime import timedelta
    start_utc = event.start_time - timedelta(hours=6)
    end_utc = event.end_time - timedelta(hours=6)
    
    start_str = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    total_edits = 0
    file_uploads = 0
    bytes_added = 0
    
    # Target wikis (comma separated)
    wikis = [w.strip() for w in event.target_wikis.split(",") if w.strip()]
    if not wikis:
        wikis = ["commons.wikimedia.org"] # Fallback
        
    for wiki in wikis:
        api_url = f"https://{wiki}/w/api.php"
        
        # 1. Fetch User Contributions (for total edits and bytes added)
        edit_params = {
            "action": "query",
            "format": "json",
            "list": "usercontribs",
            "ucuser": username,
            "ucstart": end_str,    # For ucdir=older, ucstart must be LATER than ucend
            "ucend": start_str,
            "ucdir": "older",
            "uclimit": "max",
            "ucprop": "ids|title|timestamp|flags|sizediff"
        }
        
        # Paginate through contributions
        while True:
            response = requests.get(api_url, params=edit_params, headers=HEADERS)
            response.raise_for_status()
            data = response.json()
            contribs = data.get("query", {}).get("usercontribs", [])
            
            for c in contribs:
                total_edits += 1
                diff = c.get("sizediff", 0)
                if diff > 0:
                    bytes_added += diff
                    
            if "continue" in data:
                edit_params.update(data["continue"])
            else:
                break
                
        # 2. Fetch Log Events (specifically for Uploads)
        # Note: If the event only targets non-Commons, this might return 0 uploads, which is fine.
        log_params = {
            "action": "query",
            "format": "json",
            "list": "logevents",
            "leuser": username,
            "letype": "upload",
            "lestart": end_str,
            "leend": start_str,
            "ledir": "older",
            "lelimit": "max"
        }
        
        while True:
            response = requests.get(api_url, params=log_params, headers=HEADERS)
            response.raise_for_status()
            data = response.json()
            logs = data.get("query", {}).get("logevents", [])
            
            for l in logs:
                # Deduplicate: if an upload also creates a page, it's already counted in usercontribs.
                # Standard practice is to count uploads separately and ignore the overlap in 'total_edits', 
                # or consider it a distinct metric.
                file_uploads += 1
                
            if "continue" in data:
                log_params.update(data["continue"])
            else:
                break

    return total_edits, file_uploads, bytes_added

def poll_all_active_events():
    """Iterates through all active events and updates their editors' stats."""
    db = SessionLocal()
    try:
        now_utc = datetime.utcnow()
        # Active events: start_time is in the past, end_time is in the future (or recently finished)
        events = db.query(models.Event).all()
        
        for event in events:
            # Skip if the event has been over for more than 6 minutes
            # We allow a 6-minute grace period to do one final poll after the event ends
            from datetime import timedelta
            end_utc = event.end_time - timedelta(hours=6)
            if now_utc > end_utc + timedelta(minutes=6):
                print(f"Skipping ended event: {event.name} ({event.slug})")
                continue
                
            print(f"Polling event: {event.name} ({event.slug})")
            
            for editor in event.editors:
                try:
                    edits, uploads, b_added = fetch_user_stats(editor.username, event)
                    editor.total_edits = edits
                    editor.file_uploads = uploads
                    editor.bytes_added = b_added
                    db.commit()
                except Exception as e:
                    db.rollback()
                    print(f"Error updating stats for {editor.username} in {event.slug}: {e}")
                    
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting Multi-Tenant 5-minute poller...")
    while True:
        try:
            print(f"[{datetime.utcnow().isoformat()}] Running polling cycle...")
            poll_all_active_events()
        except Exception as e:
            print(f"Polling cycle failed: {e}")
            
        time.sleep(300)
