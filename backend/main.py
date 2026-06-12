from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
import os
from datetime import datetime

from backend import models, database
from backend.auth import router as auth_router, get_current_user
from worker import poller

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Wikimedia Live Leaderboard (Multi-Tenant)")

app.include_router(auth_router, prefix="/oauth", tags=["Auth"])

# Pydantic Schemas
class UserOut(BaseModel):
    username: str
    role: str
    
class EventCreate(BaseModel):
    slug: str
    name: str
    description: Optional[str] = ""
    start_time: datetime
    end_time: datetime
    target_wikis: str

class EventOut(BaseModel):
    slug: str
    name: str
    description: str
    start_time: datetime
    end_time: datetime
    target_wikis: str
    creator_username: str

class EditorAdd(BaseModel):
    username: str

class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    total_edits: int
    file_uploads: int
    bytes_changed: int

class LiveStats(BaseModel):
    event: EventOut
    global_stats: dict
    leaderboard: list[LeaderboardEntry]

# Helper
def check_event_access(event, user):
    if user.role != "superadmin" and event.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this event")

# Routes
@app.get("/api/me", response_model=UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role}

@app.get("/api/events", response_model=List[EventOut])
def get_events(db: Session = Depends(database.get_db)):
    events = db.query(models.Event).order_by(models.Event.created_at.desc()).all()
    return [
        {**e.__dict__, "creator_username": e.creator.username if e.creator else "Unknown"}
        for e in events
    ]

@app.post("/api/events", response_model=EventOut)
def create_event(event_data: EventCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    # Check unique slug
    if db.query(models.Event).filter(models.Event.slug == event_data.slug).first():
        raise HTTPException(status_code=400, detail="Event URL slug already taken")
        
    new_event = models.Event(
        slug=event_data.slug,
        name=event_data.name,
        description=event_data.description,
        start_time=event_data.start_time,
        end_time=event_data.end_time,
        target_wikis=event_data.target_wikis,
        creator_id=current_user.id
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return {**new_event.__dict__, "creator_username": current_user.username}

@app.get("/api/events/{slug}", response_model=EventOut)
def get_event(slug: str, db: Session = Depends(database.get_db)):
    event = db.query(models.Event).filter(models.Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {**event.__dict__, "creator_username": event.creator.username if event.creator else "Unknown"}

@app.put("/api/events/{slug}", response_model=EventOut)
def update_event(slug: str, event_data: EventCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    event = db.query(models.Event).filter(models.Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    check_event_access(event, current_user)
    
    # Check slug collision if changed
    if slug != event_data.slug and db.query(models.Event).filter(models.Event.slug == event_data.slug).first():
        raise HTTPException(status_code=400, detail="New URL slug already taken")
        
    event.slug = event_data.slug
    event.name = event_data.name
    event.description = event_data.description
    event.start_time = event_data.start_time
    event.end_time = event_data.end_time
    event.target_wikis = event_data.target_wikis
    db.commit()
    db.refresh(event)
    return {
        "slug": event.slug,
        "name": event.name,
        "description": event.description or "",
        "start_time": event.start_time,
        "end_time": event.end_time,
        "target_wikis": event.target_wikis,
        "creator_username": event.creator.username if event.creator else "Unknown"
    }

@app.delete("/api/events/{slug}")
def delete_event(slug: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    event = db.query(models.Event).filter(models.Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    check_event_access(event, current_user)
    
    db.delete(event)
    db.commit()
    return {"message": "Event deleted"}

@app.post("/api/events/{slug}/editors")
def add_event_editor(slug: str, editor_data: EditorAdd, db: Session = Depends(database.get_db)):
    event = db.query(models.Event).filter(models.Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    username = editor_data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
        
    db_editor = db.query(models.EventEditor).filter(models.EventEditor.event_id == event.id, models.EventEditor.username == username).first()
    if db_editor:
        raise HTTPException(status_code=400, detail="Editor already registered for this event")
        
    new_editor = models.EventEditor(event_id=event.id, username=username)
    db.add(new_editor)
    db.commit()
    
    # Fetch stats synchronously so UI immediately shows right numbers
    try:
        edits, uploads, bytes_added = poller.fetch_user_stats(username, event)
        new_editor.total_edits = edits
        new_editor.file_uploads = uploads
        new_editor.bytes_added = bytes_added
        db.commit()
    except Exception as e:
        print(f"Initial fetch error for {username} in {slug}: {e}")
        db.rollback()
    
    return {"message": f"Editor {username} added to event {event.name}."}

@app.delete("/api/events/{slug}/editors/{username}")
def remove_event_editor(slug: str, username: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    event = db.query(models.Event).filter(models.Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    check_event_access(event, current_user)
    
    editor = db.query(models.EventEditor).filter(models.EventEditor.event_id == event.id, models.EventEditor.username == username).first()
    if not editor:
        raise HTTPException(status_code=404, detail="Editor not found in this event")
        
    db.delete(editor)
    db.commit()
    return {"message": "Editor removed"}

def refresh_event_task(event_id: int):
    db = database.SessionLocal()
    try:
        event = db.query(models.Event).filter(models.Event.id == event_id).first()
        if not event:
            return
            
        for editor in event.editors:
            try:
                edits, uploads, bytes_added = poller.fetch_user_stats(editor.username, event)
                editor.total_edits = edits
                editor.file_uploads = uploads
                editor.bytes_added = bytes_added
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Error fetching {editor.username} for event {event.slug}: {e}")
    finally:
        db.close()

@app.post("/api/events/{slug}/refresh")
def force_refresh_event(slug: str, db: Session = Depends(database.get_db)):
    event = db.query(models.Event).filter(models.Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    refresh_event_task(event.id)
    return {"message": "Refresh complete"}

@app.get("/api/events/{slug}/live-stats", response_model=LiveStats)
def get_event_stats(slug: str, db: Session = Depends(database.get_db)):
    event = db.query(models.Event).filter(models.Event.slug == slug).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    editors = db.query(models.EventEditor).filter(models.EventEditor.event_id == event.id).order_by(models.EventEditor.total_edits.desc()).all()
    
    total_editors = len(editors)
    total_edits = sum(e.total_edits for e in editors)
    total_uploads = sum(e.file_uploads for e in editors)
    bytes_added = sum(e.bytes_added for e in editors)
    
    global_stats_dict = {
        "total_edits": total_edits,
        "total_editors": total_editors,
        "total_uploads": total_uploads,
        "bytes_added": bytes_added,
    }
    
    leaderboard = []
    for rank, e in enumerate(editors, 1):
        leaderboard.append({
            "rank": rank,
            "username": e.username,
            "total_edits": e.total_edits,
            "file_uploads": e.file_uploads,
            "bytes_changed": e.bytes_added
        })
        
    event_out = {**event.__dict__, "creator_username": event.creator.username if event.creator else "Unknown"}
        
    return {"event": event_out, "global_stats": global_stats_dict, "leaderboard": leaderboard}


# Serve frontend statically
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "home.html"))

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))

@app.get("/event/{slug}")
def serve_event(slug: str):
    return FileResponse(os.path.join(FRONTEND_DIR, "event.html"))

@app.get("/event/{slug}/edit")
def serve_event_edit(slug: str):
    return FileResponse(os.path.join(FRONTEND_DIR, "edit.html"))

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
