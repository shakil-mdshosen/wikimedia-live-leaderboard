from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import os

from backend import models, database
from worker import backfill

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Wikimedia Live Leaderboard")

# Pydantic models for request/response
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
    
    # Update global editors count
    stats = db.query(models.GlobalStats).first()
    if not stats:
        stats = models.GlobalStats()
        db.add(stats)
    stats.total_editors += 1
    db.commit()
    
    # Trigger background backfill
    background_tasks.add_task(backfill.backfill_user, username, db)
    
    return {"message": f"Editor {username} added and backfill started."}

@app.get("/api/live-stats", response_model=LiveStats)
def get_live_stats(db: Session = Depends(database.get_db)):
    # 1. Get global stats
    stats = db.query(models.GlobalStats).first()
    global_stats_dict = {
        "total_edits": stats.total_edits if stats else 0,
        "total_editors": stats.total_editors if stats else 0,
        "total_uploads": stats.total_uploads if stats else 0,
        "bytes_added": stats.bytes_added if stats else 0,
    }
    
    # 2. Compute Leaderboard
    # Group by username
    # Count total edits, count file uploads (namespace == 6 OR is_new_page == True AND log_type == upload) -> simplified to namespace=6 for uploads
    leaderboard_query = db.query(
        models.EditLog.username,
        func.count(models.EditLog.id).label('total_edits'),
        func.sum(func.cast(models.EditLog.namespace == 6, models.Integer)).label('file_uploads'), # Simple NS6 count
        func.sum(models.EditLog.bytes_changed).label('bytes_changed')
    ).group_by(models.EditLog.username).order_by(func.count(models.EditLog.id).desc()).all()
    
    leaderboard = []
    rank = 1
    for row in leaderboard_query:
        leaderboard.append({
            "rank": rank,
            "username": row.username,
            "total_edits": row.total_edits,
            "file_uploads": row.file_uploads or 0,
            "bytes_changed": row.bytes_changed or 0
        })
        rank += 1
        
    return {"global_stats": global_stats_dict, "leaderboard": leaderboard}

# Serve frontend statically
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
