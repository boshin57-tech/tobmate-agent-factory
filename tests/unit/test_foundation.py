from af_core.domain.models import Project,Task,FactoryRun
from af_core.domain.enums import ProjectStatus,TaskStatus,RunStatus
from af_core.persistence.database import (
    sqlite_url,
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from af_core.persistence.repositories import (
    ProjectRepository,
    TaskRepository,
    RunRepository,
)
from af_core.operations.event_log import EventLog

def test_foundation_persistence_and_events(tmp_path):
    db=tmp_path/"factory.db"
    engine=create_database_engine(sqlite_url(db))
    initialize_database(engine)
    sessions=create_session_factory(engine)

    projects=ProjectRepository(sessions)
    tasks=TaskRepository(sessions)
    runs=RunRepository(sessions)
    events=EventLog(sessions)

    project=projects.save(Project(
        name="AF Core",
        repository_path="/tmp/repo",
        objective="Checkpoint 1",
    ))

    task=tasks.save(Task(
        project_id=project.id,
        title="Create foundation",
    ))

    run=runs.save(FactoryRun(project_id=project.id))

    project.status=ProjectStatus.RUNNING
    task.status=TaskStatus.READY
    run.status=RunStatus.RUNNING

    projects.save(project)
    tasks.save(task)
    runs.save(run)

    first=events.append(
        "ProjectCreated",
        project.id,
        {"name":project.name},
    )
    second=events.append(
        "ProjectRunning",
        project.id,
        {"status":"RUNNING"},
    )

    assert projects.get(project.id).status is ProjectStatus.RUNNING
    assert tasks.get(task.id).status is TaskStatus.READY
    assert runs.get(run.id).status is RunStatus.RUNNING
    assert second==first+1
    assert len(events.list_for_project(project.id))==2
