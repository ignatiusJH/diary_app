# models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func

from db import Base


class Diary(Base):
    __tablename__ = "diaries"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(String(200), nullable=True)
    image_url = Column(String(300), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(10), nullable=False)      # "2025-11-28"
    title = Column(String(200), nullable=False)
    memo = Column(Text, nullable=True)
    time_str = Column(String(20), nullable=True)   # "14:00" 같은 표현
    place = Column(String(200), nullable=True)
    done = Column(Boolean, default=False)


class Todo(Base):
    __tablename__ = "todos"

    # uuid 문자열 그대로 쓰기 위해 String PK
    id = Column(String(100), primary_key=True, index=True)
    date = Column(String(10), nullable=False)          # "YYYY-MM-DD"
    title = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    order = Column(Integer, nullable=False, default=0) # 정렬/드래그용
