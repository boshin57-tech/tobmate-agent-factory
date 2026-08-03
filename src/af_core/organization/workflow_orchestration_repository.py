from __future__ import annotations

from .workflow_orchestration_models import (
    OrchestrationCheckpoint,
    WorkflowExecutionRecord,
    WorkflowOrchestration,
)


class WorkflowOrchestrationRepository:
    """
    In-memory repository for multi-workflow orchestration state.
    """

    def __init__(self) -> None:
        self._orchestrations: dict[
            str,
            WorkflowOrchestration,
        ] = {}

        self._execution_records: dict[
            str,
            list[WorkflowExecutionRecord],
        ] = {}

        self._checkpoints: dict[
            str,
            list[OrchestrationCheckpoint],
        ] = {}

    def save(
        self,
        orchestration: WorkflowOrchestration,
    ) -> WorkflowOrchestration:
        if (
            orchestration.orchestration_id
            in self._orchestrations
        ):
            raise ValueError(
                "workflow orchestration already exists"
            )

        self._orchestrations[
            orchestration.orchestration_id
        ] = orchestration

        self._execution_records.setdefault(
            orchestration.orchestration_id,
            [],
        )

        self._checkpoints.setdefault(
            orchestration.orchestration_id,
            [],
        )

        return orchestration

    def replace(
        self,
        orchestration: WorkflowOrchestration,
    ) -> WorkflowOrchestration:
        if (
            orchestration.orchestration_id
            not in self._orchestrations
        ):
            raise ValueError(
                "workflow orchestration does not exist"
            )

        self._orchestrations[
            orchestration.orchestration_id
        ] = orchestration

        return orchestration

    def get(
        self,
        orchestration_id: str,
    ) -> WorkflowOrchestration | None:
        return self._orchestrations.get(
            orchestration_id
        )

    def by_workspace(
        self,
        workspace_id: str,
    ) -> tuple[
        WorkflowOrchestration,
        ...
    ]:
        return tuple(
            orchestration
            for orchestration
            in self._orchestrations.values()
            if (
                orchestration.workspace_id
                == workspace_id
            )
        )

    def add_execution_record(
        self,
        record: WorkflowExecutionRecord,
    ) -> WorkflowExecutionRecord:
        if (
            record.orchestration_id
            not in self._orchestrations
        ):
            raise ValueError(
                "workflow orchestration does not exist"
            )

        self._execution_records.setdefault(
            record.orchestration_id,
            [],
        ).append(record)

        return record

    def replace_execution_record(
        self,
        record: WorkflowExecutionRecord,
    ) -> WorkflowExecutionRecord:
        records = self._execution_records.get(
            record.orchestration_id,
            [],
        )

        for index, existing in enumerate(
            records
        ):
            if (
                existing.execution_id
                == record.execution_id
            ):
                records[index] = record
                return record

        raise ValueError(
            "workflow execution record not found"
        )

    def execution_records(
        self,
        orchestration_id: str,
    ) -> tuple[
        WorkflowExecutionRecord,
        ...
    ]:
        return tuple(
            self._execution_records.get(
                orchestration_id,
                [],
            )
        )

    def add_checkpoint(
        self,
        checkpoint: OrchestrationCheckpoint,
    ) -> OrchestrationCheckpoint:
        if (
            checkpoint.orchestration_id
            not in self._orchestrations
        ):
            raise ValueError(
                "workflow orchestration does not exist"
            )

        self._checkpoints.setdefault(
            checkpoint.orchestration_id,
            [],
        ).append(checkpoint)

        return checkpoint

    def checkpoints(
        self,
        orchestration_id: str,
    ) -> tuple[
        OrchestrationCheckpoint,
        ...
    ]:
        return tuple(
            self._checkpoints.get(
                orchestration_id,
                [],
            )
        )

    def latest_checkpoint(
        self,
        orchestration_id: str,
    ) -> OrchestrationCheckpoint | None:
        checkpoints = self._checkpoints.get(
            orchestration_id,
            [],
        )

        if not checkpoints:
            return None

        return checkpoints[-1]

    def all(
        self,
    ) -> tuple[
        WorkflowOrchestration,
        ...
    ]:
        return tuple(
            self._orchestrations.values()
        )

    @property
    def count(self) -> int:
        return len(
            self._orchestrations
        )
