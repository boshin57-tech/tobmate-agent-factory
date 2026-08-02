"""Workflow scheduling, checkpointing, and recovery."""

from __future__ import annotations

from datetime import datetime
from threading import RLock

from af_core.orchestrator.workflow_models import (
    WorkflowCheckpoint,
    WorkflowDecision,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowScheduleDecision,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepStatus,
)


class WorkflowEngineError(RuntimeError):
    pass


class WorkflowCheckpointStore:
    def __init__(self) -> None:
        self._checkpoints: dict[
            str,
            list[WorkflowCheckpoint],
        ] = {}
        self._lock = RLock()

    def append(
        self,
        run: WorkflowRun,
    ) -> WorkflowCheckpoint:
        with self._lock:
            items = self._checkpoints.setdefault(
                run.run_id,
                [],
            )

            checkpoint = WorkflowCheckpoint(
                run_id=run.run_id,
                sequence=len(items) + 1,
                status=run.status,
                steps=run.steps,
            )
            items.append(checkpoint)
            return checkpoint

    def latest(
        self,
        run_id: str,
    ) -> WorkflowCheckpoint:
        with self._lock:
            items = self._checkpoints.get(run_id, [])

            if not items:
                raise WorkflowEngineError(
                    f"No checkpoint for run: {run_id}"
                )

            return items[-1]

    def list_for_run(
        self,
        run_id: str,
    ) -> tuple[WorkflowCheckpoint, ...]:
        with self._lock:
            return tuple(
                self._checkpoints.get(run_id, [])
            )


