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
    
    headers = {
        "User-Agent": "WikimediaLiveLeaderboard/1.0 (https://github.com/shakil-mdshosen/wikimedia-live-leaderboard; shakil@example.com)"
    }
    
    try:
        edits_added = 0
        uploads_added = 0
        bytes_added = 0
        
        # 1. Process Edits (with Pagination)
        while True:
            response = requests.get(API_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            contribs = data.get("query", {}).get("usercontribs", [])
            
            for c in contribs:
                revid = c.get('revid')
                if not revid: continue
                
                edit_id_str = f"rev_{revid}"
                if db.query(models.EditLog).filter(models.EditLog.edit_id == edit_id_str).first():
                    continue
                    
                ts = datetime.strptime(c.get("timestamp"), "%Y-%m-%dT%H:%M:%SZ")
                ns = c.get("ns")
                diff = max(0, c.get("sizediff", 0))
                is_new = "new" in c
                
                log = models.EditLog(
                    edit_id=edit_id_str,
                    username=username,
                    namespace=ns,
                    is_new_page=is_new,
                    is_upload=False,
                    timestamp=ts,
                    bytes_changed=diff
                )
                db.add(log)
                edits_added += 1
                bytes_added += diff
                
            if "continue" in data:
                params.update(data["continue"])
            else:
                break

        # 2. Process Uploads via logevents (with Pagination)
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
            response_logs = requests.get(API_URL, params=log_params, headers=headers)
            response_logs.raise_for_status()
            log_data = response_logs.json()
            upload_logs = log_data.get("query", {}).get("logevents", [])
            
            for l in upload_logs:
                revid = l.get('revid')
                if not revid: continue
                
                edit_id_str = f"rev_{revid}"
                existing = db.query(models.EditLog).filter(models.EditLog.edit_id == edit_id_str).first()
                
                if existing:
                    if not existing.is_upload:
                        existing.is_upload = True
                        uploads_added += 1
                        edits_added -= 1
                else:
                    ts = datetime.strptime(l.get("timestamp"), "%Y-%m-%dT%H:%M:%SZ")
                    ns = l.get("ns")
                    log = models.EditLog(
                        edit_id=edit_id_str,
                        username=username,
                        namespace=ns,
                        is_new_page=True,
                        is_upload=True,
                        timestamp=ts,
                        bytes_changed=0
                    )
                    db.add(log)
                    uploads_added += 1
                    
            if "continue" in log_data:
                log_params.update(log_data["continue"])
            else:
                break
            
        # Update global stats
        if edits_added > 0 or uploads_added > 0:
            stats = db.query(models.GlobalStats).first()
            if not stats:
                stats = models.GlobalStats(total_editors=0, total_edits=0, total_uploads=0, bytes_added=0)
                db.add(stats)
            stats.total_edits += edits_added
            stats.total_uploads += uploads_added
            stats.bytes_added += bytes_added
            
        db.commit()
        
    except Exception as e:
        print(f"Error backfilling user {username}: {e}")
    finally:
        db.close()
