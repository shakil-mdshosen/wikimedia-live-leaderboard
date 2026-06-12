import time
import requests
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend import models
from worker.config import EVENT_START_UTC, EVENT_END_UTC

API_URL = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "WikimediaLiveLeaderboard/2.0 (https://github.com/shakil-mdshosen/wikimedia-live-leaderboard; shakil@example.com)"
}

def fetch_user_stats(username: str) -> tuple[int, int, int]:
    """
    Fetches exact edits, uploads, and bytes added for a user.
    Returns: (total_edits, file_uploads, bytes_added)
    """
    start_str = EVENT_START_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = EVENT_END_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    edits_added = 0
    uploads_added = 0
    bytes_added = 0
    
    # Track edit IDs to avoid double counting uploads as edits
    tracked_revs = set()
    
    # 1. Process Uploads First (Log Events)
    log_params = {
        "action": "query",
        "format": "json",
        "list": "logevents",
        "leuser": username,
        "lestart": end_str,
        "leend": start_str,
        "ledir": "older",
        "lelimit": "max",
        "letype": "upload"
    }
    
    while True:
        response = requests.get(API_URL, params=log_params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        upload_logs = data.get("query", {}).get("logevents", [])
        
        for l in upload_logs:
            revid = l.get('revid')
            if revid:
                tracked_revs.add(revid)
            uploads_added += 1
            
        if "continue" in data:
            log_params.update(data["continue"])
        else:
            break

    # 2. Process Standard Edits
    edit_params = {
        "action": "query",
        "format": "json",
        "list": "usercontribs",
        "ucuser": username,
        "ucstart": end_str,
        "ucend": start_str,
        "ucdir": "older",
        "uclimit": "max",
        "ucprop": "ids|title|timestamp|flags|sizediff"
    }
    
    while True:
        response = requests.get(API_URL, params=edit_params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        contribs = data.get("query", {}).get("usercontribs", [])
        
        for c in contribs:
            revid = c.get('revid')
            # Only count as an edit if it wasn't already counted as an upload
            if revid not in tracked_revs:
                edits_added += 1
            
            # Always add the bytes, even for uploads
            diff = c.get("sizediff", 0)
            if diff > 0:
                bytes_added += diff
                
        if "continue" in data:
            edit_params.update(data["continue"])
        else:
            break

    return edits_added, uploads_added, bytes_added

def poll_all_users():
    db = SessionLocal()
    try:
        editors = db.query(models.Editor).all()
        for editor in editors:
            print(f"Fetching stats for {editor.username}...")
            try:
                edits, uploads, bytes_added = fetch_user_stats(editor.username)
                editor.total_edits = edits
                editor.file_uploads = uploads
                editor.bytes_added = bytes_added
                db.commit()
                print(f"Updated {editor.username}: {edits} edits, {uploads} uploads, {bytes_added} bytes.")
            except Exception as e:
                print(f"Error fetching stats for {editor.username}: {e}")
                db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting 5-minute poller...")
    while True:
        print(f"[{datetime.utcnow().isoformat()}] Running polling cycle...")
        poll_all_users()
        print("Cycle complete. Sleeping for 5 minutes...")
        time.sleep(300)