class WorkflowEngine:
    def __init__(
        self,
        *,
        checkpoints: WorkflowCheckpointStore | None = None,
    ) -> None:
        self._runs: dict[str, WorkflowRun] = {}
        self._decisions: list[
            WorkflowScheduleDecision
        ] = []
        self._checkpoints = (
            checkpoints or WorkflowCheckpointStore()
        )
        self._lock = RLock()

    def create_run(
        self,
        workflow: WorkflowDefinition,
    ) -> WorkflowRun:
        run = WorkflowRun(
            workflow_id=workflow.workflow_id,
            workflow_version=workflow.version,
            steps=workflow.steps,
        )

        with self._lock:
            self._runs[run.run_id] = run

        self._checkpoints.append(run)
        return run

    def start_run(
        self,
        run_id: str,
        *,
        started_at: datetime | None = None,
    ) -> WorkflowRun:
        run = self.get_run(run_id)

        if run.status is not WorkflowStatus.PENDING:
            raise WorkflowEngineError(
                "Only pending workflows may start"
            )

        updated = run.model_copy(
            update={
                "status": WorkflowStatus.RUNNING,
                "started_at": started_at,
            }
        )
        return self._save(updated)

    def ready_steps(
        self,
        run_id: str,
    ) -> tuple[WorkflowStep, ...]:
        run = self.get_run(run_id)

        completed = {
            step.step_id
            for step in run.steps
            if step.status
            is WorkflowStepStatus.COMPLETED
        }

        compensation_steps = {
            step.compensation_step_id
            for step in run.steps
            if step.compensation_step_id is not None
        }

        return tuple(
            step
            for step in run.steps
            if (
                step.step_id not in compensation_steps
                and step.status
                in {
                    WorkflowStepStatus.PENDING,
                    WorkflowStepStatus.READY,
                    WorkflowStepStatus.RETRYING,
                }
                and set(step.dependency_ids).issubset(
                    completed
                )
            )
        )

    def schedule_ready(
        self,
        run_id: str,
    ) -> tuple[WorkflowScheduleDecision, ...]:
        run = self.get_run(run_id)

        if run.status is not WorkflowStatus.RUNNING:
            raise WorkflowEngineError(
                "Workflow must be running"
            )

        ready = self.ready_steps(run_id)
        decisions: list[
            WorkflowScheduleDecision
        ] = []

        for step in ready:
            decision = WorkflowScheduleDecision(
                run_id=run_id,
                step_id=step.step_id,
                decision=WorkflowDecision.SCHEDULE,
                reason="Dependencies completed",
            )
            decisions.append(decision)

        if not ready:
            decisions.append(
                WorkflowScheduleDecision(
                    run_id=run_id,
                    decision=WorkflowDecision.WAIT,
                    reason="No workflow step is ready",
                )
            )

        with self._lock:
            self._decisions.extend(decisions)

        return tuple(decisions)

    def execute_step(
        self,
        *,
        run_id: str,
        step_id: str,
        success: bool,
        error: str | None = None,
    ) -> WorkflowRun:
        run = self.get_run(run_id)

        target = self._find_step(
            run,
            step_id,
        )

        if target.status not in {
            WorkflowStepStatus.READY,
            WorkflowStepStatus.RUNNING,
            WorkflowStepStatus.RETRYING,
        }:
            updated_status = (
                WorkflowStepStatus.RUNNING
            )
        else:
            updated_status = target.status

        attempt = target.attempt_count + 1

        if success:
            new_step = target.model_copy(
                update={
                    "status": (
                        WorkflowStepStatus.COMPLETED
                    ),
                    "attempt_count": attempt,
                }
            )

            updated = self._replace_step(
                run,
                new_step,
            )

            return self._save(
                self._auto_complete_if_finished(
                    updated
                )
            )

        if attempt < target.maximum_attempts:
            new_step = target.model_copy(
                update={
                    "status": (
                        WorkflowStepStatus.RETRYING
                    ),
                    "attempt_count": attempt,
                    "metadata": {
                        **target.metadata,
                        "last_error": error,
                    },
                }
            )

            return self._save(
                self._replace_step(
                    run,
                    new_step,
                )
            )

        new_step = target.model_copy(
            update={
                "status": WorkflowStepStatus.FAILED,
                "attempt_count": attempt,
                "metadata": {
                    **target.metadata,
                    "last_error": error,
                },
            }
        )

        failed_run = self._replace_step(
            run,
            new_step,
        ).model_copy(
            update={
                "status": WorkflowStatus.FAILED,
            }
        )

        return self._save(failed_run)

    def compensate(
        self,
        run_id: str,
    ) -> WorkflowRun:
        run = self.get_run(run_id)

        if run.status is not WorkflowStatus.FAILED:
            raise WorkflowEngineError(
                "Only failed workflows can compensate"
            )

        compensated_steps: list[WorkflowStep] = []

        for step in run.steps:
            if (
                step.status
                is WorkflowStepStatus.COMPLETED
            ):
                compensated_steps.append(
                    step.model_copy(
                        update={
                            "status": (
                                WorkflowStepStatus
                                .COMPENSATED
                            )
                        }
                    )
                )
            else:
                compensated_steps.append(step)

        updated = run.model_copy(
            update={
                "status": (
                    WorkflowStatus.COMPENSATING
                ),
                "steps": tuple(
                    compensated_steps
                ),
            }
        )

        return self._save(updated)

    def recover(
        self,
        run_id: str,
    ) -> WorkflowRun:
        checkpoint = (
            self._checkpoints.latest(run_id)
        )

        recovered = WorkflowRun(
            run_id=checkpoint.run_id,
            workflow_id=(
                self.get_run(run_id).workflow_id
            ),
            workflow_version=(
                self.get_run(run_id)
                .workflow_version
            ),
            status=checkpoint.status,
            steps=checkpoint.steps,
        )

        return self._save(recovered)

    def decisions(
        self,
    ) -> tuple[WorkflowScheduleDecision, ...]:
        with self._lock:
            return tuple(self._decisions)

    def get_run(
        self,
        run_id: str,
    ) -> WorkflowRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise WorkflowEngineError(
                    f"Unknown workflow run: {run_id}"
                ) from exc

    def _save(
        self,
        run: WorkflowRun,
    ) -> WorkflowRun:
        with self._lock:
            self._runs[run.run_id] = run

        self._checkpoints.append(run)

        return run

    @staticmethod
    def _find_step(
        run: WorkflowRun,
        step_id: str,
    ) -> WorkflowStep:
        for step in run.steps:
            if step.step_id == step_id:
                return step

        raise WorkflowEngineError(
            f"Unknown workflow step: {step_id}"
        )

    @staticmethod
    def _replace_step(
        run: WorkflowRun,
        replacement: WorkflowStep,
    ) -> WorkflowRun:
        steps = tuple(
            replacement
            if step.step_id == replacement.step_id
            else step
            for step in run.steps
        )

        return run.model_copy(
            update={
                "steps": steps,
            }
        )

    @staticmethod
    def _auto_complete_if_finished(
        run: WorkflowRun,
    ) -> WorkflowRun:
        if all(
            step.status
            in {
                WorkflowStepStatus.COMPLETED,
                WorkflowStepStatus.COMPENSATED,
            }
            for step in run.steps
        ):
            return run.model_copy(
                update={
                    "status": (
                        WorkflowStatus.COMPLETED
                    )
                }
            )

        return run
