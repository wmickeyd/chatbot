from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from database import Base

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, index=True)
    role = Column(String)  # 'system', 'user', 'assistant', 'tool'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(String, primary_key=True, index=True)
    preferred_model = Column(String, default="gemma")
    preferred_temp_unit = Column(String, default="Celsius")
    preferred_lang = Column(String, default="en")
    timezone = Column(String, default="UTC")
