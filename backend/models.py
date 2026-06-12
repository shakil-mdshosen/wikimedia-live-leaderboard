from sqlalchemy import Column, Integer, String, DateTime
from backend.database import Base
import datetime

class Editor(Base):
    __tablename__ = "editors"
    
    username = Column(String, primary_key=True, index=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Aggregated Stats
    total_edits = Column(Integer, default=0)
    file_uploads = Column(Integer, default=0)
    bytes_added = Column(Integer, default=0)
