from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import os

from backend import models, database
from worker import poller

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Wikimedia Live Leaderboard")

class EditorAdd(BaseModel):
    username: str

class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    total_edits: int
    file_uploads: int
    bytes_changed: int

class LiveStats(BaseModel):
    global_stats: dict
    leaderboard: list[LeaderboardEntry]

def initial_fetch_task(username: str):
    """Fetches stats immediately upon registration without blocking the API response."""
    db = database.SessionLocal()
    try:
        editor = db.query(models.Editor).filter(models.Editor.username == username).first()
        if editor:
            edits, uploads, bytes_added = poller.fetch_user_stats(username)
            editor.total_edits = edits
            editor.file_uploads = uploads
            editor.bytes_added = bytes_added
            db.commit()
    except Exception as e:
        print(f"Initial fetch error for {username}: {e}")
    finally:
        db.close()

@app.post("/api/editors")
def add_editor(editor_data: EditorAdd, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    username = editor_data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
        
    db_editor = db.query(models.Editor).filter(models.Editor.username == username).first()
    if db_editor:
        raise HTTPException(status_code=400, detail="Editor already registered")
        
    new_editor = models.Editor(username=username)
    db.add(new_editor)
    db.commit()
    
    # Trigger an immediate one-off fetch so they don't have to wait 5 minutes to appear
    background_tasks.add_task(initial_fetch_task, username)
    
    return {"message": f"Editor {username} added. Fetching initial stats..."}

def refresh_all_users_task():
    db = database.SessionLocal()
    try:
        editors = db.query(models.Editor).all()
        for editor in editors:
            try:
                edits, uploads, bytes_added = poller.fetch_user_stats(editor.username)
                editor.total_edits = edits
                editor.file_uploads = uploads
                editor.bytes_added = bytes_added
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Error fetching {editor.username}: {e}")
    finally:
        db.close()

@app.post("/api/refresh")
def force_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(refresh_all_users_task)
    return {"message": "Background refresh started"}

@app.get("/api/live-stats", response_model=LiveStats)
def get_live_stats(db: Session = Depends(database.get_db)):
    editors = db.query(models.Editor).order_by(models.Editor.total_edits.desc()).all()
    
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
        
    return {"global_stats": global_stats_dict, "leaderboard": leaderboard}

# Serve frontend statically
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
