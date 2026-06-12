from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    role = Column(String, default="user") # 'user' or 'superadmin'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    events = relationship("Event", back_populates="creator")

class Event(Base):
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True)
    name = Column(String)
    description = Column(String, default="")
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    target_wikis = Column(String, default="commons.wikimedia.org") # Comma-separated list
    creator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    creator = relationship("User", back_populates="events")
    editors = relationship("EventEditor", back_populates="event", cascade="all, delete-orphan")

class EventEditor(Base):
    __tablename__ = "event_editors"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"))
    username = Column(String, index=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Aggregated Stats for THIS specific event
    total_edits = Column(Integer, default=0)
    file_uploads = Column(Integer, default=0)
    bytes_added = Column(Integer, default=0)
    
    event = relationship("Event", back_populates="editors")
