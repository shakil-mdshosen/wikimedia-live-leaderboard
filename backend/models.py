from sqlalchemy import Column, Integer, String, Boolean, DateTime
from backend.database import Base
import datetime

class Editor(Base):
    __tablename__ = "editors"
    
    username = Column(String, primary_key=True, index=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)

class EditLog(Base):
    __tablename__ = "edits_log"
    
    id = Column(Integer, primary_key=True, index=True)
    edit_id = Column(String, unique=True, index=True)
    username = Column(String, index=True)
    namespace = Column(Integer)
    is_new_page = Column(Boolean)
    is_upload = Column(Boolean, default=False)
    timestamp = Column(DateTime)
    bytes_changed = Column(Integer)

class GlobalStats(Base):
    __tablename__ = "global_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    total_edits = Column(Integer, default=0)
    total_editors = Column(Integer, default=0)
    total_uploads = Column(Integer, default=0)
    bytes_added = Column(Integer, default=0)
