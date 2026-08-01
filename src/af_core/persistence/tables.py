from datetime import datetime
from sqlalchemy import String,DateTime,ForeignKey,Integer,Text
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base

class ProjectRow(Base):
    __tablename__="projects"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    name:Mapped[str]=mapped_column(String,nullable=False)
    repository_path:Mapped[str]=mapped_column(Text,nullable=False)
    objective:Mapped[str]=mapped_column(Text,nullable=False)
    status:Mapped[str]=mapped_column(String,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime,nullable=False)

class TaskRow(Base):
    __tablename__="tasks"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    project_id:Mapped[str]=mapped_column(
        ForeignKey("projects.id"),nullable=False
    )
    title:Mapped[str]=mapped_column(String,nullable=False)
    status:Mapped[str]=mapped_column(String,nullable=False)

class RunRow(Base):
    __tablename__="runs"
    id:Mapped[str]=mapped_column(String,primary_key=True)
    project_id:Mapped[str]=mapped_column(
        ForeignKey("projects.id"),nullable=False
    )
    status:Mapped[str]=mapped_column(String,nullable=False)

class EventRow(Base):
    __tablename__="events"
    sequence:Mapped[int]=mapped_column(
        Integer,primary_key=True,autoincrement=True
    )
    event_type:Mapped[str]=mapped_column(String,nullable=False)
    project_id:Mapped[str]=mapped_column(
        ForeignKey("projects.id"),nullable=False
    )
    payload:Mapped[str]=mapped_column(Text,nullable=False)
