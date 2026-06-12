import requests
from datetime import datetime
from sqlalchemy.orm import Session
from backend import models
from worker.config import EVENT_START_UTC, EVENT_END_UTC

API_URL = "https://commons.wikimedia.org/w/api.php"

def backfill_user(username: str):
    """
    Fetches the user's contributions since the start of the event
    using the MediaWiki Action API, and adds them to the database.
    """
    from backend.database import SessionLocal
    db = SessionLocal()
    
    start_str = EVENT_START_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = EVENT_END_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    params = {
        "action": "query",
        "format": "json",
        "list": "usercontribs",
        "ucuser": username,
        "ucstart": end_str, # In MediaWiki API, ucstart is the later timestamp when iterating backwards
        "ucend": start_str,
        "ucdir": "older",
        "uclimit": "max",
        "ucprop": "ids|title|timestamp|flags|sizediff"
    }
    
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        contribs = data.get("query", {}).get("usercontribs", [])
        
        edits_added = 0
        uploads_added = 0
        bytes_added = 0
        
        for c in contribs:
            edit_id = c.get("revid")
            # Check if edit already exists to prevent duplicates
            if db.query(models.EditLog).filter(models.EditLog.edit_id == edit_id).first():
                continue
                
            ts = datetime.strptime(c.get("timestamp"), "%Y-%m-%dT%H:%M:%SZ")
            ns = c.get("ns")
            diff = c.get("sizediff", 0)
            is_new = "new" in c
            
            log = models.EditLog(
                edit_id=edit_id,
                username=username,
                namespace=ns,
                is_new_page=is_new,
                timestamp=ts,
                bytes_changed=diff
            )
            db.add(log)
            edits_added += 1
            if ns == 6:
                uploads_added += 1
            bytes_added += diff
            
        # Update global stats
        if edits_added > 0:
            stats = db.query(models.GlobalStats).first()
            if not stats:
                stats = models.GlobalStats()
                db.add(stats)
            stats.total_edits += edits_added
            stats.total_uploads += uploads_added
            stats.bytes_added += bytes_added
            
        db.commit()
        
    except Exception as e:
        print(f"Error backfilling user {username}: {e}")
    finally:
        db.close()
