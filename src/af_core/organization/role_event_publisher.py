from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    MessageType,
)

from .dynamic_role_models import (
    DynamicRoleAssignment,
)
from .role_event_models import (
    RoleAssignmentEventPayload,
    RoleEventType,
    RoleFailoverEventPayload,
)
from .role_failover_models import (
    RoleFailoverResult,
)


class RoleEventPublisher:
    """
    Publishes runtime role assignment and failover events
    through the Agent Communication Bus.
    """

    def __init__(
        self,
        bus: AgentCommunicationBus,
        *,
        sender_agent_id: str = (
            "dynamic-role-assignment-engine"
        ),
    ) -> None:
        self._bus = bus
        self._sender_agent_id = (
            sender_agent_id
        )

    def publish_assignment(
        self,
        *,
        event_type: RoleEventType,
        assignment: DynamicRoleAssignment,
        protected: bool = False,
        environment: str = "runtime",
    ):
        payload = (
            RoleAssignmentEventPayload
            .from_assignment(
                event_type=event_type,
                assignment=assignment,
            )
        )

        metadata = {
            "assignment_id":
                assignment.assignment_id,

            "team_id":
                assignment.team_id,

            "role_name":
                assignment.role_name,

            "assignment_status":
                assignment.status.value,
        }

        if protected:
            metadata.update(
                {
                    "required_permission":
                        "role_assignment_manage",

                    "environment":
                        environment,

                    "resource_scope":
                        assignment.team_id,
                }
            )

        message = AgentMessage(
            topic=event_type.value,
            message_type=(
                MessageType.EVENT_PUBLISHED
            ),
            sender_agent_id=(
                self._sender_agent_id
            ),
            workspace_id=(
                assignment.workspace_id
            ),
            correlation_id=(
                assignment.request_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata=metadata,
        )

        return self._bus.publish(
            message
        )

    def publish_failover(
        self,
        *,
        event_type: RoleEventType,
        workspace_id: str,
        result: RoleFailoverResult,
        protected: bool = False,
        environment: str = "runtime",
    ):
        payload = (
            RoleFailoverEventPayload
            .from_result(
                event_type=event_type,
                result=result,
            )
        )

        metadata = {
            "failover_request_id":
                result.failover_request_id,

            "team_id":
                result.assessment.team_id,

            "role_name":
                result.assessment.role_name,

            "decision":
                result.assessment
                .decision.value,
        }

        if protected:
            metadata.update(
                {
                    "required_permission":
                        "role_failover_execute",

                    "environment":
                        environment,

                    "resource_scope":
                        result.assessment.team_id,
                }
            )

        message = AgentMessage(
            topic=event_type.value,
            message_type=(
                MessageType.EVENT_PUBLISHED
            ),
            sender_agent_id=(
                self._sender_agent_id
            ),
            workspace_id=workspace_id,
            correlation_id=(
                result.failover_request_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata=metadata,
        )

        return self._bus.publish(
            message
        )
