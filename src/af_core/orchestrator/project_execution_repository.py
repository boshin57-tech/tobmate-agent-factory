"""Persistent repository for autonomous project execution runs."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Mapping

from af_core.orchestrator.project_execution_models import (
    ProjectExecutionError,
    ProjectRunEvent,
    ProjectRunEventKind,
    ProjectRunSnapshot,
    ProjectRunState,
    ProjectRunStatus,
    ProjectTaskRuntimeState,
    ProjectTaskStatus,
)


class ProjectRunRepositoryError(ProjectExecutionError):
    """Raised when project run persistence fails."""


class ProjectRunVersionConflict(ProjectRunRepositoryError):
    """Raised when a stale runtime state attempts to overwrite storage."""


_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")

_RESUMABLE_STATUSES = frozenset(
    {
        ProjectRunStatus.READY,
        ProjectRunStatus.RUNNING,
        ProjectRunStatus.PAUSED,
        ProjectRunStatus.RECOVERING,
        ProjectRunStatus.VALIDATING,
    }
)


def _task_to_dict(
    task: ProjectTaskRuntimeState,
) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "attempts": task.attempts,
        "assigned_agent_id": task.assigned_agent_id,
        "assigned_team_id": task.assigned_team_id,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "last_error": task.last_error,
        "output_reference": task.output_reference,
        "metadata": dict(task.metadata),
    }


def _task_from_dict(
    data: Mapping[str, object],
) -> ProjectTaskRuntimeState:
    return ProjectTaskRuntimeState(
        task_id=str(data["task_id"]),
        status=ProjectTaskStatus(str(data["status"])),
        attempts=int(data.get("attempts", 0)),
        assigned_agent_id=data.get("assigned_agent_id"),
        assigned_team_id=data.get("assigned_team_id"),
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
        last_error=str(data.get("last_error", "")),
        output_reference=data.get("output_reference"),
        metadata=dict(data.get("metadata", {})),
    )


def _state_to_dict(
    state: ProjectRunState,
) -> dict[str, object]:
    return {
        "run_id": state.run_id,
        "project_id": state.project_id,
        "repository_path": state.repository_path,
        "status": state.status.value,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "version": state.version,
        "workflow_id": state.workflow_id,
        "tasks": {
            task_id: _task_to_dict(task)
            for task_id, task in state.tasks.items()
        },
        "metadata": dict(state.metadata),
    }


def _state_from_dict(
    data: Mapping[str, object],
) -> ProjectRunState:
    task_data = dict(data.get("tasks", {}))

    return ProjectRunState(
        run_id=str(data["run_id"]),
        project_id=str(data["project_id"]),
        repository_path=str(data["repository_path"]),
        status=ProjectRunStatus(str(data["status"])),
        created_at=float(data["created_at"]),
        updated_at=float(data["updated_at"]),
        version=int(data["version"]),
        workflow_id=data.get("workflow_id"),
        tasks={
            task_id: _task_from_dict(dict(task))
            for task_id, task in task_data.items()
        },
        metadata=dict(data.get("metadata", {})),
    )


def _event_to_dict(
    event: ProjectRunEvent,
) -> dict[str, object]:
    return {
        "sequence": event.sequence,
        "run_id": event.run_id,
        "kind": event.kind.value,
        "occurred_at": event.occurred_at,
        "task_id": event.task_id,
        "detail": dict(event.detail),
    }


def _event_from_dict(
    data: Mapping[str, object],
) -> ProjectRunEvent:
    return ProjectRunEvent(
        sequence=int(data["sequence"]),
        run_id=str(data["run_id"]),
        kind=ProjectRunEventKind(str(data["kind"])),
        occurred_at=float(data["occurred_at"]),
        task_id=data.get("task_id"),
        detail=dict(data.get("detail", {})),
    )


class JsonProjectRunRepository:
    """Atomic JSON repository with optimistic version checks."""

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(
            parents=True,
            exist_ok=True,
        )

    @property
    def root(self) -> Path:
        return self._root

    def create(
        self,
        state: ProjectRunState,
        *,
        occurred_at: float,
    ) -> ProjectRunSnapshot:
        """Persist a newly created run and initial audit event."""

        path = self._path(state.run_id)

        if path.exists():
            raise ProjectRunRepositoryError(
                f"project run already exists: {state.run_id}"
            )

        event = ProjectRunEvent(
            sequence=1,
            run_id=state.run_id,
            kind=ProjectRunEventKind.RUN_CREATED,
            occurred_at=occurred_at,
            detail={
                "project_id": state.project_id,
                "status": state.status.value,
                "version": state.version,
            },
        )

        snapshot = ProjectRunSnapshot(
            state=state,
            events=(event,),
        )

        self._write(snapshot)
        return snapshot

    def get(
        self,
        run_id: str,
    ) -> ProjectRunSnapshot:
        """Load one persisted project run snapshot."""

        path = self._path(run_id)

        if not path.exists():
            raise ProjectRunRepositoryError(
                f"project run not found: {run_id}"
            )

        try:
            data = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectRunRepositoryError(
                f"unable to read project run: {run_id}"
            ) from exc

        return ProjectRunSnapshot(
            state=_state_from_dict(data["state"]),
            events=tuple(
                _event_from_dict(event)
                for event in data.get("events", ())
            ),
        )

    def save(
        self,
        state: ProjectRunState,
        *,
        expected_version: int,
        occurred_at: float,
        event_kind: ProjectRunEventKind = (
            ProjectRunEventKind.CHECKPOINT_SAVED
        ),
        detail: Mapping[str, object] | None = None,
    ) -> ProjectRunSnapshot:
        """Atomically save state when the stored version matches."""

        current = self.get(state.run_id)

        if current.state.version != expected_version:
            raise ProjectRunVersionConflict(
                "project run version conflict: "
                f"expected {expected_version}, "
                f"stored {current.state.version}"
            )

        event_detail = {
            "status": state.status.value,
            "version": state.version,
        }
        event_detail.update(dict(detail or {}))

        event = ProjectRunEvent(
            sequence=len(current.events) + 1,
            run_id=state.run_id,
            kind=event_kind,
            occurred_at=occurred_at,
            detail=event_detail,
        )

        snapshot = ProjectRunSnapshot(
            state=state,
            events=current.events + (event,),
        )

        self._write(snapshot)
        return snapshot

    def append_event(
        self,
        run_id: str,
        *,
        kind: ProjectRunEventKind,
        occurred_at: float,
        task_id: str | None = None,
        detail: Mapping[str, object] | None = None,
    ) -> ProjectRunEvent:
        """Append an event without changing runtime state."""

        current = self.get(run_id)

        event = ProjectRunEvent(
            sequence=len(current.events) + 1,
            run_id=run_id,
            kind=kind,
            occurred_at=occurred_at,
            task_id=task_id,
            detail=dict(detail or {}),
        )

        self._write(
            ProjectRunSnapshot(
                state=current.state,
                events=current.events + (event,),
            )
        )

        return event

    def exists(
        self,
        run_id: str,
    ) -> bool:
        return self._path(run_id).exists()

    def list_run_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                path.stem
                for path in self._root.glob("*.json")
                if not path.name.startswith(".")
            )
        )

    def resumable(
        self,
    ) -> tuple[ProjectRunSnapshot, ...]:
        """Return runs eligible for interruption recovery."""

        return tuple(
            snapshot
            for run_id in self.list_run_ids()
            if (
                snapshot := self.get(run_id)
            ).state.status in _RESUMABLE_STATUSES
        )

    def _path(
        self,
        run_id: str,
    ) -> Path:
        if not _SAFE_RUN_ID.fullmatch(run_id):
            raise ProjectRunRepositoryError(
                f"unsafe project run id: {run_id}"
            )

        return self._root / f"{run_id}.json"

    def _write(
        self,
        snapshot: ProjectRunSnapshot,
    ) -> None:
        path = self._path(snapshot.state.run_id)

        payload = {
            "state": _state_to_dict(snapshot.state),
            "events": [
                _event_to_dict(event)
                for event in snapshot.events
            ],
        }

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{snapshot.state.run_id}.",
            suffix=".tmp",
            dir=self._root,
        )

        temporary = Path(temporary_name)

        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    payload,
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                temporary,
                path,
            )
        finally:
            temporary.unlink(
                missing_ok=True
            )


class ProjectRunResumeService:
    """Convert interrupted runtime states into safe recovery states."""

    def __init__(
        self,
        repository: JsonProjectRunRepository,
    ) -> None:
        self._repository = repository

    def resume(
        self,
        run_id: str,
        *,
        now: float,
    ) -> ProjectRunSnapshot:
        current = self._repository.get(run_id)
        state = current.state

        if state.terminal:
            raise ProjectRunRepositoryError(
                "terminal project run cannot be resumed"
            )

        if state.status is ProjectRunStatus.READY:
            target = ProjectRunStatus.RUNNING
        elif state.status in {
            ProjectRunStatus.RUNNING,
            ProjectRunStatus.PAUSED,
        }:
            target = ProjectRunStatus.RECOVERING
        elif state.status is ProjectRunStatus.VALIDATING:
            target = ProjectRunStatus.RUNNING
        elif state.status is ProjectRunStatus.RECOVERING:
            self._repository.append_event(
                run_id,
                kind=ProjectRunEventKind.RUN_RESUMED,
                occurred_at=now,
                detail={
                    "status": state.status.value,
                    "version": state.version,
                },
            )
            return self._repository.get(run_id)
        else:
            raise ProjectRunRepositoryError(
                "project run is not ready for automatic resume: "
                f"{state.status.value}"
            )

        resumed = state.transition(
            target,
            now=now,
        )

        return self._repository.save(
            resumed,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.RUN_RESUMED,
            detail={
                "previous_status": state.status.value,
            },
        )
