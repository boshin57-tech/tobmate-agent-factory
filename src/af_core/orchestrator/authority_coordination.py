"""Authority-gated multi-agent task assignment."""

from __future__ import annotations

from af_core.orchestrator.coordination_engine import (
    CoordinationEngine,
)
from af_core.orchestrator.coordination_models import (
    CoordinationAssignment,
    CoordinationConflict,
    CoordinationConflictType,
    CoordinationDecision,
)
from af_core.orchestrator.coordination_registry import (
    CoordinationRegistry,
)
from af_core.runtime.authority_engine import AuthorityEngine
from af_core.runtime.capability_models import (
    AuthorityRequest,
    CapabilityScope,
)


class AuthorityAwareCoordinationEngine:
    def __init__(
        self,
        *,
        registry: CoordinationRegistry,
        coordination: CoordinationEngine,
        authority: AuthorityEngine,
    ) -> None:
        self._registry = registry
        self._coordination = coordination
        self._authority = authority

    def assign(
        self,
        *,
        task_id: str,
        agent_id: str,
    ) -> CoordinationAssignment:
        task = self._registry.get_task(task_id)

        evaluations = []

        for capability_id in sorted(
            task.required_capability_ids
        ):
            evaluation = self._authority.evaluate(
                AuthorityRequest(
                    subject_id=agent_id,
                    capability_id=capability_id,
                    scope=CapabilityScope.TASK,
                    scope_id=task_id,
                    resource=task_id,
                    action="task.assign",
                )
            )
            evaluations.append(evaluation)

            if not evaluation.allowed:
                conflict = CoordinationConflict(
                    conflict_type=(
                        CoordinationConflictType
                        .AUTHORITY_DENIED
                    ),
                    task_id=task_id,
                    agent_id=agent_id,
                    reason=(
                        "Authority denied capability "
                        f"{capability_id}: "
                        f"{evaluation.reason}"
                    ),
                )

                self._coordination._record_conflict(
                    conflict
                )

                assignment = CoordinationAssignment(
                    task_id=task_id,
                    agent_id=agent_id,
                    decision=CoordinationDecision.BLOCK,
                    reason=conflict.reason,
                    metadata={
                        "conflict_id": conflict.conflict_id,
                        "conflict_type": (
                            conflict.conflict_type.value
                        ),
                        "authority": [
                            item.model_dump(mode="json")
                            for item in evaluations
                        ],
                    },
                )

                self._coordination._record_assignment(
                    assignment
                )
                return assignment

        assignment = self._coordination.assign(
            task_id=task_id,
            agent_id=agent_id,
        )

        if evaluations:
            assignment = assignment.model_copy(
                update={
                    "metadata": {
                        **assignment.metadata,
                        "authority": [
                            item.model_dump(mode="json")
                            for item in evaluations
                        ],
                    }
                }
            )
            self._coordination._replace_last_assignment(
                assignment
            )

        return assignment

    def reassign(
        self,
        *,
        task_id: str,
        agent_id: str,
    ) -> CoordinationAssignment:
        task = self._registry.get_task(task_id)

        if task.assigned_agent_id is not None:
            reset = task.model_copy(
                update={
                    "assigned_agent_id": None,
                    "status": "pending",
                }
            )
            self._registry.update_task(reset)

        result = self.assign(
            task_id=task_id,
            agent_id=agent_id,
        )

        if result.decision is CoordinationDecision.ASSIGN:
            result = result.model_copy(
                update={
                    "decision": CoordinationDecision.REASSIGN,
                    "reason": "Task reassigned with authority",
                }
            )
            self._coordination._replace_last_assignment(
                result
            )

        return result
