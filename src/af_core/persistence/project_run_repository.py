"""Transactional SQL repository for autonomous project runs."""

from __future__ import annotations

import json
from collections.abc import Mapping

from sqlalchemy import (
    Engine,
    and_,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from af_core.orchestrator.project_execution_models import (
    ProjectRunEvent,
    ProjectRunEventKind,
    ProjectRunSnapshot,
    ProjectRunState,
    ProjectRunStatus,
)
from af_core.orchestrator.project_execution_repository import (
    ProjectRunRepositoryError,
    ProjectRunVersionConflict,
    _event_from_dict,
    _event_to_dict,
    _state_from_dict,
    _state_to_dict,
)

from .project_run_tables import (
    project_run_events,
    project_run_snapshots,
)


_RESUMABLE_STATUS_VALUES = tuple(
    status.value
    for status in (
        ProjectRunStatus.READY,
        ProjectRunStatus.RUNNING,
        ProjectRunStatus.PAUSED,
        ProjectRunStatus.RECOVERING,
        ProjectRunStatus.VALIDATING,
    )
)


def _json_dump(
    value: Mapping[str, object],
) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _state_payload(
    state: ProjectRunState,
) -> str:
    return _json_dump(
        _state_to_dict(state)
    )


def _event_values(
    event: ProjectRunEvent,
) -> dict[str, object]:
    return {
        "run_id": event.run_id,
        "sequence": event.sequence,
        "kind": event.kind.value,
        "occurred_at": event.occurred_at,
        "task_id": event.task_id,
        "detail_payload": _json_dump(
            dict(event.detail)
        ),
    }


class SQLAlchemyProjectRunRepository:
    """Store project snapshots and events in one SQL transaction."""

    def __init__(
        self,
        engine: Engine,
    ) -> None:
        self.engine = engine

    def create(
        self,
        state: ProjectRunState,
        *,
        occurred_at: float,
    ) -> ProjectRunSnapshot:
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

        try:
            with self.engine.begin() as connection:
                existing = connection.execute(
                    select(
                        project_run_snapshots.c.run_id
                    ).where(
                        project_run_snapshots.c.run_id
                        == state.run_id
                    )
                ).scalar_one_or_none()

                if existing is not None:
                    raise ProjectRunRepositoryError(
                        "project run already exists: "
                        f"{state.run_id}"
                    )

                connection.execute(
                    insert(project_run_snapshots),
                    {
                        "run_id": state.run_id,
                        "project_id": state.project_id,
                        "status": state.status.value,
                        "version": state.version,
                        "created_at": state.created_at,
                        "updated_at": state.updated_at,
                        "state_payload": _state_payload(
                            state
                        ),
                    },
                )

                connection.execute(
                    insert(project_run_events),
                    _event_values(event),
                )

        except ProjectRunRepositoryError:
            raise

        except IntegrityError as exc:
            raise ProjectRunRepositoryError(
                "project run already exists: "
                f"{state.run_id}"
            ) from exc

        except SQLAlchemyError as exc:
            raise ProjectRunRepositoryError(
                "unable to create project run: "
                f"{state.run_id}"
            ) from exc

        return ProjectRunSnapshot(
            state=state,
            events=(event,),
        )

    def get(
        self,
        run_id: str,
    ) -> ProjectRunSnapshot:
        try:
            with self.engine.connect() as connection:
                snapshot_row = connection.execute(
                    select(
                        project_run_snapshots
                    ).where(
                        project_run_snapshots.c.run_id
                        == run_id
                    )
                ).mappings().one_or_none()

                if snapshot_row is None:
                    raise ProjectRunRepositoryError(
                        "project run not found: "
                        f"{run_id}"
                    )

                event_rows = connection.execute(
                    select(
                        project_run_events
                    )
                    .where(
                        project_run_events.c.run_id
                        == run_id
                    )
                    .order_by(
                        project_run_events.c.sequence
                    )
                ).mappings().all()

        except ProjectRunRepositoryError:
            raise

        except SQLAlchemyError as exc:
            raise ProjectRunRepositoryError(
                "unable to read project run: "
                f"{run_id}"
            ) from exc

        state = _state_from_dict(
            json.loads(
                str(snapshot_row["state_payload"])
            )
        )

        events = tuple(
            _event_from_dict(
                {
                    "sequence": row["sequence"],
                    "run_id": row["run_id"],
                    "kind": row["kind"],
                    "occurred_at": row["occurred_at"],
                    "task_id": row["task_id"],
                    "detail": json.loads(
                        str(row["detail_payload"])
                    ),
                }
            )
            for row in event_rows
        )

        return ProjectRunSnapshot(
            state=state,
            events=events,
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
        try:
            with self.engine.begin() as connection:
                current = connection.execute(
                    select(
                        project_run_snapshots
                    )
                    .where(
                        project_run_snapshots.c.run_id
                        == state.run_id
                    )
                    .with_for_update()
                ).mappings().one_or_none()

                if current is None:
                    raise ProjectRunRepositoryError(
                        "project run not found: "
                        f"{state.run_id}"
                    )

                stored_version = int(
                    current["version"]
                )

                if stored_version != expected_version:
                    raise ProjectRunVersionConflict(
                        "project run version conflict: "
                        f"expected {expected_version}, "
                        f"stored {stored_version}"
                    )

                maximum_sequence = connection.execute(
                    select(
                        func.max(
                            project_run_events.c.sequence
                        )
                    ).where(
                        project_run_events.c.run_id
                        == state.run_id
                    )
                ).scalar_one()

                next_sequence = int(
                    maximum_sequence or 0
                ) + 1

                event_detail = {
                    "status": state.status.value,
                    "version": state.version,
                }
                event_detail.update(
                    dict(detail or {})
                )

                event = ProjectRunEvent(
                    sequence=next_sequence,
                    run_id=state.run_id,
                    kind=event_kind,
                    occurred_at=occurred_at,
                    detail=event_detail,
                )

                result = connection.execute(
                    update(project_run_snapshots)
                    .where(
                        and_(
                            project_run_snapshots.c.run_id
                            == state.run_id,
                            project_run_snapshots.c.version
                            == expected_version,
                        )
                    )
                    .values(
                        project_id=state.project_id,
                        status=state.status.value,
                        version=state.version,
                        created_at=state.created_at,
                        updated_at=state.updated_at,
                        state_payload=_state_payload(
                            state
                        ),
                    )
                )

                if result.rowcount != 1:
                    raise ProjectRunVersionConflict(
                        "project run version changed "
                        "during transaction"
                    )

                connection.execute(
                    insert(project_run_events),
                    _event_values(event),
                )

        except (
            ProjectRunRepositoryError,
            ProjectRunVersionConflict,
        ):
            raise

        except IntegrityError as exc:
            raise ProjectRunVersionConflict(
                "project run event sequence conflict"
            ) from exc

        except SQLAlchemyError as exc:
            raise ProjectRunRepositoryError(
                "unable to save project run: "
                f"{state.run_id}"
            ) from exc

        return self.get(state.run_id)

    def append_event(
        self,
        run_id: str,
        *,
        kind: ProjectRunEventKind,
        occurred_at: float,
        task_id: str | None = None,
        detail: Mapping[str, object] | None = None,
    ) -> ProjectRunEvent:
        try:
            with self.engine.begin() as connection:
                existing = connection.execute(
                    select(
                        project_run_snapshots.c.run_id
                    )
                    .where(
                        project_run_snapshots.c.run_id
                        == run_id
                    )
                    .with_for_update()
                ).scalar_one_or_none()

                if existing is None:
                    raise ProjectRunRepositoryError(
                        "project run not found: "
                        f"{run_id}"
                    )

                maximum_sequence = connection.execute(
                    select(
                        func.max(
                            project_run_events.c.sequence
                        )
                    ).where(
                        project_run_events.c.run_id
                        == run_id
                    )
                ).scalar_one()

                event = ProjectRunEvent(
                    sequence=int(
                        maximum_sequence or 0
                    ) + 1,
                    run_id=run_id,
                    kind=kind,
                    occurred_at=occurred_at,
                    task_id=task_id,
                    detail=dict(detail or {}),
                )

                connection.execute(
                    insert(project_run_events),
                    _event_values(event),
                )

        except ProjectRunRepositoryError:
            raise

        except IntegrityError as exc:
            raise ProjectRunRepositoryError(
                "project run event sequence conflict: "
                f"{run_id}"
            ) from exc

        except SQLAlchemyError as exc:
            raise ProjectRunRepositoryError(
                "unable to append project run event: "
                f"{run_id}"
            ) from exc

        return event

    def exists(
        self,
        run_id: str,
    ) -> bool:
        try:
            with self.engine.connect() as connection:
                value = connection.execute(
                    select(
                        project_run_snapshots.c.run_id
                    ).where(
                        project_run_snapshots.c.run_id
                        == run_id
                    )
                ).scalar_one_or_none()

            return value is not None

        except SQLAlchemyError as exc:
            raise ProjectRunRepositoryError(
                "unable to inspect project run: "
                f"{run_id}"
            ) from exc

    def list_run_ids(
        self,
    ) -> tuple[str, ...]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(
                        project_run_snapshots.c.run_id
                    ).order_by(
                        project_run_snapshots.c.run_id
                    )
                ).scalars().all()

            return tuple(str(run_id) for run_id in rows)

        except SQLAlchemyError as exc:
            raise ProjectRunRepositoryError(
                "unable to list project runs"
            ) from exc

    def resumable(
        self,
    ) -> tuple[ProjectRunSnapshot, ...]:
        try:
            with self.engine.connect() as connection:
                run_ids = connection.execute(
                    select(
                        project_run_snapshots.c.run_id
                    )
                    .where(
                        project_run_snapshots.c.status.in_(
                            _RESUMABLE_STATUS_VALUES
                        )
                    )
                    .order_by(
                        project_run_snapshots.c.run_id
                    )
                ).scalars().all()

        except SQLAlchemyError as exc:
            raise ProjectRunRepositoryError(
                "unable to list resumable project runs"
            ) from exc

        return tuple(
            self.get(str(run_id))
            for run_id in run_ids
        )
