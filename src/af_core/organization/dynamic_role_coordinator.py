from __future__ import annotations

from pydantic import BaseModel, Field

from .automated_role_failover import (
    AutomatedRoleFailoverEngine,
)
from .dynamic_role_assignment import (
    DynamicRoleAssignmentEngine,
)
from .dynamic_role_models import (
    DynamicRoleAssignment,
    RoleAssignmentRequest,
    RoleAssignmentResult,
)
from .role_event_models import (
    RoleEventType,
)
from .role_event_publisher import (
    RoleEventPublisher,
)
from .role_failover_models import (
    RoleFailoverRequest,
    RoleFailoverResult,
)


class DynamicRoleLifecycleResult(BaseModel):
    selection: RoleAssignmentResult

    active_assignments: list[
        DynamicRoleAssignment
    ] = Field(
        default_factory=list
    )

    approved_assignments: list[
        DynamicRoleAssignment
    ] = Field(
        default_factory=list
    )

    activation_required: bool = False


class DynamicRoleCoordinator:
    """
    Coordinates dynamic role assignment, approval, activation,
    release, reassignment, failover, and lifecycle events.
    """

    def __init__(
        self,
        *,
        assignment_engine: (
            DynamicRoleAssignmentEngine
        ),
        failover_engine: (
            AutomatedRoleFailoverEngine
        ),
        publisher: RoleEventPublisher,
    ) -> None:
        self._assignment_engine = (
            assignment_engine
        )

        self._failover_engine = (
            failover_engine
        )

        self._publisher = publisher

    def assign_role(
        self,
        *,
        request: RoleAssignmentRequest,
        auto_activate: bool = True,
        approval_required: bool = False,
        protected_events: bool = False,
        environment: str = "runtime",
    ) -> DynamicRoleLifecycleResult:
        selection = (
            self._assignment_engine.assign(
                request
            )
        )

        active_assignments: list[
            DynamicRoleAssignment
        ] = []

        approved_assignments: list[
            DynamicRoleAssignment
        ] = []

        for assignment in (
            selection.assignments
        ):
            self._publisher.publish_assignment(
                event_type=(
                    RoleEventType
                    .ASSIGNMENT_PROPOSED
                ),
                assignment=assignment,
                protected=protected_events,
                environment=environment,
            )

            current = assignment

            if approval_required:
                current = (
                    self._assignment_engine
                    .approve(
                        assignment.assignment_id
                    )
                )

                approved_assignments.append(
                    current
                )

                self._publisher.publish_assignment(
                    event_type=(
                        RoleEventType
                        .ASSIGNMENT_APPROVED
                    ),
                    assignment=current,
                    protected=protected_events,
                    environment=environment,
                )

            if auto_activate:
                current = (
                    self._assignment_engine
                    .activate(
                        assignment.assignment_id
                    )
                )

                active_assignments.append(
                    current
                )

                self._publisher.publish_assignment(
                    event_type=(
                        RoleEventType
                        .ASSIGNMENT_ACTIVATED
                    ),
                    assignment=current,
                    protected=protected_events,
                    environment=environment,
                )

        return DynamicRoleLifecycleResult(
            selection=selection,
            active_assignments=(
                active_assignments
            ),
            approved_assignments=(
                approved_assignments
            ),
            activation_required=(
                bool(selection.assignments)
                and not auto_activate
            ),
        )

    def approve_assignment(
        self,
        *,
        assignment_id: str,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> DynamicRoleAssignment:
        approved = (
            self._assignment_engine.approve(
                assignment_id
            )
        )

        self._publisher.publish_assignment(
            event_type=(
                RoleEventType
                .ASSIGNMENT_APPROVED
            ),
            assignment=approved,
            protected=protected_event,
            environment=environment,
        )

        return approved

    def activate_assignment(
        self,
        *,
        assignment_id: str,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> DynamicRoleAssignment:
        active = (
            self._assignment_engine.activate(
                assignment_id
            )
        )

        self._publisher.publish_assignment(
            event_type=(
                RoleEventType
                .ASSIGNMENT_ACTIVATED
            ),
            assignment=active,
            protected=protected_event,
            environment=environment,
        )

        return active

    def release_role(
        self,
        *,
        assignment_id: str,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> DynamicRoleAssignment:
        released = (
            self._assignment_engine.release(
                assignment_id
            )
        )

        self._publisher.publish_assignment(
            event_type=(
                RoleEventType
                .ASSIGNMENT_RELEASED
            ),
            assignment=released,
            protected=protected_event,
            environment=environment,
        )

        return released

    def execute_failover(
        self,
        *,
        request: RoleFailoverRequest,
        protected_events: bool = False,
        environment: str = "runtime",
    ) -> RoleFailoverResult:
        result = (
            self._failover_engine.execute(
                request
            )
        )

        if result.completed:
            event_type = (
                RoleEventType
                .FAILOVER_COMPLETED
            )
        else:
            event_type = (
                RoleEventType
                .FAILOVER_BLOCKED
            )

        self._publisher.publish_failover(
            event_type=event_type,
            workspace_id=(
                request.workspace_id
            ),
            result=result,
            protected=protected_events,
            environment=environment,
        )

        return result
