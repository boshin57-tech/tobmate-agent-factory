from datetime import datetime,timezone
from uuid import uuid4
from pydantic import BaseModel,Field
from .enums import *

def uid(p):
    return f"{p}_{uuid4().hex}"

def now():
    return datetime.now(timezone.utc)

class Project(BaseModel):
    id:str=Field(default_factory=lambda:uid("prj"))
    name:str
    repository_path:str
    objective:str
    status:ProjectStatus=ProjectStatus.CREATED
    created_at:datetime=Field(default_factory=now)

class Task(BaseModel):
    id:str=Field(default_factory=lambda:uid("tsk"))
    project_id:str
    title:str
    status:TaskStatus=TaskStatus.CREATED

class FactoryRun(BaseModel):
    id:str=Field(default_factory=lambda:uid("run"))
    project_id:str
    status:RunStatus=RunStatus.CREATED

class Evidence(BaseModel):
    id:str=Field(default_factory=lambda:uid("evd"))
    project_id:str
    evidence_type:EvidenceType
    summary:str
