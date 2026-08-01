import json
from sqlalchemy import select
from af_core.domain.models import Project,Task,FactoryRun
from af_core.domain.enums import ProjectStatus,TaskStatus,RunStatus
from .tables import ProjectRow,TaskRow,RunRow

class ProjectRepository:
    def __init__(self,sessions):
        self.sessions=sessions

    def save(self,obj):
        with self.sessions() as s:
            row=s.get(ProjectRow,obj.id)
            data=dict(
                id=obj.id,
                name=obj.name,
                repository_path=obj.repository_path,
                objective=obj.objective,
                status=obj.status.value,
                created_at=obj.created_at,
            )
            if row is None:
                s.add(ProjectRow(**data))
            else:
                for k,v in data.items():
                    setattr(row,k,v)
            s.commit()
        return obj

    def get(self,obj_id):
        with self.sessions() as s:
            r=s.get(ProjectRow,obj_id)
            return Project(
                id=r.id,
                name=r.name,
                repository_path=r.repository_path,
                objective=r.objective,
                status=ProjectStatus(r.status),
                created_at=r.created_at,
            )

class TaskRepository:
    def __init__(self,sessions):
        self.sessions=sessions

    def save(self,obj):
        with self.sessions() as s:
            row=s.get(TaskRow,obj.id)
            data=dict(
                id=obj.id,
                project_id=obj.project_id,
                title=obj.title,
                status=obj.status.value,
            )
            if row is None:
                s.add(TaskRow(**data))
            else:
                for k,v in data.items():
                    setattr(row,k,v)
            s.commit()
        return obj

    def get(self,obj_id):
        with self.sessions() as s:
            r=s.get(TaskRow,obj_id)
            return Task(
                id=r.id,
                project_id=r.project_id,
                title=r.title,
                status=TaskStatus(r.status),
            )

class RunRepository:
    def __init__(self,sessions):
        self.sessions=sessions

    def save(self,obj):
        with self.sessions() as s:
            row=s.get(RunRow,obj.id)
            data=dict(
                id=obj.id,
                project_id=obj.project_id,
                status=obj.status.value,
            )
            if row is None:
                s.add(RunRow(**data))
            else:
                for k,v in data.items():
                    setattr(row,k,v)
            s.commit()
        return obj

    def get(self,obj_id):
        with self.sessions() as s:
            r=s.get(RunRow,obj_id)
            return FactoryRun(
                id=r.id,
                project_id=r.project_id,
                status=RunStatus(r.status),
            )
